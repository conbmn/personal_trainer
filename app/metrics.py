"""
Training load metrics and race readiness.

Computes CTL/ATL/TSB (fitness/fatigue/form) from Strava heart rate data
and a composite race readiness score combining training load + Whoop recovery.
"""

from datetime import datetime, timedelta, timezone

from app.clients import strava, whoop

_RACE_DATE = "2026-07-12"


async def _safe_fetch(coro):
    try:
        return await coro
    except Exception:
        return []


def _weeks_until_race() -> int:
    race = datetime.strptime(_RACE_DATE, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return max(0, (race - datetime.now(timezone.utc)).days // 7)


# ---------------------------------------------------------------------------
# Phase label
# ---------------------------------------------------------------------------

def get_phase_label(weeks: int) -> str:
    if weeks > 16:
        return "Base"
    if weeks > 8:
        return "Build"
    if weeks > 3:
        return "Peak"
    return "Taper"


# ---------------------------------------------------------------------------
# Training load (CTL / ATL / TSB)
# ---------------------------------------------------------------------------

async def compute_training_load(days_back: int = 90) -> dict:
    """
    Fetch ~90 days of Strava activities and compute CTL, ATL, TSB.

    CTL (Chronic Training Load) = 42-day EWA of daily TSS → fitness
    ATL (Acute Training Load)   = 7-day EWA of daily TSS  → fatigue
    TSB (Training Stress Balance) = CTL - ATL              → form/freshness

    TSS is approximated from heart rate:
        hrTSS = (duration_hrs) × (avg_hr / threshold_hr)² × 100

    Threshold HR is derived from Whoop max HR (87th percentile).
    """
    # --- Fetch data in parallel ---
    import asyncio
    activities, whoop_workouts_raw = await asyncio.gather(
        strava.get_all_activities(days=days_back),
        _safe_fetch(whoop.get_workouts(days=days_back)),
    )

    threshold_hr = 175.0  # fallback
    try:
        body = await whoop.get_body_measurements()
        max_hr = body.get("max_heart_rate")
        if max_hr and max_hr > 100:
            threshold_hr = max_hr * 0.87
    except Exception:
        pass

    # --- Build Whoop workout HR lookup keyed by UTC start timestamp ---
    # Each entry: (start_ts_seconds, avg_hr, duration_seconds)
    whoop_workouts: list[tuple[float, float, float]] = []
    for w in (whoop_workouts_raw or []):
        if w.get("score_state") != "SCORED" or not w.get("score"):
            continue
        avg_hr_w = w["score"].get("average_heart_rate")
        start_str = w.get("start", "")
        end_str = w.get("end", "")
        if not avg_hr_w or not start_str:
            continue
        try:
            start_ts = datetime.fromisoformat(start_str.replace("Z", "+00:00")).timestamp()
            end_ts = datetime.fromisoformat(end_str.replace("Z", "+00:00")).timestamp() if end_str else start_ts
            whoop_workouts.append((start_ts, float(avg_hr_w), end_ts - start_ts))
        except Exception:
            continue

    def _find_whoop_hr(strava_start_str: str, duration_sec: float) -> float | None:
        """Find matching Whoop workout HR within a 30-minute window of Strava start."""
        try:
            strava_ts = datetime.fromisoformat(strava_start_str.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None
        strava_end_ts = strava_ts + duration_sec
        for w_start, w_hr, w_dur in whoop_workouts:
            w_end = w_start + w_dur
            # Overlap check: activities overlap if one starts before the other ends
            overlap_start = max(strava_ts, w_start)
            overlap_end = min(strava_end_ts, w_end)
            if overlap_end - overlap_start > 300:  # at least 5 min overlap
                return w_hr
        return None

    # --- Compute daily TSS ---
    daily_tss: dict[str, float] = {}
    activities_with_strava_hr = 0
    activities_with_whoop_hr = 0
    activities_no_hr = 0

    for act in activities:
        strava_hr = act.get("average_heartrate")
        moving_time_sec = act.get("moving_time", 0)
        date_str = (act.get("start_date_local") or "")[:10]
        start_date_utc = act.get("start_date", "")

        if not date_str or moving_time_sec == 0:
            continue

        duration_hrs = moving_time_sec / 3600.0

        if strava_hr:
            avg_hr = strava_hr
            activities_with_strava_hr += 1
        else:
            avg_hr = _find_whoop_hr(start_date_utc, moving_time_sec)
            if avg_hr:
                activities_with_whoop_hr += 1
            else:
                activities_no_hr += 1
                continue  # skip — no HR data from either source

        hr_ratio = avg_hr / threshold_hr
        tss = duration_hrs * (hr_ratio ** 2) * 100
        tss = min(tss, 300)  # cap per activity

        daily_tss[date_str] = daily_tss.get(date_str, 0.0) + tss

    # --- Build 90-day time series ---
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=days_back - 1)

    k_ctl = 2 / (42 + 1)  # 42-day constant
    k_atl = 2 / (7 + 1)   # 7-day constant

    # Seed from mean of first 7 days to reduce cold-start effect
    first_7 = []
    for i in range(7):
        d = (start_date + timedelta(days=i)).isoformat()
        first_7.append(daily_tss.get(d, 0.0))
    seed = sum(first_7) / 7 if first_7 else 0.0

    ctl = seed
    atl = seed

    # Track history for trend calculation
    ctl_history: list[float] = []
    atl_history: list[float] = []
    last_7_tss: list[float] = []

    for i in range(days_back):
        d = (start_date + timedelta(days=i)).isoformat()
        tss_today = daily_tss.get(d, 0.0)

        ctl = ctl * (1 - k_ctl) + tss_today * k_ctl
        atl = atl * (1 - k_atl) + tss_today * k_atl

        ctl_history.append(ctl)
        atl_history.append(atl)

        if i >= days_back - 7:
            last_7_tss.append(round(tss_today, 1))

    tsb = ctl - atl

    # 7-day trend: change in CTL and ATL over last 7 days
    trend_ctl = round(ctl_history[-1] - ctl_history[-8], 1) if len(ctl_history) >= 8 else 0.0
    trend_atl = round(atl_history[-1] - atl_history[-8], 1) if len(atl_history) >= 8 else 0.0

    # --- Pattern detection ---
    patterns = await _detect_patterns(daily_tss, ctl, atl, tsb)

    return {
        "ctl": round(ctl, 1),
        "atl": round(atl, 1),
        "tsb": round(tsb, 1),
        "trend_7d_ctl_change": trend_ctl,
        "trend_7d_atl_change": trend_atl,
        "daily_tss_last_7d": last_7_tss,
        "threshold_hr_used": round(threshold_hr, 1),
        "hr_data_coverage": (
            f"{activities_with_strava_hr} activities used Strava HR, "
            f"{activities_with_whoop_hr} used Whoop HR, "
            f"{activities_no_hr} had no HR data and were excluded"
        ),
        "phase": get_phase_label(_weeks_until_race()),
        "patterns": patterns,
        "interpretation": _interpret_load(ctl, atl, tsb),
    }


def _interpret_load(ctl: float, atl: float, tsb: float) -> str:
    """Plain-language interpretation of CTL/ATL/TSB for the agent."""
    parts = []

    if ctl < 20:
        parts.append("Low base fitness — still in early training")
    elif ctl < 40:
        parts.append("Moderate fitness building")
    elif ctl < 60:
        parts.append("Good fitness base for 70.3")
    else:
        parts.append("Strong fitness — well-prepared for race distance")

    if tsb < -25:
        parts.append("carrying heavy fatigue (high overreaching risk)")
    elif tsb < -10:
        parts.append("moderately fatigued (normal training load)")
    elif tsb < 5:
        parts.append("near-neutral form (balanced load)")
    elif tsb < 20:
        parts.append("fresh and ready — good form window")
    else:
        parts.append("very fresh — possibly under-training or tapering")

    return "; ".join(parts)


async def _detect_patterns(
    daily_tss: dict[str, float],
    ctl: float,
    atl: float,
    tsb: float,
) -> list[str]:
    """Detect noteworthy training patterns from load + recovery data."""
    patterns = []

    # Overreaching: ATL much higher than CTL
    if ctl > 0 and atl > ctl * 1.5:
        patterns.append(
            f"Overreaching risk: acute load ({atl:.0f}) is >50% above chronic load ({ctl:.0f}). "
            "Consider 1-2 easier days."
        )

    if tsb < -25:
        patterns.append(
            f"Heavy fatigue: TSB is {tsb:.0f}. Performance likely suppressed — a recovery day will help."
        )

    if tsb > 20:
        patterns.append(
            f"Very fresh: TSB is +{tsb:.0f}. Good time to do a quality session or race simulation."
        )

    weeks_to_race = _weeks_until_race()
    if 2 <= weeks_to_race <= 4 and 5 <= tsb <= 20:
        patterns.append(
            f"Optimal taper window: TSB is +{tsb:.0f} with {weeks_to_race} weeks to race. Hold this form."
        )

    # Recovery patterns require Whoop data
    try:
        recovery_data = await whoop.get_recovery(days=14)
        scored = [
            r for r in recovery_data
            if r.get("score_state") == "SCORED" and r.get("score")
        ]
        scored.sort(key=lambda r: r.get("created_at", ""))

        if scored:
            scores_7d = [r["score"]["recovery_score"] for r in scored[-7:]]
            low_recovery_days = sum(1 for s in scores_7d if s < 50)
            if low_recovery_days >= 4:
                patterns.append(
                    f"Chronic under-recovery: {low_recovery_days}/7 days with recovery <50%. "
                    "Investigate sleep quality, stress, or training load."
                )

            # HRV declining streak
            hrv_values = [
                (r.get("created_at", "")[:10], r["score"].get("hrv_rmssd_milli"))
                for r in scored[-5:]
                if r["score"].get("hrv_rmssd_milli")
            ]
            if len(hrv_values) >= 3:
                recent_hrv = [v for _, v in hrv_values[-3:]]
                if recent_hrv[0] > recent_hrv[1] > recent_hrv[2]:
                    patterns.append(
                        f"HRV declining 3 consecutive days "
                        f"({recent_hrv[0]:.0f} → {recent_hrv[1]:.0f} → {recent_hrv[2]:.0f} ms). "
                        "Likely accumulating fatigue — consider an easy day."
                    )

            # RHR creeping up
            rhr_14d = [r["score"].get("resting_heart_rate") for r in scored if r["score"].get("resting_heart_rate")]
            if len(rhr_14d) >= 7:
                avg_14d = sum(rhr_14d) / len(rhr_14d)
                avg_7d = sum(rhr_14d[-7:]) / 7
                if avg_7d >= avg_14d + 5:
                    patterns.append(
                        f"Resting HR elevated: 7-day avg ({avg_7d:.0f} bpm) is "
                        f"{avg_7d - avg_14d:.0f} bpm above 14-day avg ({avg_14d:.0f} bpm). "
                        "Systemic fatigue signal."
                    )
    except Exception:
        pass

    return patterns


# ---------------------------------------------------------------------------
# Race readiness score (0–100)
# ---------------------------------------------------------------------------

async def compute_race_readiness() -> dict:
    """
    Composite race readiness score combining:
    - Fitness (CTL): how much training base has been built
    - Form (TSB): freshness vs fatigue balance
    - Recovery: 7-day average Whoop recovery score
    - Race proximity: how many weeks remain

    Returns score (0-100), component breakdown, label, and interpretation.
    """
    load = await compute_training_load()
    ctl = load["ctl"]
    tsb = load["tsb"]
    weeks = _weeks_until_race()

    # --- Component 1: Fitness (CTL) → 0-25 ---
    # CTL ~42 = full score for 70.3 finish goal
    fitness_score = min(25.0, ctl * 0.6)

    # --- Component 2: Form (TSB) → 0-25 ---
    # Optimal: TSB in [-5, +20]. Taper linearly to 0 outside [-30, +30].
    if -5 <= tsb <= 20:
        form_score = 25.0
    elif tsb < -5:
        form_score = max(0.0, 25.0 * (1 - abs(tsb + 5) / 25))
    else:  # tsb > 20
        form_score = max(0.0, 25.0 * (1 - (tsb - 20) / 10))

    # --- Component 3: Recovery → 0-25 ---
    recovery_score = 12.0  # default if Whoop unavailable
    try:
        recovery_summary = await whoop.get_recovery_summary(days=7)
        avg_recovery = recovery_summary["recovery"].get("avg_score")
        if avg_recovery is not None:
            if avg_recovery >= 67:
                recovery_score = 25.0
            elif avg_recovery >= 34:
                recovery_score = 15.0
            else:
                recovery_score = 5.0
    except Exception:
        pass

    # --- Component 4: Race proximity → 0-25 ---
    if 2 <= weeks <= 6:
        proximity_score = 25.0    # prime window
    elif 7 <= weeks <= 12:
        proximity_score = 15.0
    elif 13 <= weeks <= 20:
        proximity_score = 8.0
    else:
        proximity_score = 3.0    # too far out or race day

    total = fitness_score + form_score + recovery_score + proximity_score

    # --- Status label ---
    if total >= 75:
        status = "Race Ready"
    elif total >= 55:
        status = "Building Well"
    elif total >= 35:
        status = "Developing"
    else:
        status = "Early Stage"

    # --- Interpretation ---
    interpretation = _interpret_readiness(ctl, tsb, weeks, total)

    return {
        "total_score": round(total),
        "fitness_score": round(fitness_score, 1),
        "form_score": round(form_score, 1),
        "recovery_score": round(recovery_score, 1),
        "proximity_score": round(proximity_score, 1),
        "status_label": status,
        "weeks_to_race": weeks,
        "phase": get_phase_label(weeks),
        "interpretation": interpretation,
        "load_summary": {
            "ctl": ctl,
            "atl": load["atl"],
            "tsb": tsb,
            "patterns": load["patterns"],
        },
    }


def _interpret_readiness(ctl: float, tsb: float, weeks: int, score: float) -> str:
    if weeks > 16:
        return (
            f"Still in early base building ({weeks} weeks out). "
            f"CTL of {ctl:.0f} is your current fitness — focus on consistent volume "
            "across all three disciplines before adding intensity."
        )
    if weeks > 8:
        return (
            f"In the build phase with {weeks} weeks to go. "
            f"CTL {ctl:.0f} and TSB {tsb:+.0f} — "
            + ("good load balance." if -15 <= tsb <= 5 else
               "consider a recovery week soon." if tsb < -15 else
               "you have room to add more training stress.")
        )
    if weeks > 3:
        return (
            f"Peak phase — {weeks} weeks to race day. "
            f"TSB {tsb:+.0f}: "
            + ("perfect freshness for race-specific work." if 0 <= tsb <= 15 else
               "still carrying fatigue — prioritize sleep and easy sessions." if tsb < 0 else
               "quite fresh — add one quality session before tapering.")
        )
    return (
        f"Taper time — {weeks} week{'s' if weeks != 1 else ''} to go. "
        "Reduce volume by 40%, keep a few intensity efforts, trust your training."
    )
