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
import threading
import time
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

# Track running backend containers
running_backend_containers = {}

def cleanup_container(container_id):
    """Clean up container from tracking after it stops"""
    if container_id in running_backend_containers:
        del running_backend_containers[container_id]

@project_router.get("/repos")
async def get_user_repos(request: Request):
    """Get all user's repositories without React detection"""
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        resp = await oauth.github.get('user/repos', token=token, params={
                    'page': 1,
                    'per_page': 100,
                    'sort': 'updated',  
                    'type': 'all'       
                })
        repos = resp.json()
        
        
        all_repos = []
        for repo in repos:
            repo_info = {
                "name": repo['name'],
                "full_name": repo['full_name'],
                "owner": repo['owner']['login'],
                "description": repo.get('description', ''),
                "clone_url": repo['clone_url'],
                "updated_at": repo['updated_at'],
                "private": repo.get('private', False),
                "language": repo.get('language', 'Unknown')
            }
            all_repos.append(repo_info)
        
        return {
            "repos": all_repos,
            "docker_available": docker_client is not None
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@project_router.get("/check-react/{owner}/{repo}")
async def check_if_react_project(request: Request, owner: str, repo: str):
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        headers = {'Authorization': f'token {token["access_token"]}'}
        
        # First check root level
        is_react_root = await check_react_in_directory(headers, owner, repo, "")
        if is_react_root["is_react"]:
            return {
                "is_react": True,
                "project_path": "",
                "package_json_path": is_react_root["package_json_path"],
                "details": is_react_root["details"]
            }
        
        # If not found at root, check subdirectories
        try:
            contents_url = f'https://api.github.com/repos/{owner}/{repo}/contents'
            contents_response = requests.get(contents_url, headers=headers)
            
            if contents_response.status_code == 200:
                contents = contents_response.json()
                
                # Check each directory in the root
                for item in contents:
                    if item['type'] == 'dir':
                        folder_name = item['name']
                        is_react_subfolder = await check_react_in_directory(headers, owner, repo, folder_name)
                        
                        if is_react_subfolder["is_react"]:
                            return {
                                "is_react": True,
                                "project_path": folder_name,
                                "package_json_path": is_react_subfolder["package_json_path"],
                                "details": is_react_subfolder["details"]
                            }
        except Exception as e:
            print(f"Error checking subdirectories: {str(e)}")
        
        return {
            "is_react": False,
            "project_path": None,
            "package_json_path": None,
            "details": "No React project found in root or subdirectories"
        }
        
    except Exception as e:
        return JSONResponse({
            "error": str(e),
            "is_react": False
        }, status_code=500)

async def check_react_in_directory(headers, owner: str, repo: str, directory_path: str):
    try:
        if directory_path:
            package_json_url = f'https://api.github.com/repos/{owner}/{repo}/contents/{directory_path}/package.json'
        else:
            package_json_url = f'https://api.github.com/repos/{owner}/{repo}/contents/package.json'
        
        response = requests.get(package_json_url, headers=headers)
        
        if response.status_code == 200:
            content = response.json()
            if content.get("encoding") == "base64":
                package_json = base64.b64decode(content['content']).decode('utf-8')
                package_data = json.loads(package_json)
                
                dependencies = package_data.get('dependencies', {})
                dev_dependencies = package_data.get('devDependencies', {})
                scripts = package_data.get('scripts', {})
                
                has_react = 'react' in dependencies or 'react' in dev_dependencies
                
                has_react_scripts = 'react-scripts' in dependencies or 'react-scripts' in dev_dependencies
                has_vite = 'vite' in dependencies or 'vite' in dev_dependencies
                has_build_script = 'build' in scripts
                has_start_script = 'start' in scripts
                
                project_type = "Unknown"
                if has_react_scripts:
                    project_type = "Create React App"
                elif has_vite and has_react:
                    project_type = "Vite + React"
                elif has_react:
                    project_type = "Custom React Setup"
                
                return {
                    "is_react": has_react,
                    "package_json_path": package_json_url,
                    "details": {
                        "project_type": project_type,
                        "has_react": has_react,
                        "has_react_scripts": has_react_scripts,
                        "has_vite": has_vite,
                        "has_build_script": has_build_script,
                        "has_start_script": has_start_script,
                        "dependencies": list(dependencies.keys()) if dependencies else [],
                        "dev_dependencies": list(dev_dependencies.keys()) if dev_dependencies else []
                    }
                }
        
        return {
            "is_react": False,
            "package_json_path": None,
            "details": "No package.json found or invalid format"
        }
    except Exception as e:
        return {
            "is_react": False,
            "package_json_path": None,
            "details": f"Error checking directory: {str(e)}"
        }

@project_router.get("/check-backend/{owner}/{repo}")
async def check_if_backend_project(request: Request, owner: str, repo: str):
    """Detect if repository contains Node.js or Python backend projects"""
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        headers = {'Authorization': f'token {token["access_token"]}'}
        
        # Check root level first
        backend_check_root = await check_backend_in_directory(headers, owner, repo, "")
        if backend_check_root["is_backend"]:
            return {
                "is_backend": True,
                "project_path": "",
                "backend_type": backend_check_root["backend_type"],
                "details": backend_check_root["details"]
            }
        
        # Check subdirectories
        try:
            contents_url = f'https://api.github.com/repos/{owner}/{repo}/contents'
            contents_response = requests.get(contents_url, headers=headers)
            
            if contents_response.status_code == 200:
                contents = contents_response.json()
                
                for item in contents:
                    if item['type'] == 'dir':
                        folder_name = item['name']
                        backend_check_sub = await check_backend_in_directory(headers, owner, repo, folder_name)
                        
                        if backend_check_sub["is_backend"]:
                            return {
                                "is_backend": True,
                                "project_path": folder_name,
                                "backend_type": backend_check_sub["backend_type"],
                                "details": backend_check_sub["details"]
                            }
        except Exception as e:
            print(f"Error checking subdirectories: {str(e)}")
        
        return {
            "is_backend": False,
            "project_path": None,
            "backend_type": None,
            "details": "No backend project found in root or subdirectories"
        }
        
    except Exception as e:
        return JSONResponse({
            "error": str(e),
            "is_backend": False
        }, status_code=500)

async def check_backend_in_directory(headers, owner: str, repo: str, directory_path: str):
    """Check if a directory contains a backend project (Node.js or Python)"""
    try:
        backend_info = {
            "is_backend": False,
            "backend_type": None,
            "details": {}
        }
        
        # Check for Node.js project
        if directory_path:
            package_json_url = f'https://api.github.com/repos/{owner}/{repo}/contents/{directory_path}/package.json'
        else:
            package_json_url = f'https://api.github.com/repos/{owner}/{repo}/contents/package.json'
        
        response = requests.get(package_json_url, headers=headers)
        if response.status_code == 200:
            content = response.json()
            if content.get("encoding") == "base64":
                package_json = base64.b64decode(content['content']).decode('utf-8')
                package_data = json.loads(package_json)
                
                dependencies = package_data.get('dependencies', {})
                dev_dependencies = package_data.get('devDependencies', {})
                scripts = package_data.get('scripts', {})
                
                # Check for backend frameworks
                is_express = 'express' in dependencies
                is_fastify = 'fastify' in dependencies
                is_koa = 'koa' in dependencies
                is_nestjs = '@nestjs/core' in dependencies
                has_start_script = 'start' in scripts or 'dev' in scripts
                
                if is_express or is_fastify or is_koa or is_nestjs or has_start_script:
                    framework = "Unknown"
                    if is_express:
                        framework = "Express.js"
                    elif is_fastify:
                        framework = "Fastify"
                    elif is_koa:
                        framework = "Koa"
                    elif is_nestjs:
                        framework = "NestJS"
                    elif has_start_script:
                        framework = "Node.js"
                    
                    backend_info = {
                        "is_backend": True,
                        "backend_type": "nodejs",
                        "details": {
                            "framework": framework,
                            "has_express": is_express,
                            "has_fastify": is_fastify,
                            "has_koa": is_koa,
                            "has_nestjs": is_nestjs,
                            "has_start_script": has_start_script,
                            "has_dev_script": 'dev' in scripts,
                            "scripts": list(scripts.keys()),
                            "dependencies": list(dependencies.keys())[:10]  # Limit for response size
                        }
                    }
                    return backend_info
        
        # Check for Python project
        python_files = ['requirements.txt', 'app.py', 'main.py', 'server.py', 'wsgi.py', 'asgi.py']
        for python_file in python_files:
            if directory_path:
                file_url = f'https://api.github.com/repos/{owner}/{repo}/contents/{directory_path}/{python_file}'
            else:
                file_url = f'https://api.github.com/repos/{owner}/{repo}/contents/{python_file}'
            
            response = requests.get(file_url, headers=headers)
            if response.status_code == 200:
                # Found a Python backend file
                framework = "Unknown"
                
                # Try to detect framework from requirements.txt
                if python_file == 'requirements.txt':
                    content = response.json()
                    if content.get("encoding") == "base64":
                        requirements = base64.b64decode(content['content']).decode('utf-8')
                        if 'fastapi' in requirements.lower():
                            framework = "FastAPI"
                        elif 'flask' in requirements.lower():
                            framework = "Flask"
                        elif 'django' in requirements.lower():
                            framework = "Django"
                        elif 'tornado' in requirements.lower():
                            framework = "Tornado"
                        else:
                            framework = "Python"
                elif python_file in ['app.py', 'main.py']:
                    framework = "Python"
                
                backend_info = {
                    "is_backend": True,
                    "backend_type": "python",
                    "details": {
                        "framework": framework,
                        "entry_file": python_file,
                        "has_requirements": python_file == 'requirements.txt' or 'requirements.txt' in [f for f in python_files]
                    }
                }
                return backend_info
        
        return backend_info
        
    except Exception as e:
        return {
            "is_backend": False,
            "backend_type": None,
            "details": f"Error checking directory: {str(e)}"
        }

@project_router.get("/repo-structure/{owner}/{repo}")
async def get_repo_structure(request: Request, owner: str, repo: str):
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        headers = {'Authorization': f'token {token["access_token"]}'}
        contents_url = f'https://api.github.com/repos/{owner}/{repo}/contents'
        contents_response = requests.get(contents_url, headers=headers)
        
        if contents_response.status_code != 200:
            return JSONResponse({
                "error": "Failed to fetch repository contents"
            }, status_code=400)
        
        contents = contents_response.json()
        structure = {
            "files": [],
            "directories": [],
            "has_package_json": False,
            "react_projects": [],
            "backend_projects": []
        }
        
        for item in contents:
            if item['type'] == 'file':
                structure["files"].append({
                    "name": item['name'],
                    "size": item.get('size', 0),
                    "path": item['name']
                })
                if item['name'] == 'package.json':
                    structure["has_package_json"] = True
            elif item['type'] == 'dir':
                structure["directories"].append({
                    "name": item['name'],
                    "path": item['name']
                })
        
        react_check_root = await check_react_in_directory(headers, owner, repo, "")
        if react_check_root["is_react"]:
            structure["react_projects"].append({
                "path": "",
                "location": "Root directory",
                "details": react_check_root["details"]
            })
        
        # Check for backend projects in root
        backend_check_root = await check_backend_in_directory(headers, owner, repo, "")
        if backend_check_root["is_backend"]:
            structure["backend_projects"].append({
                "path": "",
                "location": "Root directory",
                "backend_type": backend_check_root["backend_type"],
                "details": backend_check_root["details"]
            })
        
        for directory in structure["directories"]:
            react_check_sub = await check_react_in_directory(headers, owner, repo, directory["name"])
            if react_check_sub["is_react"]:
                structure["react_projects"].append({
                    "path": directory["name"],
                    "location": f"Subdirectory: {directory['name']}",
                    "details": react_check_sub["details"]
                })
            
            # Check subdirectories for backend projects
            backend_check_sub = await check_backend_in_directory(headers, owner, repo, directory["name"])
            if backend_check_sub["is_backend"]:
                structure["backend_projects"].append({
                    "path": directory["name"],
                    "location": f"Subdirectory: {directory['name']}",
                    "backend_type": backend_check_sub["backend_type"],
                    "details": backend_check_sub["details"]
                })
        
        return {
            "owner": owner,
            "repo": repo,
            "structure": structure,
            "total_react_projects": len(structure["react_projects"]),
            "total_backend_projects": len(structure["backend_projects"])
        }
        
    except Exception as e:
        return JSONResponse({
            "error": str(e)
        }, status_code=500)
        
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
    
   
    react_check = await check_if_react_project(request, owner, repo)
    if not react_check["is_react"]:
        return JSONResponse({
            "success": False,
            "error": "This project is not a React project"
        }, status_code=400)
    
    project_path = react_check.get("project_path", "")
    
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
            
            repo_base_path = os.path.join(extract_path, extracted_folders[0])
            
            if project_path:
                repo_path = os.path.join(repo_base_path, project_path)
                print(f"React project found in subdirectory: {project_path}")
            else:
                repo_path = repo_base_path
                print("React project found in root directory")
            
            if not os.path.exists(repo_path):
                return JSONResponse({
                    "success": False,
                    "error": f"Project path not found: {project_path}"
                }, status_code=400)
            
         
            validation = await validate_react_project(repo_path)
            if not validation["valid"]:
                return JSONResponse({
                    "success": False,
                    "error": validation["error"],
                    "details": validation.get("details", ""),
                    "suggestion": validation.get("suggestion", "")
                }, status_code=400)
            
            print(f"Project validation passed: {validation['project_type']}")
            
            await fix_node_compatibility_issues(repo_path)
            
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
                
                s3_prefix = f"projects/{owner}/{repo}"
                print(f"Starting S3 upload from {s3_source_folder} to {s3_prefix}")
                
                # Configure S3 for SPA routing BEFORE uploading
                await configure_s3_for_spa_routing()
                
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

@project_router.post("/run-backend/{owner}/{repo}")
async def run_backend_project(request: Request, owner: str, repo: str):
    """Run a backend project (Node.js or Python) in a Docker container"""
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    if not docker_client:
        return JSONResponse({
            "success": False,
            "error": "Docker Desktop needs to be installed and running"
        }, status_code=400)
    
    # Check if it's a backend project
    backend_check = await check_if_backend_project(request, owner, repo)
    if not backend_check["is_backend"]:
        return JSONResponse({
            "success": False,
            "error": "This project is not a backend project"
        }, status_code=400)
    
    project_path = backend_check.get("project_path", "")
    backend_type = backend_check["backend_type"]
    
    # Check if already running
    container_key = f"{owner}_{repo}"
    if container_key in running_backend_containers:
        container_info = running_backend_containers[container_key]
        try:
            container = docker_client.containers.get(container_info["container_id"])
            if container.status == "running":
                return {
                    "success": True,
                    "message": "Backend is already running",
                    "container_id": container_info["container_id"],
                    "local_url": container_info["local_url"],
                    "port": container_info["port"],
                    "backend_type": backend_type
                }
        except:
            # Container doesn't exist anymore, remove from tracking
            del running_backend_containers[container_key]
    
    try:
        # Download and extract repository
        headers = {'Authorization': f'token {token["access_token"]}'}
        zip_url = f'https://api.github.com/repos/{owner}/{repo}/zipball'
        
        response = requests.get(zip_url, headers=headers)
        if response.status_code != 200:
            return JSONResponse({"success": False, "error": "Failed to download repository"}, status_code=400)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, f"{repo}.zip")
            extract_path = os.path.join(temp_dir, "extracted")
            
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            
            extracted_folders = os.listdir(extract_path)
            if not extracted_folders:
                return JSONResponse({"success": False, "error": "No files extracted"}, status_code=400)
            
            repo_base_path = os.path.join(extract_path, extracted_folders[0])
            
            if project_path:
                repo_path = os.path.join(repo_base_path, project_path)
            else:
                repo_path = repo_base_path
            
            if not os.path.exists(repo_path):
                return JSONResponse({
                    "success": False,
                    "error": f"Project path not found: {project_path}"
                }, status_code=400)
            
            # Find available port
            import socket
            def find_free_port():
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('', 0))
                    s.listen(1)
                    port = s.getsockname()[1]
                return port
            
            port = find_free_port()
            
            # Run the appropriate container
            if backend_type == "nodejs":
                container = await run_nodejs_container(repo_path, port, owner, repo)
            elif backend_type == "python":
                container = await run_python_container(repo_path, port, owner, repo)
            else:
                return JSONResponse({
                    "success": False,
                    "error": f"Unsupported backend type: {backend_type}"
                }, status_code=400)
            
            if container:
                local_url = f"http://localhost:{port}"
                
                # Track the running container
                running_backend_containers[container_key] = {
                    "container_id": container.id,
                    "port": port,
                    "local_url": local_url,
                    "backend_type": backend_type,
                    "owner": owner,
                    "repo": repo,
                    "started_at": time.time()
                }
                
                # Start a thread to monitor container status
                def monitor_container():
                    try:
                        container.wait()
                    except:
                        pass
                    finally:
                        cleanup_container(container.id)
                
                threading.Thread(target=monitor_container, daemon=True).start()
                
                return {
                    "success": True,
                    "message": f"Backend {owner}/{repo} is now running",
                    "container_id": container.id,
                    "local_url": local_url,
                    "port": port,
                    "backend_type": backend_type
                }
            else:
                return JSONResponse({
                    "success": False,
                    "error": "Failed to start container"
                }, status_code=500)
                
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@project_router.get("/backend-status")
async def get_running_backends(request: Request):
    """Get status of all running backend containers"""
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    running_backends = []
    containers_to_remove = []
    
    for container_key, container_info in running_backend_containers.items():
        try:
            container = docker_client.containers.get(container_info["container_id"])
            running_backends.append({
                "owner": container_info["owner"],
                "repo": container_info["repo"],
                "container_id": container_info["container_id"],
                "local_url": container_info["local_url"],
                "port": container_info["port"],
                "backend_type": container_info["backend_type"],
                "status": container.status,
                "started_at": container_info["started_at"],
                "uptime": time.time() - container_info["started_at"]
            })
        except:
            # Container doesn't exist anymore
            containers_to_remove.append(container_key)
    
    # Clean up non-existent containers
    for key in containers_to_remove:
        del running_backend_containers[key]
    
    return {
        "running_backends": running_backends,
        "total_running": len(running_backends)
    }

