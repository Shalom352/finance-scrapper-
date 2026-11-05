"""
Internal routes guard (migration 0022) — TOMASTEED's own data: syndication tracker, contacts, mandates.

The Basic Auth of the Next.js middleware protects the web interface only; the backend may be reachable
directly. Internal routes therefore require the ``X-Internal-Token`` header that the Next.js proxy adds
after its own check (shared secret ``INTERNAL_API_TOKEN``). The proxy also forwards the authenticated
user (``X-Authenticated-User``), used as the actor of an edit when the request does not name one.

- token configured: a missing / wrong header -> 401;
- token not configured: production -> 503 (never open by mistake); development / tests -> allowed.
"""
from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request

from app.core.config import get_settings


async def require_internal(x_internal_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    token = settings.internal_api_token
    if not token:
        if settings.is_production:
            raise HTTPException(status_code=503, detail="internal routes disabled: INTERNAL_API_TOKEN is not set")
        return
    if not x_internal_token or not hmac.compare_digest(x_internal_token, token):
        raise HTTPException(status_code=401, detail="internal route: authentication required")


async def current_user(x_authenticated_user: str | None = Header(default=None)) -> str | None:
    user = (x_authenticated_user or "").strip()
    return user[:255] or None


WRITES_PER_MINUTE = 120  # per user (or client address): far above a human reviewer, stops a runaway script
_recent_writes: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit(who: str) -> None:
    now = time.monotonic()
    window = _recent_writes[who]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= WRITES_PER_MINUTE:
        raise HTTPException(status_code=429, detail="too many write requests: retry in a minute")
    window.append(now)


async def write_access(request: Request, x_internal_token: str | None = Header(default=None),
                       x_authenticated_user: str | None = Header(default=None)) -> str | None:
    """Every write route (review decisions, duplicates, ingestion): the same guard as the internal routes
    (audit 22/10/2026: they were reachable on port 8000 without any check), plus a per-user rate limit.
    Returns the authenticated user."""
    await require_internal(x_internal_token)
    user = await current_user(x_authenticated_user)
    _rate_limit(user or (request.client.host if request.client else "?"))
    return user


def actor_of(declared: str | None, user: str | None) -> str | None:
    """Actor of an audited decision: the user authenticated by the proxy, never a name the client chose.
    The declared actor is only used where no proxy names a user (development, tests, CLI)."""
    return user or declared
