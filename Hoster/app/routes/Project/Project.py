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
    """Check if a specific repository is a React project with deep scanning"""
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
            "react_projects": []
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
        
        for directory in structure["directories"]:
            react_check_sub = await check_react_in_directory(headers, owner, repo, directory["name"])
            if react_check_sub["is_react"]:
                structure["react_projects"].append({
                    "path": directory["name"],
                    "location": f"Subdirectory: {directory['name']}",
                    "details": react_check_sub["details"]
                })
        
        return {
            "owner": owner,
            "repo": repo,
            "structure": structure,
            "total_react_projects": len(structure["react_projects"])
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

@project_router.get("/validate/{owner}/{repo}")
async def validate_repository_for_build(request: Request, owner: str, repo: str):
    """Validate a repository before building to help debug issues"""
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    try:
        # First check if it's a React project
        react_check = await check_if_react_project(request, owner, repo)
        if not react_check["is_react"]:
            return {
                "valid": False,
                "error": "Not a React project",
                "react_check": react_check
            }
        
        # Download and validate the actual project
        headers = {'Authorization': f'token {token["access_token"]}'}
        
        # Get package.json content
        project_path = react_check.get("project_path", "")
        if project_path:
            package_json_url = f'https://api.github.com/repos/{owner}/{repo}/contents/{project_path}/package.json'
        else:
            package_json_url = f'https://api.github.com/repos/{owner}/{repo}/contents/package.json'
        
        response = requests.get(package_json_url, headers=headers)
        if response.status_code != 200:
            return JSONResponse({
                "valid": False,
                "error": "Could not fetch package.json"
            }, status_code=400)
        
        content = response.json()
        if content.get("encoding") == "base64":
            package_json_content = base64.b64decode(content['content']).decode('utf-8')
            package_data = json.loads(package_json_content)
            
            dependencies = package_data.get('dependencies', {})
            dev_dependencies = package_data.get('devDependencies', {})
            scripts = package_data.get('scripts', {})
            
            # Detailed validation
            validation_results = {
                "valid": True,
                "project_path": project_path,
                "package_json_url": package_json_url,
                "react_check": react_check,
                "validation": {
                    "has_react": 'react' in dependencies or 'react' in dev_dependencies,
                    "has_build_script": 'build' in scripts,
                    "has_start_script": 'start' in scripts,
                    "build_script": scripts.get('build', 'Not found'),
                    "start_script": scripts.get('start', 'Not found'),
                    "project_type": react_check.get("details", {}).get("project_type", "Unknown"),
                    "dependencies": list(dependencies.keys())[:10],
                    "dev_dependencies": list(dev_dependencies.keys())[:10],
                    "total_dependencies": len(dependencies),
                    "total_dev_dependencies": len(dev_dependencies)
                },
                "warnings": [],
                "recommendations": []
            }
            
            # Add warnings and recommendations
            if 'build' not in scripts:
                validation_results["valid"] = False
                validation_results["warnings"].append("No build script found in package.json")
                validation_results["recommendations"].append("Add a build script to package.json")
            
            if len(dependencies) == 0:
                validation_results["warnings"].append("No dependencies found")
                validation_results["recommendations"].append("Ensure all required dependencies are listed")
            
            if 'react' not in dependencies and 'react' not in dev_dependencies:
                validation_results["valid"] = False
                validation_results["warnings"].append("React not found in dependencies")
            
            return validation_results
        
        return JSONResponse({
            "valid": False,
            "error": "Could not decode package.json content"
        }, status_code=400)
        
    except Exception as e:
        return JSONResponse({
            "valid": False,
            "error": str(e)
        }, status_code=500)

@project_router.post("/test-build/{owner}/{repo}")
async def test_build_repository(request: Request, owner: str, repo: str):
    """Test build with enhanced debugging - downloads and validates without full Docker build"""
    token = request.session.get('token')
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    # Check if it's a React project first
    react_check = await check_if_react_project(request, owner, repo)
    if not react_check["is_react"]:
        return JSONResponse({
            "success": False,
            "error": "Not a React project",
            "react_check": react_check
        }, status_code=400)
    
    project_path = react_check.get("project_path", "")
    
    try:
        headers = {'Authorization': f'token {token["access_token"]}'}
        zip_url = f'https://api.github.com/repos/{owner}/{repo}/zipball'
        
        response = requests.get(zip_url, headers=headers)
        if response.status_code != 200:
            return JSONResponse({
                "success": False, 
                "error": "Failed to download repository"
            }, status_code=400)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, f"{repo}.zip")
            extract_path = os.path.join(temp_dir, "extracted")
            
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            
            extracted_folders = os.listdir(extract_path)
            if not extracted_folders:
                return JSONResponse({
                    "success": False, 
                    "error": "No files extracted"
                }, status_code=400)
            
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
            
            # Detailed analysis
            analysis = {
                "repository": f"{owner}/{repo}",
                "project_path": project_path or "root",
                "react_check": react_check,
                "validation": {},
                "file_structure": {},
                "package_analysis": {},
                "potential_issues": [],
                "recommendations": []
            }
            
            # Validate React project
            validation = await validate_react_project(repo_path)
            analysis["validation"] = validation
            
            # Analyze file structure
            analysis["file_structure"] = {
                "has_src": os.path.exists(os.path.join(repo_path, "src")),
                "has_public": os.path.exists(os.path.join(repo_path, "public")),
                "has_index_html": os.path.exists(os.path.join(repo_path, "public", "index.html")),
                "has_tsconfig": os.path.exists(os.path.join(repo_path, "tsconfig.json")),
                "has_eslint": any(os.path.exists(os.path.join(repo_path, f)) for f in [".eslintrc.js", ".eslintrc.json", ".eslintrc.yaml"]),
                "has_gitignore": os.path.exists(os.path.join(repo_path, ".gitignore")),
                "root_files": os.listdir(repo_path) if os.path.exists(repo_path) else []
            }
            
            # Check for entry points
            entry_points = []
            for entry in ["src/index.js", "src/index.tsx", "src/index.ts", "src/main.js", "src/main.tsx", "src/App.js", "src/App.tsx"]:
                if os.path.exists(os.path.join(repo_path, entry)):
                    entry_points.append(entry)
            analysis["file_structure"]["entry_points"] = entry_points
            
            # Analyze package.json in detail
            package_json_path = os.path.join(repo_path, "package.json")
            if os.path.exists(package_json_path):
                try:
                    with open(package_json_path, 'r', encoding='utf-8') as f:
                        package_data = json.load(f)
                    
                    dependencies = package_data.get('dependencies', {})
                    dev_dependencies = package_data.get('devDependencies', {})
                    scripts = package_data.get('scripts', {})
                    
                    analysis["package_analysis"] = {
                        "name": package_data.get('name', 'unknown'),
                        "version": package_data.get('version', 'unknown'),
                        "main": package_data.get('main', ''),
                        "homepage": package_data.get('homepage', ''),
                        "scripts": scripts,
                        "dependencies": dependencies,
                        "dev_dependencies": dev_dependencies,
                        "react_version": dependencies.get('react', dev_dependencies.get('react', 'not found')),
                        "typescript": '@types/react' in dev_dependencies or 'typescript' in dev_dependencies,
                        "build_tools": {
                            "react_scripts": 'react-scripts' in dependencies or 'react-scripts' in dev_dependencies,
                            "vite": 'vite' in dependencies or 'vite' in dev_dependencies,
                            "webpack": 'webpack' in dependencies or 'webpack' in dev_dependencies,
                            "parcel": 'parcel' in dependencies or 'parcel' in dev_dependencies
                        }
                    }
                    
                    # Check for potential issues
                    if not analysis["file_structure"]["has_src"]:
                        analysis["potential_issues"].append("No 'src' directory found")
                        analysis["recommendations"].append("Ensure your React source code is in a 'src' directory")
                    
                    if not analysis["file_structure"]["entry_points"]:
                        analysis["potential_issues"].append("No main entry point found")
                        analysis["recommendations"].append("Create src/index.js or src/index.tsx as your main entry point")
                    
                    if not analysis["file_structure"]["has_public"]:
                        analysis["potential_issues"].append("No 'public' directory found")
                        analysis["recommendations"].append("Create a 'public' directory with index.html")
                    
                    if not analysis["file_structure"]["has_index_html"]:
                        analysis["potential_issues"].append("No index.html found in public directory")
                        analysis["recommendations"].append("Add index.html to your public directory")
                    
                    if 'build' not in scripts:
                        analysis["potential_issues"].append("No build script in package.json")
                        analysis["recommendations"].append("Add a build script to package.json")
                    
                    if len(dependencies) == 0:
                        analysis["potential_issues"].append("No dependencies found")
                        analysis["recommendations"].append("Install React and other required dependencies")
                    
                    # Check for version conflicts
                    if 'react' in dependencies:
                        react_version = dependencies['react']
                        if '^18' not in react_version and '^17' not in react_version and '^16' not in react_version:
                            analysis["potential_issues"].append(f"Unusual React version: {react_version}")
                    
                except Exception as e:
                    analysis["potential_issues"].append(f"Error reading package.json: {str(e)}")
            
            return {
                "success": True,
                "analysis": analysis,
                "ready_to_build": len(analysis["potential_issues"]) == 0,
                "issue_count": len(analysis["potential_issues"])
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
            
            await modify_package_json_for_relative_paths(repo_path)
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
                    
                    await fix_index_html_paths(s3_source_folder)
                
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


@project_router.get("/debug-blank-page/{owner}/{repo}")
async def debug_blank_page_issue(request: Request, owner: str, repo: str):
    """Debug why a deployed React app shows a blank page"""
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
        
        # Get all files
        response = s3.list_objects_v2(
            Bucket=S3_BUCKET_NAME,
            Prefix=s3_prefix
        )
        
        debug_info = {
            "owner": owner,
            "repo": repo,
            "s3_prefix": s3_prefix,
            "issues_found": [],
            "recommendations": [],
            "files_analysis": {},
            "index_html_analysis": {},
            "static_files_analysis": {}
        }
        
        if 'Contents' not in response:
            debug_info["issues_found"].append("No files found in S3")
            debug_info["recommendations"].append("Build and deploy the project first")
            return debug_info
        
        files = response['Contents']
        file_keys = [item['Key'] for item in files]
        
        # Check for index.html
        index_key = f"{s3_prefix}/index.html"
        has_index = index_key in file_keys
        
        if not has_index:
            debug_info["issues_found"].append("No index.html found in S3")
            debug_info["recommendations"].append("Ensure your React build creates an index.html file")
        else:
            # Analyze index.html content
            try:
                index_obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=index_key)
                index_content = index_obj['Body'].read().decode('utf-8')
                
                debug_info["index_html_analysis"] = {
                    "size": len(index_content),
                    "content_type": index_obj.get('ContentType', 'unknown'),
                    "has_react_root": 'id="root"' in index_content or "id='root'" in index_content,
                    "has_scripts": '<script' in index_content,
                    "has_stylesheets": '<link' in index_content and 'stylesheet' in index_content,
                    "preview": index_content[:300] + "..." if len(index_content) > 300 else index_content,
                    "absolute_paths_count": index_content.count('="/')
                }
                
                if len(index_content.strip()) < 100:
                    debug_info["issues_found"].append("index.html is very small - possibly corrupted")
                    debug_info["recommendations"].append("Rebuild the project - the build may have failed")
                
                if not debug_info["index_html_analysis"]["has_react_root"]:
                    debug_info["issues_found"].append("No React root div found in index.html")
                    debug_info["recommendations"].append("Ensure your index.html has <div id='root'></div>")
                
                if not debug_info["index_html_analysis"]["has_scripts"]:
                    debug_info["issues_found"].append("No JavaScript files linked in index.html")
                    debug_info["recommendations"].append("React build should include script tags for JS bundles")
                
                if debug_info["index_html_analysis"]["absolute_paths_count"] > 0:
                    debug_info["issues_found"].append(f"Found {debug_info['index_html_analysis']['absolute_paths_count']} absolute paths in index.html")
                    debug_info["recommendations"].append("Fix absolute paths to relative paths for S3 hosting")
                
            except Exception as e:
                debug_info["issues_found"].append(f"Could not read index.html content: {str(e)}")
        
        # Check for static/assets folders
        static_files = [key for key in file_keys if '/static/' in key or '/assets/' in key]
        js_files = [key for key in file_keys if key.endswith('.js')]
        css_files = [key for key in file_keys if key.endswith('.css')]
        
        debug_info["static_files_analysis"] = {
            "static_files_count": len(static_files),
            "js_files_count": len(js_files),
            "css_files_count": len(css_files),
            "js_files": js_files[:5],  # Show first 5
            "css_files": css_files[:5]  # Show first 5
        }
        
        if len(js_files) == 0:
            debug_info["issues_found"].append("No JavaScript files found")
            debug_info["recommendations"].append("React build should create JS bundle files")
        
        if len(css_files) == 0:
            debug_info["issues_found"].append("No CSS files found")
            debug_info["recommendations"].append("Consider if your app should have CSS files")
        
        # Check S3 website configuration
        try:
            website_config = s3.get_bucket_website(Bucket=S3_BUCKET_NAME)
            debug_info["s3_website_config"] = website_config
            
            error_doc = website_config.get('ErrorDocument', {}).get('Key')
            if error_doc != 'index.html':
                debug_info["issues_found"].append(f"S3 ErrorDocument is '{error_doc}', should be 'index.html' for SPA routing")
                debug_info["recommendations"].append("Configure S3 ErrorDocument to 'index.html' for React Router")
                
        except Exception as e:
            debug_info["issues_found"].append("S3 bucket not configured for website hosting")
            debug_info["recommendations"].append("Enable S3 static website hosting with ErrorDocument=index.html")
        
        # Generate S3 URLs for testing
        s3_base_url = f"{S3_BASE_URL}projects/{owner}/{repo}/"
        debug_info["test_urls"] = {
            "direct_s3_url": s3_base_url,
            "index_html_url": f"{s3_base_url}index.html",
            "sample_js_url": f"{s3_base_url}{js_files[0].split('/')[-1]}" if js_files else None,
            "sample_css_url": f"{s3_base_url}{css_files[0].split('/')[-1]}" if css_files else None
        }
        
        # Overall assessment
        debug_info["severity"] = "high" if len(debug_info["issues_found"]) > 3 else "medium" if len(debug_info["issues_found"]) > 0 else "low"
        debug_info["total_issues"] = len(debug_info["issues_found"])
        
        return debug_info
        
    except Exception as e:
        return JSONResponse({
            "error": str(e),
            "success": False
        }, status_code=500)

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
                    
                    # Add cache control headers
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

