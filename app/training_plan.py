"""
Training plan generator.

Builds periodized training plans based on:
  - Real Strava training history (current fitness level)
  - Whoop recovery trends (how the athlete is handling load)
  - Race goal and athlete preferences
"""

import json
from datetime import datetime, timezone

from app.clients import strava, whoop
from app.metrics import compute_training_load, get_phase_label

# ---------------------------------------------------------------------------
# Athlete race config — hardcoded for now, could be a settings page later
# ---------------------------------------------------------------------------

RACE_CONFIG = {
    "race_name": "Ironman 70.3 Vitoria-Gasteiz",
    "race_date": "2026-07-12",
    "distances": {
        "swim_km": 1.9,
        "bike_km": 90,
        "run_km": 21.1,
    },
    "goal": "Finish comfortably, no specific time goal",
    "availability": [
        "Weekday mornings before work (~60-90 min)",
        "Weekday evenings after work (~60-90 min)",
        "Weekends (long sessions, 2-4 hours)",
    ],
    "athlete_context": (
        "Based in Amsterdam. Rides a Cube Attain road bike. "
        "Has access to a pool for swimming. "
        "First Ironman 70.3. Training with girlfriend who is also athletic. "
        "Works full-time as an analyst with demanding schedule."
    ),
}


def get_weeks_until_race() -> int:
    race_date = datetime.strptime(RACE_CONFIG["race_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return max(0, (race_date - now).days // 7)


async def gather_fitness_snapshot() -> dict:
    """
    Pull current fitness data from Strava and Whoop to inform the plan.
    """
    snapshot = {}

    # Recent training (last 30 days for a good picture)
    try:
        snapshot["training_30d"] = await strava.get_training_summary(days=30)
    except Exception as e:
        snapshot["training_30d"] = {"error": str(e)}

    # Recent training (last 7 days for current week)
    try:
        snapshot["training_7d"] = await strava.get_training_summary(days=7)
    except Exception as e:
        snapshot["training_7d"] = {"error": str(e)}

    # All-time stats
    try:
        athlete = await strava.get_athlete()
        snapshot["all_time_stats"] = await strava.get_athlete_stats(athlete["id"])
        snapshot["athlete_weight_kg"] = athlete.get("weight")
    except Exception as e:
        snapshot["all_time_stats"] = {"error": str(e)}

    # Recovery trends (last 14 days)
    try:
        snapshot["recovery_14d"] = await whoop.get_recovery_summary(days=14)
    except Exception as e:
        snapshot["recovery_14d"] = {"error": str(e)}

    # Training load metrics (CTL/ATL/TSB)
    try:
        snapshot["training_load"] = await compute_training_load()
    except Exception as e:
        snapshot["training_load"] = {"error": str(e)}

    return snapshot


def build_plan_prompt(snapshot: dict, plan_type: str = "full") -> str:
    """
    Build the prompt that will generate the training plan.
    """
    weeks_left = get_weeks_until_race()

    load = snapshot.get("training_load", {})
    ctl = load.get("ctl", "N/A")
    atl = load.get("atl", "N/A")
    tsb = load.get("tsb", "N/A")
    phase = get_phase_label(weeks_left)

    prompt = f"""You are an experienced triathlon coach creating a training plan.

## RACE
- **Race:** {RACE_CONFIG['race_name']}
- **Date:** {RACE_CONFIG['race_date']} ({weeks_left} weeks away)
- **Distances:** {RACE_CONFIG['distances']['swim_km']}km swim, {RACE_CONFIG['distances']['bike_km']}km bike, {RACE_CONFIG['distances']['run_km']}km run
- **Goal:** {RACE_CONFIG['goal']}
- **Current phase:** {phase}

## ATHLETE CONTEXT
{RACE_CONFIG['athlete_context']}

## TRAINING AVAILABILITY
{chr(10).join('- ' + a for a in RACE_CONFIG['availability'])}

## TRAINING LOAD METRICS
- CTL (fitness): {ctl}
- ATL (fatigue): {atl}
- TSB (form): {tsb}
- Phase: {phase}
{('- Patterns: ' + '; '.join(load['patterns'])) if load.get('patterns') else ''}

## CURRENT FITNESS (from real Strava + Whoop data)
{json.dumps(snapshot, indent=2, default=str)}

## YOUR TASK
"""

    if plan_type == "full":
        prompt += f"""Generate a **periodized training plan** for the remaining {weeks_left} weeks until race day.

Structure the plan in phases:
1. **Base phase** — build aerobic endurance across all three disciplines
2. **Build phase** — increase sport-specific intensity and volume
3. **Peak phase** — race-specific sessions, brick workouts (bike→run)
4. **Taper phase** — reduce volume, maintain intensity, fresh for race day

For each phase, provide:
- Duration (which weeks)
- Weekly structure (which days = which sport/session type)
- Key sessions with approximate duration and intensity
- Weekly volume targets (km or hours per sport)

Important guidelines:
- Base the starting volume on the athlete's ACTUAL current training from the data above
- Progress volume by no more than 10% per week
- Include at least 1 rest day per week
- Include brick workouts (bike→run) in build and peak phases
- Factor in recovery data — if HRV is trending down or recovery is poor, note where to add extra rest
- Keep weekday sessions 60-90 min, weekend sessions can be 2-4 hours
- Be specific with session descriptions (not just "easy ride" but "Zone 2 ride, flat terrain, 70-80% max HR")
"""

    elif plan_type == "next_week":
        prompt += """Generate a **detailed plan for next week only**.

For each day (Monday through Sunday), provide:
- Sport (swim/bike/run/rest)
- Session type and description
- Duration
- Intensity zone
- Key focus

Base this on where the athlete is in their training cycle relative to race day,
and factor in their current recovery state from Whoop data.
"""

    elif plan_type == "adjust":
        prompt += """Based on the current fitness and recovery data, suggest **adjustments** 
to the athlete's current training:

- Are they doing enough volume for their race goal?
- Is the balance between swim/bike/run appropriate?
- Are there signs of overtraining or under-recovery?
- What should they add, reduce, or change?
- Any specific sessions they should prioritize in the next 2 weeks?
"""

    return prompt
