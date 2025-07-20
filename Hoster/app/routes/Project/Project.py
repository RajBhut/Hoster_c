from fastapi import Request, APIRouter, Response
from fastapi.responses import RedirectResponse, JSONResponse
import requests
import docker
import os
import shutil
import zipfile
import tempfile
import json
import base64
import boto3
from dotenv import load_dotenv

from app.config import oauth

load_dotenv()


AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_BASE_URL = os.getenv("S3_BASE_URL", f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_BASE_URL = os.getenv("S3_BASE_URL", f"https://{S3_BUCKET_NAME}.s3.amazonaws.com/")

project_router = APIRouter()


docker_client = None
try:
    docker_client = docker.from_env()
    print("Docker client initialized successfully")
except Exception as e:
    print(f"Docker not available: {e}")

@project_router.get("/repos")
async def get_user_repos(request: Request):
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        resp = await oauth.github.get('user/repos', token=token)
        repos = resp.json()
        
        react_repos = []
        for repo in repos:
            is_react = await is_react_project(request, repo['owner']['login'], repo['name'])
            repo_info = {
                "name": repo['name'],
                "full_name": repo['full_name'],
                "owner": repo['owner']['login'],
                "description": repo.get('description', ''),
                "is_react": is_react,
                "clone_url": repo['clone_url'],
                "updated_at": repo['updated_at']
            }
            react_repos.append(repo_info)
        
        return {
            "repos": react_repos,
            "docker_available": docker_client is not None
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
        
@project_router.delete("/s3/{owner}/{repo}")
async def delete_s3_hosted_project(request: Request, owner: str, repo: str):
    
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME]):
        return JSONResponse({
            "error": "S3 not configured", 
            "configured": False
        }, status_code=400)
    
    s3_prefix = f"projects/{owner}/{repo}"
    
    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION,
        )
        
        response = s3.list_objects_v2(
            Bucket=S3_BUCKET_NAME,
            Prefix=s3_prefix
        )
        
        if 'Contents' in response:
            objects_to_delete = [{'Key': item['Key']} for item in response['Contents']]
            
            s3.delete_objects(
                Bucket=S3_BUCKET_NAME,
                Delete={
                    'Objects': objects_to_delete
                }
            )
            
            return {
                "success": True,
                "message": f"Deleted {len(objects_to_delete)} files from S3 for {owner}/{repo}",
                "deleted_count": len(objects_to_delete)
            }
        else:
            return {
                "success": True,
                "message": f"No files found for {owner}/{repo} in S3",
                "deleted_count": 0
            }
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@project_router.post("/build/{owner}/{repo}")
async def build_react_project(request: Request, owner: str, repo: str):
    
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    if not docker_client:
        return JSONResponse({
            "success": False,
            "error": "Docker Desktop needs to be installed and running"
        }, status_code=400)
    
    
    if not await is_react_project(request, owner, repo):
        return JSONResponse({
            "success": False,
            "error": "This project is not a React project"
        }, status_code=400)
    
    try:
        headers = {'Authorization': f'token {token["access_token"]}'}
        zip_url = f'https://api.github.com/repos/{owner}/{repo}/zipball'
        
        response = requests.get(zip_url, headers=headers)
        if response.status_code != 200:
            return JSONResponse({"success": False, "error": "Failed to download repository"}, status_code=400)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, f"{repo}.zip")
            extract_path = os.path.join(temp_dir, "extracted")
            build_output = os.path.join(temp_dir, "build_output")
            os.makedirs(build_output)
            
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            
            extracted_folders = os.listdir(extract_path)
            if not extracted_folders:
                return JSONResponse({"success": False, "error": "No files extracted"}, status_code=400)
            
            repo_path = os.path.join(extract_path, extracted_folders[0])
            
            await modify_package_json_for_relative_paths(repo_path)
            
            build_result = await build_react_in_docker(repo_path, build_output, owner, repo)
            
            if build_result["success"]:
                server_build_dir = f"./builds/{owner}_{repo}"
                os.makedirs(server_build_dir, exist_ok=True)
                
                s3_source_folder = None
                
                if os.path.exists(build_output) and os.listdir(build_output):
                    if os.path.exists(os.path.join(build_output, "index.html")):
                        print(f"Found index.html in build_output directory")
                        s3_source_folder = build_output
                    else:
                        possible_build_dirs = [
                            os.path.join(build_output, "build"),  
                            os.path.join(build_output, "dist"),   
                        ]
                        
                        for build_dir in possible_build_dirs:
                            if os.path.exists(build_dir) and os.path.isdir(build_dir):
                                if os.path.exists(os.path.join(build_dir, "index.html")):
                                    print(f"Found build directory: {build_dir}")
                                    s3_source_folder = build_dir
                                    break
                    
                    if not s3_source_folder:
                        print("No specific build folder found, using build_output directly")
                        s3_source_folder = build_output
                    
                    print(f"Copying from {s3_source_folder} to {server_build_dir}")
                    shutil.copytree(s3_source_folder, server_build_dir, dirs_exist_ok=True)
                    
                    static_folder = os.path.join(s3_source_folder, "static")
                    if os.path.exists(static_folder) and os.path.isdir(static_folder):
                        print(f"Ensuring static folder is copied properly")
                        static_server_dir = os.path.join(server_build_dir, "static")
                        os.makedirs(static_server_dir, exist_ok=True)
                        shutil.copytree(static_folder, static_server_dir, dirs_exist_ok=True)
                    
                    await fix_index_html_paths(s3_source_folder)
                
                s3_prefix = f"projects/{owner}/{repo}"
                print(f"Starting S3 upload from {s3_source_folder} to {s3_prefix}")
                s3_urls = upload_folder_to_s3(s3_source_folder, s3_prefix)
                s3_base_url = f"{S3_BASE_URL}projects/{owner}/{repo}/" if S3_BASE_URL else None
                
                print(f"S3 upload complete, got {len(s3_urls)} files")
                return {
                    "success": True,
                    "message": f"Project {owner}/{repo} built successfully",
                    "build_path": server_build_dir,
                    "build_id": f"{owner}_{repo}",
                    "logs": build_result["logs"],
                    "s3_url": s3_base_url,
                    "s3_files": s3_urls[:5] if s3_urls else [],
                    "file_count": len(s3_urls) if s3_urls else 0
                }
            else:
                return JSONResponse({
                    "success": False,
                    "error": build_result["error"],
                    "logs": build_result["logs"]
                }, status_code=400)
                
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@project_router.get("/builds")
async def list_builds(request: Request):
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    builds_dir = "./builds"
    if not os.path.exists(builds_dir):
        os.makedirs(builds_dir)
        return {"builds": []}
    
    builds = []
    for build_folder in os.listdir(builds_dir):
        build_path = os.path.join(builds_dir, build_folder)
        if os.path.isdir(build_path):
            files = os.listdir(build_path)
            has_index = 'index.html' in files
            builds.append({
                "id": build_folder,
                "name": build_folder.replace('_', '/'),
                "path": build_path,
                "file_count": len(files),
                "has_index": has_index,
                "files": files[:10]  
            })
    
    return {"builds": builds}