async def fix_index_html_paths(folder_path):
    """Enhanced index.html path fixing with comprehensive debugging"""
    index_path = os.path.join(folder_path, "index.html")
    if not os.path.exists(index_path):
        print(f"❌ No index.html found in {folder_path}")
        # List files in the directory to debug
        if os.path.exists(folder_path):
            files = os.listdir(folder_path)
            print(f"Files in {folder_path}: {files}")
        return False
        
    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        html_content = original_content
        
        print(f"📄 Original index.html content preview:")
        print(f"Length: {len(original_content)} characters")
        print(f"First 200 chars: {original_content[:200]}")
        
        # Check if it's actually empty or has minimal content
        if len(original_content.strip()) < 100:
            print("⚠️  WARNING: index.html seems very short - possibly corrupted build")
            
        # More comprehensive path fixing
        changes_made = []
        
        # Fix static asset paths
        if 'src="/static/' in html_content:
            html_content = html_content.replace('src="/static/', 'src="./static/')
            changes_made.append("Fixed src static paths")
            
        if 'href="/static/' in html_content:
            html_content = html_content.replace('href="/static/', 'href="./static/')
            changes_made.append("Fixed href static paths")
            
        if 'src="/assets/' in html_content:
            html_content = html_content.replace('src="/assets/', 'src="./assets/')
            changes_made.append("Fixed src assets paths")
            
        if 'href="/assets/' in html_content:
            html_content = html_content.replace('href="/assets/', 'href="./assets/')
            changes_made.append("Fixed href assets paths")
        
        # Fix any remaining absolute paths (but be careful not to break external URLs)
        import re
        # Only fix paths that start with / but aren't URLs
        pattern = r'(src|href)="(/[^"]*?)"'
        def fix_path(match):
            attr, path = match.groups()
            # Don't fix external URLs or data URLs
            if path.startswith(('http', 'https', 'data:', 'mailto:', 'tel:')):
                return match.group(0)
            # Fix local absolute paths
            return f'{attr}=".{path}"'
        
        new_content = re.sub(pattern, fix_path, html_content)
        if new_content != html_content:
            html_content = new_content
            changes_made.append("Fixed remaining absolute paths")
        
        # Add or fix base tag for SPA routing
        if '<base href="/">' in html_content:
            html_content = html_content.replace('<base href="/">', '<base href="./">')
            changes_made.append("Updated base href to relative")
        elif '<head>' in html_content and '<base href="./">' not in html_content:
            html_content = html_content.replace('<head>', '<head>\n    <base href="./">')
            changes_made.append("Added relative base href")
        
        # Ensure React root div exists
        if 'id="root"' not in html_content and 'id=\'root\'' not in html_content:
            print("⚠️  WARNING: No React root div found - this might cause blank page")
            
        # Write the fixed content
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        print(f"✅ Fixed index.html paths - Changes made: {changes_made}")
        print(f"📄 Updated content preview:")
        print(f"Length: {len(html_content)} characters")
        print(f"First 200 chars: {html_content[:200]}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error fixing index.html paths: {str(e)}")
        return False

