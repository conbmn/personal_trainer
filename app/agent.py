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

client = AsyncOpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = f"""You are a knowledgeable cycling and triathlon coach assistant.
You have access to the user's Strava training data AND Whoop recovery/sleep data.
Use the available tools to pull real data before answering questions.

The athlete is training for {RACE_CONFIG['race_name']} on {RACE_CONFIG['race_date']} ({get_weeks_until_race()} weeks away).
It's a 70.3: 1.9km swim, 90km bike, 21.1km run. Goal is to finish comfortably.

Guidelines:
- Always fetch data before making training recommendations — never guess.
- For training questions, pull Strava data. For recovery/sleep/readiness, pull Whoop data.
- For "should I train today?" questions, pull BOTH Strava and Whoop data.
- Be specific: reference actual distances, times, heart rates, recovery scores, and HRV.
- Use metric units (km, meters, bpm, ms for HRV).
- Be concise but insightful — like a good coach talking to an athlete.
- Whoop recovery zones: Red (<34) = take it easy, Yellow (34-66) = moderate OK, Green (67+) = go hard.
- If you notice patterns (e.g., declining HRV, poor sleep streak, overtraining), flag them.
- When asked about training plans, use the training plan tools to generate data-driven plans.
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