@project_router.delete("/stop-backend/{owner}/{repo}")
async def stop_backend_project(request: Request, owner: str, repo: str):
    """Stop a running backend container"""
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    container_key = f"{owner}_{repo}"
    
    if container_key not in running_backend_containers:
        return JSONResponse({
            "success": False,
            "error": "Backend is not running"
        }, status_code=404)
    
    try:
        container_info = running_backend_containers[container_key]
        container = docker_client.containers.get(container_info["container_id"])
        container.stop(timeout=10)
        container.remove()
        
        del running_backend_containers[container_key]
        
        return {
            "success": True,
            "message": f"Backend {owner}/{repo} stopped successfully"
        }
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@project_router.get("/backend-logs/{owner}/{repo}")
async def get_backend_logs(request: Request, owner: str, repo: str):
    """Get logs from a running backend container"""
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    container_key = f"{owner}_{repo}"
    
    if container_key not in running_backend_containers:
        return JSONResponse({
            "success": False,
            "error": "Backend is not running"
        }, status_code=404)
    
    try:
        container_info = running_backend_containers[container_key]
        container = docker_client.containers.get(container_info["container_id"])
        
        logs = container.logs(tail=100).decode('utf-8')
        
        return {
            "success": True,
            "logs": logs.split('\n'),
            "container_id": container_info["container_id"],
            "backend_type": container_info["backend_type"]
        }
        
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
                    extra_args = {
                        "ContentType": content_type
                    }
                    
                    if lower_file.endswith((".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2")):
                        extra_args["CacheControl"] = "public, max-age=31536000"  # 1 year for assets
                    elif lower_file.endswith(".html"):
                        extra_args["CacheControl"] = "public, max-age=0, must-revalidate"  # No cache for HTML
                    
                    s3.upload_file(
                        local_path, 
                        bucket, 
                        s3_key, 
                        ExtraArgs=extra_args
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
    """Simple React project check - now just calls the deeper check function"""
    react_check = await check_if_react_project(request, owner, repo)
    return react_check.get("is_react", False)

async def fix_node_compatibility_issues(repo_path):
    """Fix Node.js compatibility issues for modern React projects"""
    package_json_path = os.path.join(repo_path, "package.json")
    if not os.path.exists(package_json_path):
        return False
    
    try:
        with open(package_json_path, 'r', encoding='utf-8') as f:
            package_data = json.load(f)
        
        dependencies = package_data.get('dependencies', {})
        dev_dependencies = package_data.get('devDependencies', {})
        
        # Check if using problematic Vite version
        vite_version = dev_dependencies.get('vite', dependencies.get('vite', ''))
        
        changes_made = []
        
        # If using Vite 7.x which requires Node 20+, add engine requirements
        if vite_version and ('7.' in vite_version or '^7' in vite_version):
            if 'engines' not in package_data:
                package_data['engines'] = {}
            package_data['engines']['node'] = '>=20.0.0'
            changes_made.append("Added Node.js engine requirement")
        
        # Add legacy-peer-deps option for npm compatibility
        if 'npmrc' not in package_data:
            npmrc_path = os.path.join(repo_path, '.npmrc')
            with open(npmrc_path, 'w') as f:
                f.write("legacy-peer-deps=true\n")
                f.write("fund=false\n")
            changes_made.append("Created .npmrc for compatibility")
        
        if changes_made:
            with open(package_json_path, 'w', encoding='utf-8') as f:
                json.dump(package_data, f, indent=2)
            
            print(f"✅ Fixed Node compatibility - Changes: {changes_made}")
        
        return True
        
    except Exception as e:
        print(f"Error fixing Node compatibility: {str(e)}")
        return False

async def configure_s3_for_spa_routing():
    """Configure S3 bucket for SPA routing - crucial for React Router"""
    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME]):
        print("S3 credentials not configured")
        return False
        
    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION,
        )
        
        # Configure website with SPA routing - ERROR DOCUMENT IS KEY!
        website_configuration = {
            'ErrorDocument': {'Key': 'index.html'},  # This makes /about redirect to index.html
            'IndexDocument': {'Suffix': 'index.html'},
        }
        
        s3.put_bucket_website(
            Bucket=S3_BUCKET_NAME,
            WebsiteConfiguration=website_configuration
        )
        
        print("✅ Configured S3 for SPA routing (404 -> index.html)")
        return True
        
    except Exception as e:
        print(f"Error configuring S3 for SPA: {str(e)}")
        return False


