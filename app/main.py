"""
Fitness Agent — main application.

Run with:
    uvicorn app.main:app --reload --port 8000
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.routes.auth_routes import router as auth_router
from app.routes.strava_routes import router as strava_router
from app.routes.whoop_routes import router as whoop_router
from app.routes.agent_routes import router as agent_router

app = FastAPI(
    title="Fitness Agent",
    description="Personal training agent connecting Strava + Whoop + LLM",
    version="0.1.0",
)

# Allow the frontend to talk to the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(auth_router)
app.include_router(strava_router)
app.include_router(whoop_router)
app.include_router(agent_router)

# Serve static files
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}
