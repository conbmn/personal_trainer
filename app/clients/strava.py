"""
Strava API client.

Wraps Strava's REST API v3 into clean async methods.
All methods auto-handle authentication via get_valid_access_token.

API docs: https://developers.strava.com/docs/reference/
Rate limits: 200 requests/15min, 2000 requests/day
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.auth import get_valid_access_token

BASE_URL = "https://www.strava.com/api/v3"


async def _get(endpoint: str, params: dict | None = None) -> dict | list:
    """Make an authenticated GET request to the Strava API."""
    token = await get_valid_access_token("strava")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}{endpoint}",
            headers=headers,
            params=params or {},
        )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Athlete
# ---------------------------------------------------------------------------

async def get_athlete() -> dict:
    """Get the authenticated athlete's profile."""
    return await _get("/athlete")


async def get_athlete_stats(athlete_id: int) -> dict:
    """Get the athlete's stats (totals, recent rides, etc.)."""
    return await _get(f"/athletes/{athlete_id}/stats")


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

async def get_activities(
    days: int = 30,
    per_page: int = 50,
    page: int = 1,
) -> list[dict]:
    """
    Get recent activities.

    Args:
        days: How many days back to look (default 30)
        per_page: Number of activities per page (max 200)
        page: Page number for pagination
    """
    after = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    return await _get("/athlete/activities", {
        "after": after,
        "per_page": per_page,
        "page": page,
    })


async def get_all_activities(days: int = 30) -> list[dict]:
    """Get ALL activities in the given time range, handling pagination."""
    all_activities = []
    page = 1

    while True:
        batch = await get_activities(days=days, per_page=200, page=page)
        if not batch:
            break
        all_activities.extend(batch)
        if len(batch) < 200:
            break
        page += 1

    return all_activities


async def get_activity_detail(activity_id: int) -> dict:
    """Get full details for a specific activity."""
    return await _get(f"/activities/{activity_id}", {
        "include_all_efforts": True,
    })


# ---------------------------------------------------------------------------
# Summary helpers (for the agent)
# ---------------------------------------------------------------------------

async def get_training_summary(days: int = 7) -> dict:
    """
    Build a training summary for the LLM agent to reason about.
    Returns structured data about recent training load.
    """
    activities = await get_all_activities(days=days)

    rides = [a for a in activities if a.get("type") in ("Ride", "VirtualRide")]
    runs = [a for a in activities if a.get("type") in ("Run", "VirtualRun")]
    swims = [a for a in activities if a.get("type") == "Swim"]

    def summarize(acts: list) -> dict:
        if not acts:
            return {"count": 0, "total_km": 0, "total_time_hrs": 0, "total_elevation_m": 0}
        return {
            "count": len(acts),
            "total_km": round(sum(a["distance"] for a in acts) / 1000, 1),
            "total_time_hrs": round(sum(a["moving_time"] for a in acts) / 3600, 1),
            "total_elevation_m": round(sum(a.get("total_elevation_gain", 0) for a in acts)),
            "avg_speed_kmh": round(
                sum(a["distance"] for a in acts)
                / max(sum(a["moving_time"] for a in acts), 1)
                * 3.6,
                1,
            ),
        }

    return {
        "period_days": days,
        "total_activities": len(activities),
        "rides": summarize(rides),
        "runs": summarize(runs),
        "swims": summarize(swims),
        "activities_list": [
            {
                "name": a["name"],
                "type": a["type"],
                "date": a["start_date_local"],
                "distance_km": round(a["distance"] / 1000, 1),
                "moving_time_min": round(a["moving_time"] / 60),
                "elevation_m": round(a.get("total_elevation_gain", 0)),
                "avg_hr": a.get("average_heartrate"),
                "max_hr": a.get("max_heartrate"),
                "suffer_score": a.get("suffer_score"),
            }
            for a in activities
        ],
    }
