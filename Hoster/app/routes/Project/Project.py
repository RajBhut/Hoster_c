from fastapi import FastAPI, Request, APIRouter, Response
from fastapi.responses import RedirectResponse, HTMLResponse
import requests
import docker
import os
import shutil
import zipfile
import tempfile
import json

from app.config import oauth

project_router = APIRouter()

docker_client = docker.from_env()

@project_router.get("/repos")
async def get_user_repos(request: Request):
    token = request.session.get('token')
    if not token:
        return RedirectResponse('/user/login')
    
    resp = await oauth.github.get('user/repos', token=token)
    repos = resp.json()
    
    react_repos = []
    for repo in repos:
        repo_info = {
            "name": repo['name'],
            "full_name": repo['full_name'],
            "owner": repo['owner']['login'],
            "is_react": await is_react_project(request, repo['owner']['login'], repo['name'])
        }
        react_repos.append(repo_info)
    
    html_content = "<h2>Your Repositories</h2><ul>"
    for repo in react_repos:
        if repo['is_react']:
            html_content += f"""
            <li>
                <strong>{repo['full_name']}</strong> (React Project)
                <br>
                <a href='/project/build/{repo['owner']}/{repo['name']}' style='background: green; color: white; padding: 5px; text-decoration: none;'>Build Project</a>
            </li><br>
            """
        else:
            html_content += f"<li>{repo['full_name']} (Not a React project)</li><br>"
    
    html_content += "</ul><br><a href='/project/builds'>View Built Projects</a>"
    return HTMLResponse(html_content)

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
                import base64
                package_json = base64.b64decode(content['content']).decode('utf-8')
                package_data = json.loads(package_json)
                
                dependencies = package_data.get('dependencies', {})
                dev_dependencies = package_data.get('devDependencies', {})
                
                return ('react' in dependencies or 'react' in dev_dependencies)
        
        return False
    except:
        return False

@project_router.get("/build/{owner}/{repo}")
async def build_react_project(request: Request, owner: str, repo: str):
    """Build React project in Docker container"""
    token = request.session.get('token')
    if not token:
        return RedirectResponse('/user/login')
    
    if not await is_react_project(request, owner, repo):
        return HTMLResponse("""
        <h2>Unsupported Project</h2>
        <p>This project is not a React project. Currently only React projects are supported.</p>
        <a href='/project/repos'>Back to Repositories</a>
        """)
    
    try:
        headers = {'Authorization': f'token {token["access_token"]}'}
        zip_url = f'https://api.github.com/repos/{owner}/{repo}/zipball'
        
        response = requests.get(zip_url, headers=headers)
        if response.status_code != 200:
            return {"error": "Failed to download repository"}
        
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
                return {"error": "No files extracted"}
            
            repo_path = os.path.join(extract_path, extracted_folders[0])
            
            build_result = await build_react_in_docker(repo_path, build_output, owner, repo)
            
            if build_result["success"]:
                server_build_dir = f"./builds/{owner}_{repo}"
                os.makedirs(server_build_dir, exist_ok=True)
                
                if os.path.exists(build_output) and os.listdir(build_output):
                        build_folder = os.path.join(build_output, "build")
                        if os.path.exists(build_folder):
                            shutil.copytree(build_folder, server_build_dir, dirs_exist_ok=True)
                        else:
                            shutil.copytree(build_output, server_build_dir, dirs_exist_ok=True)
                
                return HTMLResponse(f"""
                <h2>Build Successful!</h2>
                <p>Project <strong>{owner}/{repo}</strong> has been built successfully.</p>
                <p><strong>Build location:</strong> {server_build_dir}</p>
                <p><a href='/project/builds'>View All Builds</a></p>
                <p><a href='/project/repos'>Back to Repositories</a></p>
                <pre><strong>Build Logs:</strong>\n{chr(10).join(build_result["logs"])}</pre>
                """)
            else:
                return HTMLResponse(f"""
                <h2>Build Failed</h2>
                <p><strong>Error:</strong> {build_result["error"]}</p>
                <p><a href='/project/repos'>Back to Repositories</a></p>
                <pre><strong>Logs:</strong>\n{chr(10).join(build_result["logs"])}</pre>
                """)
                
    except Exception as e:
        return HTMLResponse(f"""
        <h2>Build Failed</h2>
        <p><strong>Error:</strong> {str(e)}</p>
        <p><a href='/project/repos'>Back to Repositories</a></p>
        """)


#     try:
#         # Create Dockerfile for React build
#         dockerfile_content = """
# FROM node:18-alpine
# WORKDIR /app
# COPY package*.json ./
# RUN npm install
# COPY . .
# RUN npm run build
# CMD ["sh"]
# """
        
#         dockerfile_path = os.path.join(repo_path, "Dockerfile.build")
#         with open(dockerfile_path, 'w') as f:
#             f.write(dockerfile_content)
        
#         # Build Docker image
#         image_tag = f"react_build_{owner}_{repo}".lower().replace('-', '_')
#         image, logs = docker_client.images.build(
#             path=repo_path,
#             dockerfile="Dockerfile.build",
#             tag=image_tag,
#             rm=True
#         )
        
#         # Run container and copy build output
#         container = docker_client.containers.run(
#             image_tag,
#             detach=True,
#             volumes={build_output: {'bind': '/output', 'mode': 'rw'}}
#         )
        
#         # Copy the build directory (React projects typically build to 'build' or 'dist')
#         copy_commands = [
#             "cp -r /app/build/* /output/ 2>/dev/null || echo 'No build folder'",
#             "cp -r /app/dist/* /output/ 2>/dev/null || echo 'No dist folder'",
#         ]
        
#         exec_results = []
#         for cmd in copy_commands:
#             exec_result = container.exec_run(f"sh -c '{cmd}'")
#             exec_results.append(exec_result.output.decode())
        