async def run_nodejs_container(repo_path: str, port: int, owner: str, repo: str):
   
    try:
        abs_repo_path = os.path.abspath(repo_path)
        
        # Detect the start command
        package_json_path = os.path.join(repo_path, "package.json")
        start_command = "npm start"
        
        if os.path.exists(package_json_path):
            with open(package_json_path, 'r', encoding='utf-8') as f:
                package_data = json.load(f)
                scripts = package_data.get('scripts', {})
                
                if 'dev' in scripts:
                    start_command = "npm run dev"
                elif 'start' in scripts:
                    start_command = "npm start"
                else:
                    start_command = "node index.js"  # fallback
        
        # Docker command to run Node.js app
        run_command = f"""
        set -e
        echo "🚀 Starting Node.js backend..."
        echo "Installing dependencies..."
        npm install --production
        echo "Starting application with: {start_command}"
        {start_command}
        """
        
        container = docker_client.containers.run(
            "node:18-alpine",
            command=["sh", "-c", run_command],
            volumes={abs_repo_path: {'bind': '/app', 'mode': 'ro'}},
            working_dir='/app',
            ports={f'{port}/tcp': port},
            environment={
                'NODE_ENV': 'development',
                'PORT': str(port)
            },
            detach=True,
            
            name=f"backend_{owner}_{repo}_{port}"
        )
        
        print(f"✅ Started Node.js container {container.id} on port {port}")
        return container
        
    except Exception as e:
        print(f"❌ Error starting Node.js container: {str(e)}")
        return None