@project_router.get("/s3-info/{owner}/{repo}")
async def get_s3_hosting_info(request: Request, owner: str, repo: str):
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME]):
        return JSONResponse({
            "error": "S3 not configured",
            "configured": False
        }, status_code=400)
    
    s3_prefix = f"projects/{owner}/{repo}"
    s3_base_url = f"{S3_BASE_URL}projects/{owner}/{repo}/"
    
    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION,
        )
        
        response = s3.list_objects_v2(
            Bucket=S3_BUCKET_NAME,
            Prefix=s3_prefix
        )
        
        files = []
        has_static_folder = False
        if 'Contents' in response:
            for item in response['Contents'][:50]:  
                key = item['Key']
                file_url = f"{S3_BASE_URL}{key}"
                
                if '/static/' in key or '/assets/' in key:
                    has_static_folder = True
                
                files.append({
                    "key": key,
                    "url": file_url,
                    "size": item['Size'],
                    "last_modified": item['LastModified'].isoformat()
                })
        
        has_index = any(f["key"].endswith("index.html") for f in files)
        
        website_url = None
        try:
            website_config = s3.get_bucket_website(Bucket=S3_BUCKET_NAME)
            region = s3.get_bucket_location(Bucket=S3_BUCKET_NAME)['LocationConstraint'] or 'us-east-1'
            website_url = f"http://{S3_BUCKET_NAME}.s3-website-{region}.amazonaws.com/projects/{owner}/{repo}/"
        except Exception as e:
            website_config = str(e)
        
        return {
            "owner": owner,
            "repo": repo,
            "s3_base_url": s3_base_url,
            "website_url": website_url,
            "configured": True,
            "files": files,
            "file_count": len(files),
            "has_index": has_index,
            "has_static_folder": has_static_folder,
            "directories": list(set(["/".join(f["key"].split("/")[:-1]) for f in files if "/" in f["key"]]))
        }
    except Exception as e:
        return JSONResponse({
            "error": str(e),
            "configured": True,
            "success": False
        }, status_code=500)

