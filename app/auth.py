"""
Authentication — Google OAuth (OIDC), session-scoped.

Auth is ACTIVE only when Google OAuth creds are configured (``auth_enabled``).
Local dev runs open (no login); the deployment gates the whole app behind
login. Each logged-in user gets a private library scoped by their stable id,
and logging out wipes all of their data.

The signed session cookie (Starlette SessionMiddleware) stores the user dict.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.utils.logger import get_logger

_log = get_logger(__name__)
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])

_LOCAL_USER = {"id": "public", "email": "local@dev", "name": "Local", "provider": "none"}

_oauth = None  # lazy Authlib OAuth registry


def _get_oauth():
    global _oauth
    if _oauth is None:
        from authlib.integrations.starlette_client import OAuth
        s = get_settings()
        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=s.google_oauth_client_id,
            client_secret=s.google_oauth_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        _oauth = oauth
    return _oauth


def current_user(request: Request) -> Optional[Dict[str, Any]]:
    """The logged-in user dict, or a stand-in when auth is disabled."""
    if not get_settings().auth_enabled:
        return _LOCAL_USER
    return request.session.get("user")


def owner_id(request: Request) -> str:
    """Stable per-user key for scoping data. Empty string if unauthenticated."""
    u = current_user(request)
    return u["id"] if u else ""


def require_owner(request: Request) -> str:
    """Owner id, or 401 when auth is on and the caller isn't logged in."""
    oid = owner_id(request)
    if get_settings().auth_enabled and not oid:
        raise HTTPException(401, "Authentication required")
    return oid


def _redirect_uri(request: Request) -> str:
    s = get_settings()
    if s.oauth_redirect_base:
        return s.oauth_redirect_base.rstrip("/") + "/api/auth/callback/google"
    return str(request.url_for("auth_callback_google"))


@auth_router.get("/me")
async def auth_me(request: Request):
    s = get_settings()
    if not s.auth_enabled:
        return {"auth_enabled": False, "authenticated": True, "user": None, "providers": []}
    user = request.session.get("user")
    return {
        "auth_enabled": True,
        "authenticated": bool(user),
        "user": user,
        "providers": ["google"],
    }


@auth_router.get("/login/google")
async def auth_login_google(request: Request):
    if not get_settings().auth_enabled:
        raise HTTPException(400, "Auth is not configured on this server")
    oauth = _get_oauth()
    return await oauth.google.authorize_redirect(request, _redirect_uri(request))


@auth_router.get("/callback/google", name="auth_callback_google")
async def auth_callback_google(request: Request):
    from authlib.integrations.starlette_client import OAuthError
    oauth = _get_oauth()
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        _log.warning("OAuth callback failed", extra={"err": str(exc)})
        return RedirectResponse("/?auth_error=1")
    info = token.get("userinfo") or {}
    sub = info.get("sub")
    if not sub:
        return RedirectResponse("/?auth_error=1")
    request.session["user"] = {
        "id": sub,
        "email": info.get("email", ""),
        "name": info.get("name", ""),
        "picture": info.get("picture", ""),
        "provider": "google",
    }
    # Live log (visible in the Space's run logs — grep for "LOGIN").
    _log.info("LOGIN", extra={
        "email": info.get("email", ""),
        "name": info.get("name", ""),
        "user_id": sub,
    })
    # Durable audit trail on persistent storage, so the record survives restarts
    # (the Space's live logs do not). One JSON line per sign-in.
    try:
        import json, os, time
        from app.config import get_settings
        path = os.path.join(get_settings().data_dir, "logins.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "email": info.get("email", ""),
                "name":  info.get("name", ""),
                "id":    sub,
            }) + "\n")
    except Exception as exc:  # never let audit logging break sign-in
        _log.warning("login audit write failed", extra={"err": str(exc)})
    return RedirectResponse("/")


@auth_router.post("/logout")
async def auth_logout(request: Request):
    """Log out and delete everything owned by this user (session-wise)."""
    user = request.session.get("user")
    deleted = 0
    if user:
        from app import storage
        from app.knowledge_base import get_kb
        try:
            deleted = await asyncio.to_thread(lambda: storage.delete_by_owner(user["id"]))
        except Exception as exc:  # noqa: BLE001
            _log.warning("logout storage cleanup failed", extra={"err": str(exc)})
        try:
            get_kb().delete_by_owner(user["id"])
        except Exception as exc:  # noqa: BLE001
            _log.warning("logout kb cleanup failed", extra={"err": str(exc)})
    request.session.pop("user", None)
    return {"logged_out": True, "deleted": deleted}