async def run_python_container(repo_path: str, port: int, owner: str, repo: str):
    """Run Python backend in Docker container"""
    try:
        abs_repo_path = os.path.abspath(repo_path)
        
        # Detect Python entry point and framework
        start_command = "python app.py"
        
        # Check for common Python entry files
        if os.path.exists(os.path.join(repo_path, "main.py")):
            start_command = "python main.py"
        elif os.path.exists(os.path.join(repo_path, "server.py")):
            start_command = "python server.py"
        elif os.path.exists(os.path.join(repo_path, "app.py")):
            start_command = "python app.py"
        elif os.path.exists(os.path.join(repo_path, "wsgi.py")):
            start_command = "gunicorn wsgi:app --bind 0.0.0.0:8000"
        elif os.path.exists(os.path.join(repo_path, "asgi.py")):
            start_command = "uvicorn asgi:app --host 0.0.0.0 --port 8000"
        
        # Check requirements.txt for framework detection
        requirements_path = os.path.join(repo_path, "requirements.txt")
        if os.path.exists(requirements_path):
            with open(requirements_path, 'r') as f:
                requirements = f.read().lower()
                if 'fastapi' in requirements:
                    if os.path.exists(os.path.join(repo_path, "main.py")):
                        start_command = f"uvicorn main:app --host 0.0.0.0 --port {port} --reload"
                    elif os.path.exists(os.path.join(repo_path, "app.py")):
                        start_command = f"uvicorn app:app --host 0.0.0.0 --port {port} --reload"
                elif 'flask' in requirements:
                    start_command = f"python -m flask run --host 0.0.0.0 --port {port}"
                elif 'django' in requirements:
                    start_command = f"python manage.py runserver 0.0.0.0:{port}"
        
        # Docker command to run Python app
        run_command = f"""
        set -e
        echo "🐍 Starting Python backend..."
        echo "Installing dependencies..."
        if [ -f requirements.txt ]; then
            pip install -r requirements.txt
        else
            echo "No requirements.txt found, proceeding without dependencies"
        fi
        echo "Starting application with: {start_command}"
        {start_command}
        """
        
        container = docker_client.containers.run(
            "python:3.11-alpine",
            command=["sh", "-c", run_command],
            volumes={abs_repo_path: {'bind': '/app', 'mode': 'ro'}},
            working_dir='/app',
            ports={f'{port}/tcp': port},
            environment={
                'PYTHONPATH': '/app',
                'FLASK_ENV': 'development',
                'FLASK_APP': 'app.py'
            },
            detach=True,
            remove=True,
            name=f"backend_{owner}_{repo}_{port}"
        )
        
        print(f"✅ Started Python container {container.id} on port {port}")
        return container
        
    except Exception as e:
        print(f"❌ Error starting Python container: {str(e)}")
        return None