@project_router.get("/debug-s3/{owner}/{repo}")
async def debug_s3_project(request: Request, owner: str, repo: str):
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME]):
        return JSONResponse({
            "error": "S3 not configured",
            "configured": False
        }, status_code=400)
    
    s3_prefix = f"projects/{owner}/{repo}"
    
    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION,
        )
        
        try:
            bucket_info = s3.get_bucket_location(Bucket=S3_BUCKET_NAME)
            bucket_region = bucket_info['LocationConstraint'] or "us-east-1"
        except Exception as e:
            bucket_region = f"Error: {str(e)}"
            
        try:
            website_config = s3.get_bucket_website(Bucket=S3_BUCKET_NAME)
        except Exception as e:
            website_config = f"Not configured as website: {str(e)}"
        
        response = s3.list_objects_v2(
            Bucket=S3_BUCKET_NAME,
            Prefix=s3_prefix
        )
        
        files = []
        if 'Contents' in response:
            for item in response['Contents']:
                key = item['Key']
                try:
                    head = s3.head_object(Bucket=S3_BUCKET_NAME, Key=key)
                    content_type = head.get('ContentType', 'unknown')
                except Exception as e:
                    content_type = f"Error: {str(e)}"
                
                file_url = f"{S3_BASE_URL}{key}"
                files.append({
                    "key": key,
                    "url": file_url,
                    "size": item['Size'],
                    "content_type": content_type,
                    "last_modified": item['LastModified'].isoformat()
                })
        
        directories = set()
        for file in files:
            path_parts = file["key"].split("/")
            for i in range(1, len(path_parts)):
                directories.add("/".join(path_parts[:i]))
        
        return {
            "owner": owner,
            "repo": repo,
            "s3_bucket": S3_BUCKET_NAME,
            "s3_region": bucket_region,
            "s3_website_config": website_config,
            "s3_base_url": S3_BASE_URL,
            "file_count": len(files),
            "files": files,
            "has_index": any(f["key"].endswith("index.html") for f in files),
            "has_static_folder": any("/static/" in f["key"] for f in files),
            "has_assets_folder": any("/assets/" in f["key"] for f in files),
            "directories": sorted(list(directories))
        }
    except Exception as e:
        return JSONResponse({
            "error": str(e),
            "success": False
        }, status_code=500)

@project_router.delete("/builds/{build_id}")
async def delete_build(request: Request, build_id: str):
    
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    build_path = f"./builds/{build_id}"
    if os.path.exists(build_path):
        try:
            shutil.rmtree(build_path)
            return {"success": True, "message": f"Build {build_id} deleted"}
        except Exception as e:
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)
    else:
        return JSONResponse({"success": False, "error": "Build not found"}, status_code=404)


@project_router.post("/setup-s3-website")
async def setup_s3_website(request: Request):
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME]):
        return JSONResponse({
            "error": "S3 not configured",
            "configured": False
        }, status_code=400)
    
    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION,
        )
        
        try:
            website_configuration = {
                'ErrorDocument': {'Key': 'index.html'},
                'IndexDocument': {'Suffix': 'index.html'},
            }
            
            s3.put_bucket_website(
                Bucket=S3_BUCKET_NAME,
                WebsiteConfiguration=website_configuration
            )
            
            region = s3.get_bucket_location(Bucket=S3_BUCKET_NAME)
            region_name = region['LocationConstraint'] or 'us-east-1'
            website_url = f"http://{S3_BUCKET_NAME}.s3-website-{region_name}.amazonaws.com/"
            
            return {
                "success": True,
                "message": "S3 bucket configured for static website hosting",
                "website_url": website_url
            }
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": f"Failed to configure website hosting: {str(e)}"
            }, status_code=500)
            
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

