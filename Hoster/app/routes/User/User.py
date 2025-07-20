from fastapi import Request, APIRouter
from fastapi.responses import RedirectResponse, JSONResponse
from app.config import oauth

user_routes = APIRouter()

@user_routes.get("/login")
async def login(request: Request):
    redirect_uri = str(request.base_url).rstrip('/') + "/api/user/auth"
    print(f"Redirect URI: {redirect_uri}")
    return await oauth.github.authorize_redirect(request, redirect_uri)

@user_routes.get("/auth")
async def auth(request: Request):
    try:
        print(f"Auth request URL: {request.url}")
        print(f"Session before auth: {dict(request.session)}")
        
        token = await oauth.github.authorize_access_token(request)
        print(f"Token received: {token}")
        
        request.session['token'] = token
        
        user = await oauth.github.get('user', token=token)
        user_data = user.json()
        request.session['user_info'] = user_data
        
        print(f"Session after auth: {dict(request.session)}")
        print(f"User data: {user_data.get('login', 'No login')}")
        
        
        return RedirectResponse('http://localhost:5173/')
    except Exception as e:
        print(f"Auth error: {str(e)}")
       
        return RedirectResponse('http://localhost:5173/?error=auth_failed')

@user_routes.get("/me")
async def get_current_user(request: Request):
    print(f"Session data: {dict(request.session)}")
    token = request.session.get('token')
    print(f"Token: {token}")
    user_info = request.session.get('user_info')
    
    if not token:
        print("No token found in session")
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    return {
        "authenticated": True,
        "user": user_info,
        "token_type": token.get('token_type', 'bearer')
    }

@user_routes.post("/logout")
async def logout(request: Request):
    print("Logging out user")
    request.session.clear()
    return {"success": True, "message": "Logged out"}