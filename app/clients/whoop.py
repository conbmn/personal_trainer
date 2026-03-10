"""
Whoop API client.

Wraps Whoop's REST API v2 into clean async methods.
All methods auto-handle authentication via get_valid_access_token.

API docs: https://developer.whoop.com/api/
Note: Whoop uses pagination with next_token, max 25 per page.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.auth import get_valid_access_token

BASE_URL = "https://api.prod.whoop.com/developer"


async def _get(endpoint: str, params: dict | None = None) -> dict | list:
    """Make an authenticated GET request to the Whoop API."""
    token = await get_valid_access_token("whoop")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}{endpoint}",
            headers=headers,
            params=params or {},
        )
        response.raise_for_status()
        return response.json()


async def _get_all_paginated(endpoint: str, params: dict | None = None) -> list[dict]:
    """Fetch all pages of a paginated Whoop endpoint."""
    params = params or {}
    all_records = []

    while True:
        data = await _get(endpoint, params)
        records = data.get("records", [])
        all_records.extend(records)

        next_token = data.get("next_token")
        if not next_token or not records:
            break
        params["nextToken"] = next_token

    return all_records


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

async def get_profile() -> dict:
    """Get the authenticated user's profile."""
    return await _get("/v2/user/profile/basic")


async def get_body_measurements() -> dict:
    """Get body measurements (height, weight, max HR)."""
    return await _get("/v2/user/measurement/body")


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------

async def get_recovery(days: int = 7, limit: int = 25) -> list[dict]:
    """Get recent recovery scores."""
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return await _get_all_paginated("/v2/recovery", {
        "start": start,
        "limit": limit,
    })


# ---------------------------------------------------------------------------
# Sleep
# ---------------------------------------------------------------------------

async def get_sleep(days: int = 7, limit: int = 25) -> list[dict]:
    """Get recent sleep data."""
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return await _get_all_paginated("/v2/activity/sleep", {
        "start": start,
        "limit": limit,
    })


# ---------------------------------------------------------------------------
# Workouts
# ---------------------------------------------------------------------------

async def get_workouts(days: int = 7, limit: int = 25) -> list[dict]:
    """Get recent workouts."""
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return await _get_all_paginated("/v2/activity/workout", {
        "start": start,
        "limit": limit,
    })


# ---------------------------------------------------------------------------
# Cycles (daily strain)
# ---------------------------------------------------------------------------

async def get_cycles(days: int = 7, limit: int = 25) -> list[dict]:
    """Get recent physiological cycles (daily strain data)."""
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return await _get_all_paginated("/v2/cycle", {
        "start": start,
        "limit": limit,
    })


# ---------------------------------------------------------------------------
# Summary helper (for the agent)
# ---------------------------------------------------------------------------

async def get_recovery_summary(days: int = 7) -> dict:
    """
    Build a recovery/readiness summary for the LLM agent.
    Combines recovery, sleep, and workout data.
    """
    recovery_data = await get_recovery(days=days)
    sleep_data = await get_sleep(days=days)
    workout_data = await get_workouts(days=days)

    # Parse recovery scores
    scored_recovery = [
        r for r in recovery_data
        if r.get("score_state") == "SCORED" and r.get("score")
    ]

    recovery_scores = [r["score"]["recovery_score"] for r in scored_recovery]
    hrv_values = [r["score"]["hrv_rmssd_milli"] for r in scored_recovery if r["score"].get("hrv_rmssd_milli")]
    rhr_values = [r["score"]["resting_heart_rate"] for r in scored_recovery if r["score"].get("resting_heart_rate")]

    # Parse sleep
    scored_sleep = [
        s for s in sleep_data
        if s.get("score_state") == "SCORED" and s.get("score") and not s.get("nap")
    ]

    sleep_performances = [
        s["score"]["sleep_performance_percentage"]
        for s in scored_sleep
        if s["score"].get("sleep_performance_percentage") is not None
    ]

    sleep_durations_hrs = []
    for s in scored_sleep:
        stage = s["score"].get("stage_summary", {})
        total_sleep = (
            stage.get("total_light_sleep_time_milli", 0)
            + stage.get("total_slow_wave_sleep_time_milli", 0)
            + stage.get("total_rem_sleep_time_milli", 0)
        )
        if total_sleep > 0:
            sleep_durations_hrs.append(round(total_sleep / 3_600_000, 1))

    # Parse strain from workouts
    scored_workouts = [
        w for w in workout_data
        if w.get("score_state") == "SCORED" and w.get("score")
    ]
    strain_values = [w["score"]["strain"] for w in scored_workouts if w["score"].get("strain")]

    def safe_avg(values):
        return round(sum(values) / len(values), 1) if values else None

    def safe_min(values):
        return round(min(values), 1) if values else None

    def safe_max(values):
        return round(max(values), 1) if values else None

    return {
        "period_days": days,
        "recovery": {
            "count": len(recovery_scores),
            "avg_score": safe_avg(recovery_scores),
            "min_score": safe_min(recovery_scores),
            "max_score": safe_max(recovery_scores),
            "days_red": sum(1 for s in recovery_scores if s < 34),
            "days_yellow": sum(1 for s in recovery_scores if 34 <= s < 67),
            "days_green": sum(1 for s in recovery_scores if s >= 67),
        },
        "hrv": {
            "avg_ms": safe_avg(hrv_values),
            "min_ms": safe_min(hrv_values),
            "max_ms": safe_max(hrv_values),
        },
        "resting_heart_rate": {
            "avg_bpm": safe_avg(rhr_values),
            "min_bpm": safe_min(rhr_values),
            "max_bpm": safe_max(rhr_values),
        },
        "sleep": {
            "count": len(sleep_durations_hrs),
            "avg_hours": safe_avg(sleep_durations_hrs),
            "min_hours": safe_min(sleep_durations_hrs),
            "max_hours": safe_max(sleep_durations_hrs),
            "avg_performance_pct": safe_avg(sleep_performances),
        },
        "workouts": {
            "count": len(scored_workouts),
            "total_strain": round(sum(strain_values), 1) if strain_values else 0,
            "avg_strain": safe_avg(strain_values),
            "max_strain": safe_max(strain_values),
        },
        "daily_details": [
            {
                "date": r.get("created_at", "")[:10],
                "recovery_score": r["score"]["recovery_score"],
                "hrv_ms": round(r["score"].get("hrv_rmssd_milli", 0), 1),
                "rhr_bpm": r["score"].get("resting_heart_rate"),
                "spo2_pct": r["score"].get("spo2_percentage"),
            }
            for r in scored_recovery
        ],
    }