def upload_folder_to_s3(local_folder, s3_prefix):
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY or not S3_BUCKET_NAME:
        print("S3 credentials not configured, skipping upload")
        return []
        
    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION,
        )
        bucket = S3_BUCKET_NAME
        
        print(f"Uploading from {local_folder} to S3 bucket {bucket} with prefix {s3_prefix}")
        total_files = sum(len(files) for _, _, files in os.walk(local_folder))
        print(f"Found {total_files} files to upload")
        
        uploaded_files = []
        file_count = 0
        
        for root, dirs, files in os.walk(local_folder):
            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, local_folder)
                s3_key = f"{s3_prefix}/{relative_path}".replace("\\", "/")
                
                content_type = "application/octet-stream"  
                lower_file = file.lower()
                
                if lower_file.endswith((".html", ".htm")):
                    content_type = "text/html"
                elif lower_file.endswith(".css"):
                    content_type = "text/css"
                elif lower_file.endswith(".js"):
                    content_type = "application/javascript"
                elif lower_file.endswith(".json"):
                    content_type = "application/json"
                
                elif lower_file.endswith(".png"):
                    content_type = "image/png"
                elif lower_file.endswith((".jpg", ".jpeg")):
                    content_type = "image/jpeg"
                elif lower_file.endswith(".gif"):
                    content_type = "image/gif"
                elif lower_file.endswith(".svg"):
                    content_type = "image/svg+xml"
                elif lower_file.endswith(".webp"):
                    content_type = "image/webp"
                elif lower_file.endswith(".ico"):
                    content_type = "image/x-icon"
                
                # Fonts
                elif lower_file.endswith(".woff"):
                    content_type = "font/woff"
                elif lower_file.endswith(".woff2"):
                    content_type = "font/woff2"
                elif lower_file.endswith(".ttf"):
                    content_type = "font/ttf"
                elif lower_file.endswith(".otf"):
                    content_type = "font/otf"
                
                print(f"Uploading {relative_path} as {content_type}")
                
                try:
                    s3.upload_file(
                        local_path, 
                        bucket, 
                        s3_key, 
                        ExtraArgs={
                            "ContentType": content_type
                        }
                    )
                    file_count += 1
                    uploaded_files.append(f"{S3_BASE_URL}{s3_key}")
                except Exception as e:
                    print(f"Failed to upload {relative_path}: {str(e)}")
                
        print(f"Successfully uploaded {file_count} of {total_files} files to S3")
        return uploaded_files
    except Exception as e:
        print(f"S3 upload error: {str(e)}")
        return []

async def is_react_project(request: Request, owner: str, repo: str):
    token = request.session.get('token')
    if not token:
        return False
    
    try:
        headers = {'Authorization': f'token {token["access_token"]}'}
        url = f'https://api.github.com/repos/{owner}/{repo}/contents/package.json'
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            content = response.json()
            if content.get("encoding") == "base64":
                package_json = base64.b64decode(content['content']).decode('utf-8')
                package_data = json.loads(package_json)
                
                dependencies = package_data.get('dependencies', {})
                dev_dependencies = package_data.get('devDependencies', {})
                
                return ('react' in dependencies or 'react' in dev_dependencies)
        
        return False
    except:
        return False

async def fix_index_html_paths(folder_path):
    index_path = os.path.join(folder_path, "index.html")
    if not os.path.exists(index_path):
        print(f"No index.html found in {folder_path}")
        return False
        
    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        html_content = html_content.replace('src="/static/', 'src="./static/')
        html_content = html_content.replace('href="/static/', 'href="./static/')
        
        html_content = html_content.replace('src="/assets/', 'src="./assets/')
        html_content = html_content.replace('href="/assets/', 'href="./assets/')
        
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        return True
    except Exception as e:
        print(f"Error fixing index.html paths: {str(e)}")
        return False

async def modify_package_json_for_relative_paths(repo_path):
    package_json_path = os.path.join(repo_path, "package.json")
    if not os.path.exists(package_json_path):
        print("package.json not found, skipping modification")
        return False
    
    try:
        with open(package_json_path, 'r', encoding='utf-8') as f:
            package_data = json.load(f)
        
        package_data["homepage"] = "."
        
        vite_config_candidates = [
            os.path.join(repo_path, "vite.config.js"),
            os.path.join(repo_path, "vite.config.ts")
        ]
        
        vite_config_path = None
        for candidate in vite_config_candidates:
            if os.path.exists(candidate):
                vite_config_path = candidate
                break
        
        with open(package_json_path, 'w', encoding='utf-8') as f:
            json.dump(package_data, f, indent=2)
        
        if vite_config_path:
            try:
                print(f"Modifying Vite config at {vite_config_path}")
                with open(vite_config_path, 'r', encoding='utf-8') as f:
                    vite_config = f.read()
                
                if 'export default' in vite_config and ('defineConfig' in vite_config or 'define' in vite_config):
                    if 'base:' not in vite_config:
                      
                        if '{' in vite_config:
                            new_config = vite_config.replace('{', '{\n  base: "./",', 1)
                            with open(vite_config_path, 'w', encoding='utf-8') as f:
                                f.write(new_config)
                            print("Added base: './' to Vite config")
                        else:
                            print("Could not find opening brace in Vite config")
                    else:
                        print("Vite config already has 'base' configuration")
            except Exception as e:
                print(f"Error modifying Vite config: {str(e)}")
        
        return True
    except Exception as e:
        print(f"Error modifying package.json: {str(e)}")
        return False

