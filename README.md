# Fitness Agent 🚴‍♂️

Personal training agent connecting **Strava** + **Whoop** + **OpenAI** via FastAPI.

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up config
cp .env.example .env
# Edit .env with your actual credentials

# 4. Run the server
uvicorn app.main:app --reload --port 8000
```

## Connect Your Accounts

1. Open http://localhost:8000/docs — interactive API docs
2. Visit http://localhost:8000/auth/strava/login — connect Strava
3. Visit http://localhost:8000/auth/whoop/login — connect Whoop
4. Check http://localhost:8000/auth/status — verify both are connected

## Project Structure

```
fitness-agent/
├── app/
│   ├── main.py            # FastAPI app entry point
│   ├── config.py          # Settings from .env
│   ├── auth.py            # OAuth logic (auth URLs, token exchange, refresh)
│   ├── token_store.py     # JSON-based token persistence
│   ├── routes/
│   │   └── auth_routes.py # /auth/* endpoints
│   └── clients/           # (Phase 2) Strava & Whoop API wrappers
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Phases

- [x] **Phase 1** — OAuth auth flow + token management
- [ ] **Phase 2** — Strava & Whoop API clients
- [ ] **Phase 3** — OpenAI agent with function calling
- [ ] **Phase 4** — Scheduling, notifications, polish
