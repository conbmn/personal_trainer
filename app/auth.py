"""
OAuth 2.0 service for Strava and Whoop.

Handles:
  - Building authorization URLs (redirect user to provider login)
  - Exchanging authorization codes for tokens
  - Refreshing expired tokens
"""

import secrets
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.token_store import save_tokens, get_tokens, is_token_expired

# Simple in-memory state storage (fine for single-user personal app)
_pending_states: set[str] = set()


# ---------------------------------------------------------------------------
# Provider configs — keeps the rest of the code provider-agnostic
# ---------------------------------------------------------------------------

PROVIDERS = {
    "strava": {
        "client_id": lambda: settings.strava_client_id,
        "client_secret": lambda: settings.strava_client_secret,
        "auth_url": settings.strava_auth_url,
        "token_url": settings.strava_token_url,
        "scopes": settings.strava_scopes,
    },
    "whoop": {
        "client_id": lambda: settings.whoop_client_id,
        "client_secret": lambda: settings.whoop_client_secret,
        "auth_url": settings.whoop_auth_url,
        "token_url": settings.whoop_token_url,
        "scopes": settings.whoop_scopes,
    },
}


def get_authorize_url(provider: str) -> str:
    """
    Build the URL to redirect the user to for OAuth authorization.
    """
    cfg = PROVIDERS[provider]
    redirect_uri = f"{settings.app_base_url}/auth/{provider}/callback"

    params = {
        "client_id": cfg["client_id"](),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": cfg["scopes"],
    }

    # Whoop requires a state parameter (exactly 8 chars)
    if provider == "whoop":
        state = secrets.token_hex(4)  # 8 hex chars
        params["state"] = state
        _pending_states.add(state)

    return f"{cfg['auth_url']}?{urlencode(params)}"


def validate_state(state: str | None) -> bool:
    """Check and consume a state parameter."""
    if state is None:
        return True  # Strava doesn't use state
    if state in _pending_states:
        _pending_states.discard(state)
        return True
    return False


async def exchange_code_for_tokens(provider: str, code: str) -> dict:
    """
    Exchange the authorization code (from callback) for access + refresh tokens.
    This is step 2 of the OAuth flow.
    """
    cfg = PROVIDERS[provider]
    redirect_uri = f"{settings.app_base_url}/auth/{provider}/callback"

    payload = {
        "client_id": cfg["client_id"](),
        "client_secret": cfg["client_secret"](),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(cfg["token_url"], data=payload)
        response.raise_for_status()
        token_data = response.json()

    save_tokens(provider, token_data)
    return token_data


async def refresh_tokens(provider: str) -> dict:
    """
    Use the refresh_token to get a new access_token.
    Called automatically when the current token is expired.
    """
    cfg = PROVIDERS[provider]
    tokens = get_tokens(provider)

    if not tokens or not tokens.get("refresh_token"):
        raise ValueError(f"No refresh token stored for {provider}. Re-authenticate.")

    payload = {
        "client_id": cfg["client_id"](),
        "client_secret": cfg["client_secret"](),
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(cfg["token_url"], data=payload)
        response.raise_for_status()
        token_data = response.json()

    # Some providers (Strava) rotate the refresh token — always save the new one
    if "refresh_token" not in token_data:
        token_data["refresh_token"] = tokens["refresh_token"]

    save_tokens(provider, token_data)
    return token_data


async def get_valid_access_token(provider: str) -> str:
    """
    Get a valid access token — refreshes automatically if expired.
    This is what your API clients should call.
    """
    if is_token_expired(provider):
        token_data = await refresh_tokens(provider)
        return token_data["access_token"]

    tokens = get_tokens(provider)
    if not tokens:
        raise ValueError(f"Not authenticated with {provider}. Visit /auth/{provider}/login")
    return tokens["access_token"]