async def validate_react_project(repo_path: str):
    """Validate React project before building"""
    try:
        package_json_path = os.path.join(repo_path, "package.json")
        
        if not os.path.exists(package_json_path):
            return {
                "valid": False,
                "error": "package.json not found",
                "details": "This directory does not contain a package.json file"
            }
        
        with open(package_json_path, 'r', encoding='utf-8') as f:
            package_data = json.load(f)
        
        dependencies = package_data.get('dependencies', {})
        dev_dependencies = package_data.get('devDependencies', {})
        scripts = package_data.get('scripts', {})
        
        has_react = 'react' in dependencies or 'react' in dev_dependencies
        if not has_react:
            return {
                "valid": False,
                "error": "Not a React project",
                "details": "No React dependency found in package.json"
            }
        
        if 'build' not in scripts:
            return {
                "valid": False,
                "error": "No build script found",
                "details": f"Available scripts: {list(scripts.keys())}",
                "suggestion": "Add a 'build' script to package.json"
            }
        
        project_type = "Unknown"
        if 'react-scripts' in dependencies or 'react-scripts' in dev_dependencies:
            project_type = "Create React App"
        elif 'vite' in dependencies or 'vite' in dev_dependencies:
            project_type = "Vite + React"
        elif '@vitejs/plugin-react' in dev_dependencies:
            project_type = "Vite + React"
        
        return {
            "valid": True,
            "project_type": project_type,
            "build_script": scripts.get('build', ''),
            "has_start_script": 'start' in scripts,
            "dependencies_count": len(dependencies),
            "dev_dependencies_count": len(dev_dependencies)
        }
        
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "error": "Invalid package.json",
            "details": f"JSON parsing error: {str(e)}"
        }
    except Exception as e:
        return {
            "valid": False,
            "error": "Validation failed",
            "details": str(e)
        }
