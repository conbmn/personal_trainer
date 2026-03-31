"""
Fitness Agent — OpenAI-powered training assistant.

Uses function calling to let the LLM decide when to pull Strava and Whoop data.
The agent loop handles tool calls automatically until the LLM has
enough info to give a final answer.
"""

import json
from openai import AsyncOpenAI

from app.config import settings
from app.clients import strava
from app.clients import whoop
from app.training_plan import gather_fitness_snapshot, build_plan_prompt, get_weeks_until_race, RACE_CONFIG
from app.metrics import get_phase_label
from app import metrics

client = AsyncOpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = f"""You are an expert triathlon coach with deep knowledge of periodization, training physiology, and data-driven coaching.

## ATHLETE & RACE
- Race: {RACE_CONFIG['race_name']} on {RACE_CONFIG['race_date']} ({get_weeks_until_race()} weeks away)
- Format: 70.3 — 1.9km swim / 90km bike / 21.1km run. Goal: finish comfortably.
- Context: {RACE_CONFIG['athlete_context']}
- Current training phase: **{get_phase_label(get_weeks_until_race())}** ({get_weeks_until_race()} weeks out)

## TOOL ROUTING — always fetch real data before responding
- `get_training_load` → CTL/ATL/TSB and pattern alerts. Use for: fitness trends, fatigue, overtraining, "am I building?", trend questions.
- `get_race_readiness` → 0-100 composite score. Use for: "am I on track?", "how prepared am I?", race countdown questions.
- `get_training_summary(days)` → raw activity list. Use for: "what did I do this week?", specific sessions, volume by sport.
- `get_recovery_summary(days)` → Whoop daily recovery, HRV, sleep. Use for: today's readiness, sleep quality, HRV questions.
- `get_sleep_data` → detailed sleep stages. Use for: sleep-specific deep dives.
- `generate_training_plan` → full/next_week/adjust plans. Use when the athlete asks for a structured plan.
- For "should I train today?" → call BOTH `get_training_load` AND `get_recovery_summary`.
- For any training recommendation → call at least one tool first. Never guess.

## PERIODIZATION AWARENESS
- Base (>16 weeks): Build aerobic volume, Zone 2 work, all three sports equally.
- Build (9-16 weeks): Add intensity, introduce brick workouts (bike→run), sport-specific sessions.
- Peak (4-8 weeks): Race-pace efforts, long brick sessions, reduce easy volume.
- Taper (≤3 weeks): Drop volume 40%, keep 2-3 intensity sessions, trust the training.

## PATTERN DETECTION — proactively flag these when you see them in data
- HRV declining 3+ consecutive days → accumulated fatigue, recommend easy day or rest
- TSB < -25 → heavy fatigue, performance suppressed, recovery priority
- ATL > 1.5 × CTL → overreaching risk, recommend recovery week
- 4+ of last 7 recovery scores < 50 → chronic under-recovery, investigate sleep/stress
- TSB +5 to +20 near race (2-4 weeks out) → optimal freshness window, don't add load
- RHR trending up 5+ bpm over 2 weeks → systemic fatigue signal

## RESPONSE STYLE
- Always cite actual numbers: CTL, TSB, HRV, distances, recovery scores.
- Be direct: "Your TSB is -18, which means significant fatigue. I'd recommend..."
- Flag patterns proactively even if the user didn't ask.
- Use metric units (km, bpm, ms for HRV).
- For responses longer than 3 sentences, use ## headers and bullet points for scannability.
- Reference specific weeks remaining in every training plan or phase discussion.
- Whoop recovery zones: Red (<34) = rest, Yellow (34-66) = moderate OK, Green (67+) = go hard.
"""

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    # --- Strava tools ---
    {
        "type": "function",
        "function": {
            "name": "get_training_summary",
            "description": (
                "Get a structured summary of recent Strava training including ride/run/swim "
                "totals, distances, time, elevation, heart rate, and individual activities. "
                "Use this for questions about training load, volume, or recent performance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 7)",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_athlete_profile",
            "description": "Get the athlete's Strava profile (name, city, weight, etc.)",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_athlete_stats",
            "description": (
                "Get all-time Strava athlete stats including total rides, runs, swims, "
                "and year-to-date totals. Use for big-picture questions."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_activity_detail",
            "description": (
                "Get full details for a specific Strava activity by ID. "
                "Use when the user asks about a particular ride or workout."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "activity_id": {
                        "type": "integer",
                        "description": "The Strava activity ID",
                    }
                },
                "required": ["activity_id"],
            },
        },
    },
    # --- Whoop tools ---
    {
        "type": "function",
        "function": {
            "name": "get_recovery_summary",
            "description": (
                "Get a structured Whoop recovery summary including recovery scores, "
                "HRV, resting heart rate, sleep duration/performance, and daily strain. "
                "Use for questions about recovery, readiness, sleep quality, or whether to train."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 7)",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_whoop_profile",
            "description": "Get the user's Whoop profile and body measurements (height, weight, max HR).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sleep_data",
            "description": (
                "Get detailed Whoop sleep data including sleep stages, sleep needed, "
                "respiratory rate, and sleep performance. Use for sleep-specific questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 7)",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_whoop_workouts",
            "description": (
                "Get Whoop workout data including strain, heart rate zones, and sport type. "
                "Use for Whoop-specific workout metrics (complements Strava activity data)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 7)",
                    }
                },
            },
        },
    },
    # --- Training load & readiness tools ---
    {
        "type": "function",
        "function": {
            "name": "get_training_load",
            "description": (
                "Compute CTL (chronic training load = fitness), ATL (acute training load = fatigue), "
                "and TSB (training stress balance = form/freshness) from 90 days of Strava heart rate data. "
                "Also returns pattern warnings (overreaching, HRV decline, under-recovery) and a "
                "plain-language interpretation. Use for any question about fitness trends, fatigue levels, "
                "peaking, overtraining, or 'should I build or rest?'. More insightful than raw summary for trends."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_race_readiness",
            "description": (
                "Compute a 0-100 race readiness score combining fitness (CTL), form (TSB), "
                "7-day Whoop recovery trend, and weeks to race. Returns total score, component breakdown, "
                "a status label (Race Ready / Building Well / Developing / Early Stage), and interpretation. "
                "Use when the athlete asks how prepared they are, whether they're on track, or for a "
                "race countdown assessment."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    # --- Training plan tools ---
    {
        "type": "function",
        "function": {
            "name": "generate_training_plan",
            "description": (
                "Generate a full periodized training plan for the athlete's Ironman 70.3. "
                "Pulls real Strava and Whoop data to base the plan on current fitness. "
                "Use when the athlete asks for a training plan, program, or schedule."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_type": {
                        "type": "string",
                        "enum": ["full", "next_week", "adjust"],
                        "description": (
                            "'full' = complete periodized plan until race day. "
                            "'next_week' = detailed plan for next week only. "
                            "'adjust' = suggestions to adjust current training."
                        ),
                    }
                },
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

async def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool call and return the result as a JSON string."""
    try:
        # Strava tools
        if name == "get_training_summary":
            result = await strava.get_training_summary(days=arguments.get("days", 7))
        elif name == "get_athlete_profile":
            result = await strava.get_athlete()
        elif name == "get_athlete_stats":
            athlete = await strava.get_athlete()
            result = await strava.get_athlete_stats(athlete["id"])
        elif name == "get_activity_detail":
            result = await strava.get_activity_detail(arguments["activity_id"])
        # Whoop tools
        elif name == "get_recovery_summary":
            result = await whoop.get_recovery_summary(days=arguments.get("days", 7))
        elif name == "get_whoop_profile":
            profile = await whoop.get_profile()
            body = await whoop.get_body_measurements()
            result = {**profile, **body}
        elif name == "get_sleep_data":
            result = await whoop.get_sleep(days=arguments.get("days", 7))
        elif name == "get_whoop_workouts":
            result = await whoop.get_workouts(days=arguments.get("days", 7))
        # Training load & readiness tools
        elif name == "get_training_load":
            result = await metrics.compute_training_load()
        elif name == "get_race_readiness":
            result = await metrics.compute_race_readiness()
        # Training plan tools
        elif name == "generate_training_plan":
            plan_type = arguments.get("plan_type", "full")
            snapshot = await gather_fitness_snapshot()
            prompt = build_plan_prompt(snapshot, plan_type=plan_type)
            # Return the prompt as the "data" — the LLM will use it to generate the plan
            result = {"plan_prompt": prompt, "weeks_until_race": get_weeks_until_race()}
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as e:
        result = {"error": str(e)}

    return json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

async def run_agent(user_message: str, conversation_history: list | None = None) -> str:
    """
    Run the agent loop.

    1. Send the user's message (+ history) to OpenAI
    2. If the model wants to call tools, execute them and feed results back
    3. Repeat until the model gives a final text response
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if conversation_history:
        messages.extend(conversation_history)

    messages.append({"role": "user", "content": user_message})

    while True:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
        )

        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            return msg.content

        for call in msg.tool_calls:
            arguments = json.loads(call.function.arguments)
            result = await execute_tool(call.function.name, arguments)

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })
