from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from app.routes.User.User import user_routes 
from app.routes.Project.Project import project_router
from starlette.config import Config

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key="your-secret-key-here")
config = Config('.env')

app.include_router(user_routes, prefix="/user")
app.include_router(project_router, prefix="/project")

@app.get("/")
async def home(req: Request, res: Response):
    # Check if user is logged in
    token = req.session.get('token')
    user_info = req.session.get('user_info', {})
    
    if token:
        # User is logged in - show dashboard
        username = user_info.get('login', 'User')
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>GitHub Hoster - Dashboard</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .nav-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
                .nav-card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; border: 2px solid #e9ecef; }}
                .nav-card:hover {{ border-color: #007bff; }}
                .nav-card a {{ text-decoration: none; color: #333; font-weight: bold; }}
                .nav-card p {{ margin: 10px 0 0 0; color: #666; font-size: 14px; }}
                .user-info {{ background: #e7f3ff; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .logout {{ float: right; background: #dc3545; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚀 GitHub Hoster Dashboard</h1>
                    <div class="user-info">
                        Welcome back, <strong>{username}</strong>! 
                        <a href="/user/logout" class="logout">Logout</a>
                        <div style="clear: both;"></div>
                    </div>
                </div>
                
                <div class="nav-grid">
                    <div class="nav-card">
                        <a href="/user/repos">📁 View Repositories</a>
                        <p>Browse and view your GitHub repositories</p>
                    </div>
                    
                    <div class="nav-card">
                        <a href="/project/repos">🔨 Build Projects</a>
                        <p>Clone and build your React projects</p>
                    </div>
                    
                    <div class="nav-card">
                        <a href="/project/builds">📦 Built Projects</a>
                        <p>View and manage your built applications</p>
                    </div>
                    
                    <div class="nav-card">
                        <a href="/user/profile">👤 Profile</a>
                        <p>View your GitHub profile information</p>
                    </div>
                </div>
                
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
                    <h3>🛠️ Quick Actions</h3>
                    <p><a href="/project/repos" style="background: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Start Building Projects</a></p>
                </div>
            </div>
        </body>
        </html>
        """
    else:
       
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>GitHub Hoster</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
                .login-container { background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); text-align: center; max-width: 400px; }
                .login-btn { background: #333; color: white; padding: 12px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; margin-top: 20px; }
                .login-btn:hover { background: #555; }
                h1 { color: #333; margin-bottom: 10px; }
                p { color: #666; margin-bottom: 30px; }
            </style>
        </head>
        <body>
            <div class="login-container">
                <h1>🚀 GitHub Hoster</h1>
                <p>Clone, build, and host your GitHub projects with ease!</p>
                <a href="/user/login" class="login-btn">🔑 Login with GitHub</a>
                
                <div style="margin-top: 30px; font-size: 14px; color: #999;">
                    <p><strong>Features:</strong></p>
                    <ul style="text-align: left; display: inline-block;">
                        <li>Clone GitHub repositories</li>
                        <li>Build React projects automatically</li>
                        <li>Store built files on server</li>
                        <li>Easy project management</li>
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """
    
    return HTMLResponse(html_content)

@app.get("/dashboard")
async def dashboard(req: Request):
    """Alternative dashboard route"""
    return await home(req, Response())