async def build_react_in_docker(repo_path: str, build_output: str, owner: str, repo: str):
    if not docker_client:
        return {
            "success": False,
            "error": "Docker not available",
            "logs": ["Docker Desktop is not running"]
        }
    
    try:
        abs_build_output = os.path.abspath(build_output)
        abs_repo_path = os.path.abspath(repo_path)
        
        build_command = [
            "sh", "-c", 
            """
            set -e
            echo "🚀 Starting React build process..."
            echo "Copying project files to writable location..."
            cp -r /source/* /app/
            
            echo "📋 Analyzing project structure..."
            ls -la /app/
            
            echo "📦 Installing dependencies..."
            npm install --verbose 2>&1 || {
                echo "❌ npm install failed!"
                echo "Package.json content:"
                cat package.json
                echo "Node version:"
                node --version
                echo "NPM version:"
                npm --version
                exit 1
            }
            
            echo "🔍 Checking for required files..."
            if [ ! -f package.json ]; then
                echo "❌ No package.json found"
                exit 1
            fi
            
            if [ ! -d src ]; then
                echo "⚠️  Warning: No src directory found"
                ls -la
            fi
            
            if [ ! -d public ]; then
                echo "⚠️  Warning: No public directory found"
                ls -la
            fi
            
            echo "🏗️  Building React app..."
            npm run build --verbose 2>&1
            BUILD_EXIT_CODE=$?
            
            if [ $BUILD_EXIT_CODE -ne 0 ]; then
                echo "❌ Build failed! Debugging..."
                echo "Node version check:"
                node --version
                echo "Package.json scripts:"
                cat package.json | grep -A 10 '"scripts"' || echo "No scripts section found"
                echo "Available files:"
                find . -name "*.js" -o -name "*.jsx" -o -name "*.ts" -o -name "*.tsx" | head -10
                exit 1
            fi
            
            echo "✅ Build completed, checking output..."
            
            # Find the build directory
            BUILD_DIR=""
            if [ -d build ]; then
                BUILD_DIR="build"
                echo "📁 Found build directory"
            elif [ -d dist ]; then
                BUILD_DIR="dist"
                echo "📁 Found dist directory"
            else
                echo "❌ No build directory found!"
                echo "Available directories:"
                ls -la
                exit 1
            fi
            
            echo "📊 Build directory contents:"
            ls -la "$BUILD_DIR"
            
            # Validate critical files
            if [ ! -f "$BUILD_DIR/index.html" ]; then
                echo "❌ No index.html found in build!"
                exit 1
            fi
            
            # Check index.html size
            INDEX_SIZE=$(wc -c < "$BUILD_DIR/index.html")
            echo "📄 index.html size: $INDEX_SIZE bytes"
            
            if [ "$INDEX_SIZE" -lt 100 ]; then
                echo "⚠️  WARNING: index.html is very small!"
                echo "Content preview:"
                head -5 "$BUILD_DIR/index.html"
            fi
            
            # Check for React root div
            if grep -q 'id="root"' "$BUILD_DIR/index.html" || grep -q "id='root'" "$BUILD_DIR/index.html"; then
                echo "✅ React root div found"
            else
                echo "⚠️  WARNING: No React root div found in index.html"
                echo "Index.html content:"
                cat "$BUILD_DIR/index.html"
            fi
            
            # Check for script tags
            SCRIPT_COUNT=$(grep -c '<script' "$BUILD_DIR/index.html" || echo "0")
            echo "📜 Script tags found: $SCRIPT_COUNT"
            
            if [ "$SCRIPT_COUNT" -eq 0 ]; then
                echo "⚠️  WARNING: No script tags found in index.html"
            fi
            
            echo "📦 Copying build files to output..."
            cp -r "$BUILD_DIR"/* /output/
            
            echo "✅ SUCCESS: Build completed and files copied"
            echo "📊 Final output contents:"
            ls -la /output/
            """
        ]
        
        # Run the build in Node.js container
        container = docker_client.containers.run(
            "node:20-alpine",  # Use Node 20 for compatibility with latest Vite
            command=build_command,
            volumes={
                abs_repo_path: {'bind': '/source', 'mode': 'ro'},    # React project source (read-only)
                abs_build_output: {'bind': '/output', 'mode': 'rw'}  # Build output (writable)
            },
            working_dir='/app',
            remove=True,  # Auto-remove when done
            detach=True
        )
        
        # Wait for completion and get logs
        result = container.wait()
        logs = container.logs().decode('utf-8')
        
        # Enhanced success validation
        build_success = (
            result['StatusCode'] == 0 and 
            os.path.exists(build_output) and 
            os.path.exists(os.path.join(build_output, "index.html"))
        )
        
        # Additional validation for blank page prevention
        if build_success:
            index_path = os.path.join(build_output, "index.html")
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    index_content = f.read()
                
                # Check for common blank page issues
                if len(index_content.strip()) < 100:
                    build_success = False
                    logs += "\n❌ VALIDATION FAILED: index.html is too small"
                
                if 'id="root"' not in index_content and "id='root'" not in index_content:
                    logs += "\n⚠️  WARNING: No React root div found"
                
                if '<script' not in index_content:
                    build_success = False
                    logs += "\n❌ VALIDATION FAILED: No script tags found in index.html"
                    
            except Exception as e:
                logs += f"\n⚠️  Could not validate index.html: {str(e)}"
        
        return {
            "success": build_success,
            "error": None if build_success else f"Build failed (exit code: {result['StatusCode']})",
            "logs": logs.split('\n')
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "logs": [f"Docker error: {str(e)}"]
        }