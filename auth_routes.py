"""
Auth routes — handles the browser-based OAuth flow.

Endpoints:
  GET /auth/{provider}/login     → redirects user to provider's login page
  GET /auth/{provider}/callback  → receives the code, exchanges for tokens
  GET /auth/{provider}/status    → check if we have valid tokens
  GET /auth/status               → check all providers at once
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.auth import get_authorize_url, exchange_code_for_tokens, get_valid_access_token
from app.token_store import get_tokens, delete_tokens

router = APIRouter(prefix="/auth", tags=["auth"])

SUPPORTED_PROVIDERS = ["strava", "whoop"]


def _validate_provider(provider: str) -> None:
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")


# ---------------------------------------------------------------------------
# Login — redirect user to provider
# ---------------------------------------------------------------------------

@router.get("/{provider}/login")
async def login(provider: str):
    """Redirect the user to the provider's OAuth login page."""
    _validate_provider(provider)
    url = get_authorize_url(provider)
    return RedirectResponse(url=url)


# ---------------------------------------------------------------------------
# Callback — provider redirects back here with a code
# ---------------------------------------------------------------------------

@router.get("/{provider}/callback")
async def callback(provider: str, code: str | None = None, error: str | None = None):
    """
    OAuth callback endpoint.
    The provider redirects here after the user authorizes (or denies).
    """
    _validate_provider(provider)

    if error:
        return {"status": "error", "provider": provider, "detail": error}

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")

    try:
        token_data = await exchange_code_for_tokens(provider, code)
        return {
            "status": "success",
            "provider": provider,
            "message": f"Successfully authenticated with {provider}!",
            "token_preview": token_data["access_token"][:15] + "...",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {str(e)}")


# ---------------------------------------------------------------------------
# Status — check authentication state
# ---------------------------------------------------------------------------

@router.get("/{provider}/status")
async def provider_status(provider: str):
    """Check if we have valid tokens for a provider."""
    _validate_provider(provider)
    tokens = get_tokens(provider)

    if not tokens:
        return {"provider": provider, "authenticated": False, "message": "Not connected"}

    try:
        await get_valid_access_token(provider)
        return {"provider": provider, "authenticated": True, "message": "Connected"}
    except Exception:
        return {"provider": provider, "authenticated": False, "message": "Token expired, re-auth needed"}


@router.get("/status")
async def all_status():
    """Check authentication status for all providers."""
    results = {}
    for provider in SUPPORTED_PROVIDERS:
        tokens = get_tokens(provider)
        if tokens:
            try:
                await get_valid_access_token(provider)
                results[provider] = {"authenticated": True, "message": "Connected"}
            except Exception:
                results[provider] = {"authenticated": False, "message": "Token expired"}
        else:
            results[provider] = {"authenticated": False, "message": "Not connected"}
    return results


# ---------------------------------------------------------------------------
# Logout — remove stored tokens
# ---------------------------------------------------------------------------

@router.get("/{provider}/logout")
async def logout(provider: str):
    """Remove stored tokens for a provider."""
    _validate_provider(provider)
    delete_tokens(provider)
    return {"provider": provider, "message": "Tokens removed"}
