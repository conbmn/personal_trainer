"""
Whoop data routes — endpoints to explore your recovery and sleep data.
"""

from fastapi import APIRouter, HTTPException

from app.clients import whoop

router = APIRouter(prefix="/whoop", tags=["whoop"])


@router.get("/profile")
async def profile():
    """Get your Whoop profile."""
    try:
        return await whoop.get_profile()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/body")
async def body():
    """Get body measurements (height, weight, max HR)."""
    try:
        return await whoop.get_body_measurements()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recovery")
async def recovery(days: int = 7):
    """Get recent recovery scores."""
    try:
        return await whoop.get_recovery(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sleep")
async def sleep(days: int = 7):
    """Get recent sleep data."""
    try:
        return await whoop.get_sleep(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workouts")
async def workouts(days: int = 7):
    """Get recent workouts."""
    try:
        return await whoop.get_workouts(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cycles")
async def cycles(days: int = 7):
    """Get recent cycles (daily strain)."""
    try:
        return await whoop.get_cycles(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def recovery_summary(days: int = 7):
    """
    Get a structured recovery summary.
    This is what the LLM agent will use.
    """
    try:
        return await whoop.get_recovery_summary(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
