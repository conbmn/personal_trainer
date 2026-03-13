# Fitness Agent 🚴‍♂️

AI-powered personal training coach connecting **Strava** + **Whoop** + **OpenAI** via FastAPI. Built for Ironman 70.3 Vitoria-Gasteiz (July 2026) preparation.

The agent pulls real training and recovery data, reasons about it using GPT-4o with function calling, and gives specific, data-driven coaching advice through a chat interface.

## Features

- **Strava integration** — activities, distances, elevation, heart rate, training load
- **Whoop integration** — recovery scores, HRV, resting heart rate, sleep quality
- **AI coaching agent** — 9 tools across both platforms, answers questions using real data
- **Training plan generator** — periodized Ironman 70.3 plans based on current fitness
- **Conversation memory** — multi-turn chat with full context
- **Chat UI** — dark-themed web interface at localhost:8000

## Quick Start

```bash
# 1. Create environment
conda create -n personal_trainer python=3.11
conda activate personal_trainer

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up config
cp .env.example .env
# Edit .env with your Strava, Whoop, and OpenAI credentials

# 4. Run the server
uvicorn app.main:app --reload --port 8000
```

## Connect Your Accounts

1. Open http://localhost:8000/docs — interactive API docs
2. Visit http://localhost:8000/auth/strava/login — connect Strava
3. Visit http://localhost:8000/auth/whoop/login — connect Whoop (requires HTTPS, use ngrok)
4. Check http://localhost:8000/auth/status — verify both are connected

**Note:** Whoop requires HTTPS for OAuth redirects. Use `ngrok http 8000` to create a tunnel, update `APP_BASE_URL` in `.env` to the ngrok URL, then auth. Switch back to `http://localhost:8000` after.

## Project Structure

```
personal_trainer/
├── app/
│   ├── main.py              # FastAPI app + CORS + static file serving
│   ├── config.py            # Settings from .env (pydantic-settings)
│   ├── auth.py              # OAuth 2.0 (auth URLs, token exchange, refresh, state)
│   ├── token_store.py       # JSON-based token persistence
│   ├── agent.py             # LLM agent loop with OpenAI function calling
│   ├── training_plan.py     # Ironman 70.3 periodized plan generator
│   ├── clients/
│   │   ├── strava.py        # Strava API v3 client
│   │   └── whoop.py         # Whoop API v2 client
│   ├── routes/
│   │   ├── auth_routes.py   # /auth/* — OAuth flow endpoints
│   │   ├── strava_routes.py # /strava/* — training data endpoints
│   │   ├── whoop_routes.py  # /whoop/* — recovery data endpoints
│   │   └── agent_routes.py  # /agent/chat — AI coach endpoint
│   └── static/
│       └── index.html       # Chat UI
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Agent Tools

The AI coach has 9 tools it can call autonomously:

| Tool | Source | Description |
|------|--------|-------------|
| get_training_summary | Strava | Recent training volume, distances, HR |
| get_athlete_profile | Strava | Athlete profile and weight |
| get_athlete_stats | Strava | All-time and YTD totals |
| get_activity_detail | Strava | Full details for a specific activity |
| get_recovery_summary | Whoop | Recovery scores, HRV, RHR, sleep stats |
| get_whoop_profile | Whoop | Profile and body measurements |
| get_sleep_data | Whoop | Detailed sleep stages and performance |
| get_whoop_workouts | Whoop | Workout strain and HR zones |
| generate_training_plan | Both | Periodized Ironman 70.3 plan from real data |

## Example Prompts

- "How was my training this week?"
- "Should I train hard today or take it easy?"
- "Generate my Ironman 70.3 training plan"
- "What should I train next week?"
- "Am I on track for my race? What should I adjust?"
- "Compare my last 7 days vs the previous 7 days"

## Built With

- **FastAPI** — async web framework
- **OpenAI GPT-4o** — LLM with function calling
- **httpx** — async HTTP client for API calls
- **pydantic-settings** — configuration management

## Roadmap

- [x] OAuth auth flow + token management (Strava + Whoop)
- [x] Strava API client (activities, stats, summaries)
- [x] Whoop API client (recovery, sleep, workouts)
- [x] OpenAI agent with function calling (9 tools)
- [x] Chat UI with conversation memory
- [x] Ironman 70.3 training plan generator
- [ ] Dashboard with charts (volume trends, HRV, recovery)
- [ ] Deploy to cloud (Railway/Render)
- [ ] Telegram bot for mobile access
