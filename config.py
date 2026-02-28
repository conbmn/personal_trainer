"""
Centralized configuration — reads from .env file automatically.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Strava
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_auth_url: str = "https://www.strava.com/oauth/authorize"
    strava_token_url: str = "https://www.strava.com/oauth/token"
    strava_scopes: str = "read,activity:read_all"

    # Whoop
    whoop_client_id: str = ""
    whoop_client_secret: str = ""
    whoop_auth_url: str = "https://api.prod.whoop.com/oauth/oauth2/auth"
    whoop_token_url: str = "https://api.prod.whoop.com/oauth/oauth2/token"
    whoop_scopes: str = "read:recovery read:sleep read:workout read:profile read:body_measurement"

    # App
    app_base_url: str = "http://localhost:8000"
    secret_key: str = "change-me"

    # OpenAI (Phase 3)
    openai_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton — import this everywhere
settings = Settings()
