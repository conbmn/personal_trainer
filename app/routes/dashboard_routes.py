"""
Dashboard API endpoint.

Single GET /api/dashboard route that fans out to Strava, Whoop, and metrics
in parallel and returns a composed payload for the frontend dashboard.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from app.clients import strava, whoop
from app import metrics

router = APIRouter(prefix="/api", tags=["dashboard"])


async def _safe_fetch(coro):
    try:
        return await coro
    except Exception:
        return None


def _recovery_label(score: float) -> str:
    if score >= 67:
        return "green"
    if score >= 34:
        return "yellow"
    return "red"


def _week_start_date() -> str:
    """ISO date string for this week's Monday (UTC)."""
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


@router.get("/dashboard")
async def get_dashboard():
    training_summary, recovery_raw, sleep_raw, readiness = await asyncio.gather(
        _safe_fetch(strava.get_training_summary(days=14)),
        _safe_fetch(whoop.get_recovery(days=2)),
        _safe_fetch(whoop.get_sleep(days=2)),
        _safe_fetch(metrics.compute_race_readiness()),
    )

    # --- Today's recovery ---
    today_block = None
    try:
        scored = [
            r for r in (recovery_raw or [])
            if r.get("score_state") == "SCORED" and r.get("score")
        ]
        scored.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        if scored:
            r = scored[0]
            score = r["score"]["recovery_score"]
            sleep_hrs = None
            try:
                # Match sleep entry closest to this recovery record
                sleep_scored = [
                    s for s in (sleep_raw or [])
                    if s.get("score_state") == "SCORED" and s.get("score") and not s.get("nap")
                ]
                sleep_scored.sort(key=lambda s: s.get("created_at", ""), reverse=True)
                if sleep_scored:
                    stage = sleep_scored[0]["score"].get("stage_summary", {})
                    total_ms = (
                        stage.get("total_light_sleep_time_milli", 0)
                        + stage.get("total_slow_wave_sleep_time_milli", 0)
                        + stage.get("total_rem_sleep_time_milli", 0)
                    )
                    if total_ms > 0:
                        sleep_hrs = round(total_ms / 3_600_000, 1)
            except Exception:
                pass

            today_block = {
                "recovery_score": score,
                "recovery_label": _recovery_label(score),
                "hrv_ms": round(r["score"].get("hrv_rmssd_milli", 0), 1) or None,
                "rhr_bpm": r["score"].get("resting_heart_rate"),
                "sleep_hours": sleep_hrs,
                "score_date": (r.get("created_at") or "")[:10],
            }
    except Exception:
        pass

    # --- Activities ---
    activities_list = []
    last_activity = None
    week_volume = {"swim_km": 0.0, "swim_min": 0, "bike_km": 0.0, "bike_min": 0, "run_km": 0.0, "run_min": 0}

    try:
        raw_list = (training_summary or {}).get("activities_list", [])
        # Sort newest first
        raw_list.sort(key=lambda a: a.get("date", ""), reverse=True)
        activities_list = raw_list[:7]
        if activities_list:
            last_activity = activities_list[0]

        # Week volume — filter from Monday of current week
        monday = _week_start_date()
        for a in raw_list:
            date_str = (a.get("date") or "")[:10]
            if date_str < monday:
                continue
            t = a.get("type", "")
            dist = a.get("distance_km", 0) or 0
            mins = a.get("moving_time_min", 0) or 0
            if t == "Swim":
                week_volume["swim_km"] = round(week_volume["swim_km"] + dist, 1)
                week_volume["swim_min"] += mins
            elif t in ("Ride", "VirtualRide"):
                week_volume["bike_km"] = round(week_volume["bike_km"] + dist, 1)
                week_volume["bike_min"] += mins
            elif t in ("Run", "VirtualRun"):
                week_volume["run_km"] = round(week_volume["run_km"] + dist, 1)
                week_volume["run_min"] += mins
    except Exception:
        pass

    # --- Race + metrics ---
    race_block = None
    metrics_block = None
    try:
        if readiness:
            race_block = {
                "weeks_to_race": readiness.get("weeks_to_race"),
                "phase": readiness.get("phase"),
                "readiness_score": readiness.get("total_score"),
                "readiness_label": readiness.get("status_label"),
            }
            load = readiness.get("load_summary", {})
            metrics_block = {
                "ctl": load.get("ctl"),
                "atl": load.get("atl"),
                "tsb": load.get("tsb"),
            }
    except Exception:
        pass

    return {
        "today": today_block,
        "last_activity": last_activity,
        "recent_activities": activities_list,
        "week_volume": week_volume,
        "race": race_block,
        "metrics": metrics_block,
    }
