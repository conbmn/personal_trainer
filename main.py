"""
Fitness Agent — main application.

Run with:
    uvicorn app.main:app --reload --port 8000
"""

from fastapi import FastAPI

from app.routes.auth_routes import router as auth_router

app = FastAPI(
    title="Fitness Agent",
    description="Personal training agent connecting Strava + Whoop + LLM",
    version="0.1.0",
)

# Register routes
app.include_router(auth_router)


@app.get("/")
async def root():
    return {
        "app": "Fitness Agent",
        "status": "running",
        "docs": "Visit /docs for interactive API docs",
        "next_steps": [
            "1. Copy .env.example to .env and fill in your credentials",
            "2. Visit /auth/strava/login to connect Strava",
            "3. Visit /auth/whoop/login to connect Whoop",
            "4. Check /auth/status to verify connections",
        ],
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