#         container.stop()
#         container.remove()
#         docker_client.images.remove(image_tag)
        
#         # Convert logs to strings
#         log_messages = []
#         for log in logs:
#             if isinstance(log, dict) and 'stream' in log:
#                 log_messages.append(log['stream'].strip())
#             else:
#                 log_messages.append(str(log).strip())
        
#         return {
#             "success": True,
#             "logs": log_messages + exec_results
#         }
        
#     except Exception as e:
#         return {
#             "success": False,
#             "error": str(e),
#             "logs": [f"Docker build failed: {str(e)}"]
#         }

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

# Copy package files first for better caching
COPY package*.json ./

# Install dependencies with verbose logging
RUN npm install --verbose || (echo "NPM install failed" && exit 1)

# Copy all files
COPY . .

# Try multiple build commands
RUN npm run build 2>&1 || npm run compile 2>&1 || (echo "Build completed with warnings" && ls -la)

# Create output directory and copy build files
RUN mkdir -p /app/output && \
    (cp -r /app/build/* /app/output/ 2>/dev/null || echo "No build folder") && \
    (cp -r /app/dist/* /app/output/ 2>/dev/null || echo "No dist folder") && \
    ls -la /app/output/

# Keep container running
CMD ["tail", "-f", "/dev/null"]
"""
        
        dockerfile_path = os.path.join(repo_path, "Dockerfile.build")
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)
        
        image_tag = f"react_build_{owner}_{repo}".lower().replace('-', '_').replace('.', '_')
        
        print(f"Building Docker image: {image_tag}")
        image, logs = docker_client.images.build(
            path=repo_path,
            dockerfile="Dockerfile.build",
            tag=image_tag,
            rm=True,
            pull=True 
        )
        
        print("Docker image built successfully")
        
        abs_build_output = os.path.abspath(build_output)
        
        container = docker_client.containers.run(
            image_tag,
            detach=True,
            volumes={abs_build_output: {'bind': '/output', 'mode': 'rw'}},
            working_dir='/app'
        )
        
        print(f"Container started: {container.id}")
        
        import time
        time.sleep(2)
        
        container.reload()
        if container.status != 'running':
            container_logs = container.logs().decode()
            print(f"Container stopped unexpectedly: {container_logs}")
            
            try:
                container.remove()
                docker_client.images.remove(image_tag)
            except:
                pass
                
            return {
                "success": False,
                "error": "Container stopped during build",
                "logs": [container_logs]
            }
        
        copy_commands = [
            "ls -la /app/",
            "ls -la /app/build/ 2>/dev/null || echo 'No build directory'",
            "ls -la /app/dist/ 2>/dev/null || echo 'No dist directory'",
            "cp -r /app/build /output/ 2>/dev/null || echo 'No build directory to copy'",
            "cp -r /app/dist/* /output/ 2>/dev/null || echo 'No dist files to copy'",
            "ls -la /output/ || echo 'Output directory empty'"
        ]
        
        exec_results = []
        for cmd in copy_commands:
            try:
                exec_result = container.exec_run(f"sh -c '{cmd}'")
                output = exec_result.output.decode()
                exec_results.append(f"Command: {cmd}\nOutput: {output}")
                print(f"Exec result: {output}")
            except Exception as e:
                exec_results.append(f"Command failed: {cmd}, Error: {str(e)}")
        
        try:
            container.stop()
            container.remove()
            docker_client.images.remove(image_tag)
        except Exception as e:
            print(f"Cleanup error: {e}")
        
        log_messages = []
        for log in logs:
            if isinstance(log, dict) and 'stream' in log:
                log_messages.append(log['stream'].strip())
            else:
                log_messages.append(str(log).strip())
        
        if os.path.exists(build_output) and os.listdir(build_output):
            return {
                "success": True,
                "logs": log_messages + exec_results
            }
        else:
            return {
                "success": False,
                "error": "No build files were generated",
                "logs": log_messages + exec_results
            }
        
    except Exception as e:
       
        try:
            if 'container' in locals():
                container.stop()
                container.remove()
            if 'image_tag' in locals():
                docker_client.images.remove(image_tag)
        except:
            pass
            
        return {
            "success": False,
            "error": str(e),
            "logs": [f"Docker build failed: {str(e)}"]
        }

@project_router.get("/builds")
async def list_builds(request: Request):
    builds_dir = "./builds"
    if not os.path.exists(builds_dir):
        os.makedirs(builds_dir)
        return HTMLResponse("<h2>No builds found</h2><a href='/project/repos'>Back to Repositories</a>")
    
    builds = []
    for build_folder in os.listdir(builds_dir):
        build_path = os.path.join(builds_dir, build_folder)
        if os.path.isdir(build_path):
            files = os.listdir(build_path)
            builds.append({
                "name": build_folder,
                "path": build_path,
                "file_count": len(files)
            })
    
    if not builds:
        return HTMLResponse("<h2>No builds found</h2><a href='/project/repos'>Back to Repositories</a>")
    
    html_content = "<h2>Built Projects</h2><ul>"
    for build in builds:
        html_content += f"""
        <li>
            <strong>{build['name']}</strong><br>
            Path: {build['path']}<br>
            Files: {build['file_count']}<br>
        </li><br>
        """
    
    html_content += "</ul><a href='/project/repos'>Back to Repositories</a>"
    return HTMLResponse(html_content)

def check_project_type(req: Request, res: Response):
    token = req.session.get('token')
    if not token:
        return RedirectResponse('/user/login')
    project = oauth.github.get('user/repos', token=token)
    if project.status_code == 200:
        return project.json()
    return {"error": "Unable to fetch projects", "status_code": project.status_code}