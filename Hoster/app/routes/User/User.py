from fastapi import Request, APIRouter
from fastapi.responses import RedirectResponse, HTMLResponse
import requests
import base64
from app.config import oauth

user_routes = APIRouter()

@user_routes.get("/login")
async def login(request: Request):
    redirect_uri = str(request.base_url) + "user/auth"
    print(redirect_uri)  
    return await oauth.github.authorize_redirect(request, redirect_uri)

@user_routes.get("/auth")
async def auth(request: Request):
    token = await oauth.github.authorize_access_token(request)
    print(request.url)
    print(token)
    request.session['token'] = token
    
    user = await oauth.github.get('user', token=token)
    user_data = user.json()
    request.session['user_info'] = user_data  # Store user info

    return RedirectResponse('/')  # Redirect to dashboard

@user_routes.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse('/')

@user_routes.get("/profile")
async def profile(request: Request):
    token = request.session.get('token')
    if not token:
        return RedirectResponse('/user/login')
    
    user_data = request.session.get('user_info', {})
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Profile</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .profile {{ max-width: 500px; margin: 0 auto; background: #f8f9fa; padding: 30px; border-radius: 10px; }}
            img {{ border-radius: 50%; }}
        </style>
    </head>
    <body>
        <div class="profile">
            <h2>👤 Profile Information</h2>
            <img src="{user_data.get('avatar_url', '')}" width="100" height="100">
            <h3>{user_data.get('name', 'No name')}</h3>
            <p><strong>Username:</strong> {user_data.get('login', '')}</p>
            <p><strong>Email:</strong> {user_data.get('email', 'Not public')}</p>
            <p><strong>Public Repos:</strong> {user_data.get('public_repos', 0)}</p>
            <p><strong>Followers:</strong> {user_data.get('followers', 0)}</p>
            <p><strong>Following:</strong> {user_data.get('following', 0)}</p>
            
            <div style="margin-top: 30px;">
                <a href="/" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">← Back to Dashboard</a>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html_content)

@user_routes.get("/repos")
async def get_repos(request: Request):
    token = request.session.get('token')
    if not token:
        return RedirectResponse('/user/login')
    
    resp = await oauth.github.get('user/repos', token=token)
    repos = resp.json()
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>My Repositories</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .repo-list { max-width: 800px; margin: 0 auto; }
            .repo-item { background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 8px; border-left: 4px solid #007bff; }
            .repo-name { font-weight: bold; color: #007bff; }
            .repo-desc { color: #666; margin: 5px 0; }
        </style>
    </head>
    <body>
        <div class="repo-list">
            <h2>📁 My Repositories</h2>
    """
    
    for repo in repos:
        description = repo.get('description', 'No description')
        html_content += f"""
        <div class="repo-item">
            <div class="repo-name">{repo['full_name']}</div>
            <div class="repo-desc">{description}</div>
            <a href="/user/code/{repo['owner']['login']}/{repo['name']}/README.md">View Code</a>
        </div>
        """
    
    html_content += """
            <div style="margin-top: 30px; text-align: center;">
                <a href="/" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">← Back to Dashboard</a>
                <a href="/project/repos" style="background: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-left: 10px;">🔨 Build Projects</a>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html_content)

@user_routes.get("/code/{owner}/{repo}/{path:path}")
async def get_code(request: Request, owner: str, repo: str, path: str):
    token = request.session.get('token')
    if not token:
        return RedirectResponse('/user/login')

    headers = {'Authorization': f'token {token["access_token"]}'}
    url = f'https://api.github.com/repos/{owner}/{repo}/contents/{path}'
    r = requests.get(url, headers=headers)

    if r.status_code == 200:
        content = r.json()
        if content.get("encoding") == "base64":
            code = base64.b64decode(content['content']).decode('utf-8')
            return HTMLResponse(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Code Viewer</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    pre {{ background: #f8f9fa; padding: 20px; border-radius: 5px; overflow-x: auto; }}
                    .header {{ margin-bottom: 20px; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h3>📄 {owner}/{repo}/{path}</h3>
                    <a href="/user/repos">← Back to Repositories</a>
                </div>
                <pre><code>{code}</code></pre>
            </body>
            </html>
            """)
        return {"error": "Unsupported encoding"}
    return {"error": "File not found", "status_code": r.status_code}