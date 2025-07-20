from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.routes.User.User import user_routes 
from app.routes.Project.Project import project_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key-here",
    https_only=False 
)
app.include_router(user_routes, prefix="/api/user")
app.include_router(project_router, prefix="/api/project")

@app.get("/")
async def root():
    return {"message": "GitHub Hoster API", "version": "1.0.0"}

@app.get("/api/health")
async def health():
    return {"status": "healthy"}