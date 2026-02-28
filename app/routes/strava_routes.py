"""
Strava data routes — endpoints to explore your training data.

These are for testing and direct access. In Phase 3, the LLM agent
will call the client functions directly as tools.
"""

from fastapi import APIRouter, HTTPException

from app.clients import strava

router = APIRouter(prefix="/strava", tags=["strava"])


@router.get("/athlete")
async def athlete():
    """Get your Strava profile."""
    try:
        return await strava.get_athlete()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def stats():
    """Get your all-time stats (totals, recent activity counts)."""
    try:
        athlete = await strava.get_athlete()
        return await strava.get_athlete_stats(athlete["id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/activities")
async def activities(days: int = 30):
    """Get recent activities (default: last 30 days)."""
    try:
        return await strava.get_all_activities(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/activities/{activity_id}")
async def activity_detail(activity_id: int):
    """Get full details for a specific activity."""
    try:
        return await strava.get_activity_detail(activity_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def training_summary(days: int = 7):
    """
    Get a structured training summary.
    This is what the LLM agent will use in Phase 3.
    """
    try:
        return await strava.get_training_summary(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