async def modify_package_json_for_relative_paths(repo_path):
    """Fix both relative paths AND SPA routing for React projects"""
    package_json_path = os.path.join(repo_path, "package.json")
    if not os.path.exists(package_json_path):
        print("package.json not found, skipping modification")
        return False
    
    try:
        # Read and modify package.json
        with open(package_json_path, 'r', encoding='utf-8') as f:
            package_data = json.load(f)
        
        # Set homepage for relative paths
        package_data["homepage"] = "."
        
        # Write back package.json
        with open(package_json_path, 'w', encoding='utf-8') as f:
            json.dump(package_data, f, indent=2)
        
        print("✅ Modified package.json homepage to '.'")
        
        # Handle different project types
        dependencies = package_data.get('dependencies', {})
        dev_dependencies = package_data.get('devDependencies', {})
        is_cra = 'react-scripts' in dependencies or 'react-scripts' in dev_dependencies
        is_vite = 'vite' in dependencies or 'vite' in dev_dependencies
        
        if is_vite:
            await fix_vite_config_for_spa(repo_path)
        
        if is_cra:
            await create_redirects_for_cra(repo_path)
        
        return True
        
    except Exception as e:
        print(f"Error modifying package.json: {str(e)}")
        return False

async def fix_vite_config_for_spa(repo_path):
    """Fix Vite config for SPA routing and relative paths with version compatibility"""
    vite_config_candidates = [
        os.path.join(repo_path, "vite.config.js"),
        os.path.join(repo_path, "vite.config.ts")
    ]
    
    vite_config_path = None
    for candidate in vite_config_candidates:
        if os.path.exists(candidate):
            vite_config_path = candidate
            break
    
    if not vite_config_path:
        # Create a new vite config if none exists
        vite_config_path = os.path.join(repo_path, "vite.config.js")
    
    try:
        # Create a proper Vite config that handles SPA routing and Node compatibility
        new_config = '''import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    // Ensure compatibility with older Node versions
    target: 'es2015',
    sourcemap: false
  },
  // Handle potential crypto issues
  define: {
    global: 'globalThis',
  },
  optimizeDeps: {
    include: ['react', 'react-dom']
  }
})
'''
        
        with open(vite_config_path, 'w', encoding='utf-8') as f:
            f.write(new_config)
        
        print("✅ Created compatible Vite config with SPA support")
        return True
        
    except Exception as e:
        print(f"Error fixing Vite config: {str(e)}")
        return False

async def create_redirects_for_cra(repo_path):
    """Create redirects file for Create React App SPA routing"""
    try:
        public_dir = os.path.join(repo_path, "public")
        if not os.path.exists(public_dir):
            os.makedirs(public_dir)
        
        # Create _redirects file for Netlify-style hosting
        redirects_path = os.path.join(public_dir, "_redirects")
        with open(redirects_path, 'w') as f:
            f.write("/*    /index.html   200\n")
        
        print("✅ Created _redirects file for SPA routing")
        return True
        
    except Exception as e:
        print(f"Error creating redirect files: {str(e)}")
        return False

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