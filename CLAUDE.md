# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered personal triathlon coaching agent integrating Strava (training data) and Whoop (recovery data) with OpenAI function calling. Built for Ironman 70.3 race preparation, training load balancing, and recovery-informed scheduling. Includes a dashboard view with live CTL/ATL/TSB metrics, race readiness score, and 30-day Whoop trends.

## Running the Project

```bash
conda activate personal_trainer
uvicorn app.main:app --reload --port 8000
```

- Web UI: http://localhost:8000
- API docs: http://localhost:8000/docs

**First-time setup:**
```bash
conda create -n personal_trainer python=3.11
pip install -r requirements.txt
cp .env.example .env  # then fill in credentials
```

**Whoop OAuth requires HTTPS** — use `ngrok http 8000` and update `APP_BASE_URL` in `.env`.

## Architecture

```
FastAPI (app/main.py)
├── app/routes/             — HTTP endpoints
│   ├── auth_routes.py      — OAuth callbacks for Strava and Whoop
│   ├── strava_routes.py    — Strava data endpoints
│   ├── whoop_routes.py     — Whoop data endpoints
│   ├── agent_routes.py     — Chat agent endpoint
│   └── dashboard_routes.py — GET /api/dashboard (fan-out: Strava + Whoop + metrics)
├── app/clients/            — Async httpx API clients (strava.py, whoop.py)
├── app/agent.py            — OpenAI agent loop with 11 function-calling tools
├── app/metrics.py          — CTL/ATL/TSB training load computation + race readiness score
├── app/auth.py             — OAuth 2.0 service for Strava and Whoop
├── app/token_store.py      — JSON-based token persistence (token_store.json)
├── app/training_plan.py    — Ironman 70.3 periodized plan generator
├── app/config.py           — Pydantic Settings (reads .env)
└── app/static/             — Chat + dashboard UI (index.html)
```

**Agent tools** (defined in `app/agent.py`): 4 Strava tools, 4 Whoop tools, 2 metrics tools (`get_training_load`, `get_race_readiness`), 1 training plan generator. The agent loop sends user message + conversation history → executes tool calls → feeds results back → returns final response.

**Metrics module** (`app/metrics.py`):
- `compute_training_load()` — computes CTL (42-day EWA), ATL (7-day EWA), TSB from 90 days of Strava HR data; falls back to Whoop HR when Strava HR is missing; detects patterns (overreaching, HRV decline, RHR trend, under-recovery)
- `compute_race_readiness()` — 0-100 composite score from CTL, TSB, 7-day Whoop recovery avg, and weeks to race
- `get_phase_label(weeks)` — returns Base / Build / Peak / Taper

**Dashboard** (`GET /api/dashboard`): fans out in parallel to Strava, Whoop, and metrics; returns today's recovery block, last 7 activities (merged Strava + Whoop-only), current-week volume by sport, race countdown + readiness, CTL/ATL/TSB, and 30-day Whoop trends.

**Token management**: Tokens stored in `token_store.json` (gitignored), auto-refreshed 5 minutes before expiry.

## Key Configuration

Environment variables in `.env`:
- `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`
- `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`
- `OPENAI_API_KEY`
- `APP_BASE_URL` — must be HTTPS for Whoop OAuth

**Race config** is hardcoded in `app/training_plan.py`: Ironman 70.3 Vitoria-Gasteiz, July 12, 2026.

## No Tests or Linting Configured

There is no test suite or linter configuration. The project uses standard Python async patterns throughout — all API calls use `httpx.AsyncClient`.
