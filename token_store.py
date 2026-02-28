"""
Simple JSON-based token storage.

Stores OAuth tokens per provider in a local JSON file.
Good enough for a personal project — swap for SQLite/Postgres later if needed.
"""

import json
import time
from pathlib import Path
from typing import Optional

STORE_PATH = Path(__file__).parent.parent / "token_store.json"


def _load_store() -> dict:
    if STORE_PATH.exists():
        return json.loads(STORE_PATH.read_text())
    return {}


def _save_store(store: dict) -> None:
    STORE_PATH.write_text(json.dumps(store, indent=2))


def save_tokens(provider: str, token_data: dict) -> None:
    """
    Save tokens for a provider (strava / whoop).

    Expects token_data to contain at least:
      - access_token
      - refresh_token
      - expires_in (seconds until expiry) OR expires_at (unix timestamp)
    """
    store = _load_store()

    # Normalize expiry to a unix timestamp
    if "expires_at" not in token_data and "expires_in" in token_data:
        token_data["expires_at"] = int(time.time()) + token_data["expires_in"]

    store[provider] = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at": token_data.get("expires_at", 0),
    }
    _save_store(store)


def get_tokens(provider: str) -> Optional[dict]:
    """Get stored tokens for a provider. Returns None if not found."""
    store = _load_store()
    return store.get(provider)


def is_token_expired(provider: str) -> bool:
    """Check if the access token for a provider is expired (with 5min buffer)."""
    tokens = get_tokens(provider)
    if not tokens:
        return True
    return time.time() > (tokens["expires_at"] - 300)  # 5 min buffer


def delete_tokens(provider: str) -> None:
    """Remove tokens for a provider."""
    store = _load_store()
    store.pop(provider, None)
    _save_store(store)