async def build_react_in_docker(repo_path: str, build_output: str, owner: str, repo: str):
    
    if not docker_client:
        return {
            "success": False,
            "error": "Docker not available",
            "logs": ["Docker Desktop is not running"]
        }
    
    try:
        dockerfile_content = """
FROM node:18-alpine
WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Determine if it's a CRA or Vite project and build accordingly
RUN if grep -q "react-scripts" package.json; then \\
        echo "Building Create React App project..." && \\
        npm run build; \\
    elif grep -q "vite" package.json; then \\
        echo "Building Vite project..." && \\
        npm run build; \\
    else \\
        echo "Unknown React project type, attempting to build..." && \\
        npm run build; \\
    fi

# List the build output for debugging
RUN echo "Listing build output directories:" && \\
    ls -la && \\
    (ls -la build 2>/dev/null || echo "No 'build' directory") && \\
    (ls -la dist 2>/dev/null || echo "No 'dist' directory")

CMD ["tail", "-f", "/dev/null"]
"""
        
        dockerfile_path = os.path.join(repo_path, "Dockerfile.build")
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)
        
        image_tag = f"react_build_{owner}_{repo}".lower().replace('-', '_').replace('.', '_')
        
        image, logs = docker_client.images.build(
            path=repo_path,
            dockerfile="Dockerfile.build",
            tag=image_tag,
            rm=True
        )
        
        abs_build_output = os.path.abspath(build_output)
        container = docker_client.containers.run(
            image_tag,
            detach=True,
            volumes={abs_build_output: {'bind': '/output', 'mode': 'rw'}},
            working_dir='/app'
        )
        
        import time
        time.sleep(2)
        
        copy_commands = [
            "if [ -d '/app/build' ]; then mkdir -p /output/static && cp -r /app/build/* /output/ && echo 'Copied CRA build files'; fi",
            
            "if [ -d '/app/build/static' ]; then cp -r /app/build/static /output/ && echo 'Explicitly copied static folder'; fi",
            
            "if [ -d '/app/dist' ]; then cp -r /app/dist/* /output/ && echo 'Copied Vite build files'; fi",
            
            "echo 'Output directory contents:' && ls -la /output/",
            
            "if [ -d '/output/static' ]; then echo 'Static directory found' && ls -la /output/static/; else echo 'No static directory'; fi",
            
            "if [ -d '/output/assets' ]; then echo 'Assets directory found' && ls -la /output/assets/; else echo 'No assets directory'; fi"
        ]
        
        exec_results = []
        for cmd in copy_commands:
            try:
                print(f"Executing Docker command: {cmd}")
                exec_result = container.exec_run(["sh", "-c", cmd])
                output = exec_result.output.decode()
                exec_results.append(output)
                print(f"Command output: {output}")
            except Exception as e:
                error_msg = f"Command failed: {str(e)}"
                exec_results.append(error_msg)
                print(error_msg)
        
        container.stop()
        container.remove()
        docker_client.images.remove(image_tag)
        
        log_messages = []
        for log in logs:
            if isinstance(log, dict) and 'stream' in log:
                log_messages.append(log['stream'].strip())
        
        if os.path.exists(build_output) and os.listdir(build_output):
            if os.path.exists(os.path.join(build_output, "index.html")):
                return {
                    "success": True,
                    "logs": log_messages + exec_results
                }
            else:
                return {
                    "success": False,
                    "error": "Build completed but no index.html was found",
                    "logs": log_messages + exec_results
                }
        else:
            return {
                "success": False,
                "error": "No build files were generated",
                "logs": log_messages + exec_results
            }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "logs": [f"Docker build failed: {str(e)}"]
        }