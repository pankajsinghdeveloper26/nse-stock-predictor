"""
auth.py
================
Simple API-key authentication + in-memory rate limiting for server.py.

Both are OFF by default so the API keeps working exactly as before with
zero config:

    - Auth is enabled automatically the moment API_KEYS is set (see
      config.py / .env.example). With no keys configured, every request
      is treated as authenticated (back-compat with the pre-auth API).
    - Rate limiting is ON by default (config.RATE_LIMIT_ENABLED=true) but
      generous (60 req/min per client) - set RATE_LIMIT_ENABLED=false to
      fully disable it.

This is intentionally in-memory (a dict of sliding request-timestamp
windows, guarded by a lock) rather than Redis-backed - fine for a single
backend process; if you scale to multiple worker processes/machines,
swap `_RateLimiter` for a shared store (Redis, etc.) without changing
the call sites in server.py.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request

import config

# --------------------------------------------------------------------------- #
# API key auth
# --------------------------------------------------------------------------- #
def check_api_key(x_api_key: str | None) -> None:
    """
    Raise HTTPException(401) if API-key auth is enabled and the supplied
    key is missing/invalid. No-op if auth is disabled (no keys configured).
    """
    if not config.AUTH_ENABLED:
        return
    if not x_api_key or x_api_key not in config.API_KEYS:
        raise HTTPException(
            status_code=401,
            detail=(
                f"Missing or invalid API key. Send it in the "
                f"'{config.API_KEY_HEADER_NAME}' header."
            ),
        )


async def api_key_dependency(
    x_api_key: str | None = Header(default=None, alias=None),
) -> None:
    """
    FastAPI dependency form of check_api_key(), usable per-route via
    `Depends(auth.api_key_dependency)` if you want auth on specific
    endpoints only, instead of the blanket middleware in server.py.
    """
    check_api_key(x_api_key)


# --------------------------------------------------------------------------- #
# Rate limiting: fixed client-count sliding window, per client key
# --------------------------------------------------------------------------- #
class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client_id: str) -> tuple[bool, int]:
        """
        Returns (allowed, retry_after_seconds). Records the hit if allowed.
        """
        now = time.time()
        with self._lock:
            window = self._hits[client_id]
            cutoff = now - self.window_seconds
            while window and window[0] < cutoff:
                window.popleft()

            if len(window) >= self.max_requests:
                retry_after = int(self.window_seconds - (now - window[0])) + 1
                return False, max(retry_after, 1)

            window.append(now)
            return True, 0


_rate_limiter = RateLimiter(
    max_requests=config.RATE_LIMIT_REQUESTS,
    window_seconds=config.RATE_LIMIT_WINDOW_SECONDS,
)


def client_identifier(request: Request, x_api_key: str | None) -> str:
    """Rate-limit per API key when auth is on, else per client IP."""
    if config.AUTH_ENABLED and x_api_key:
        return f"key:{x_api_key}"
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


def enforce_rate_limit(request: Request, x_api_key: str | None) -> None:
    """Raise HTTPException(429) if this client has exceeded the rate limit."""
    if not config.RATE_LIMIT_ENABLED:
        return
    client_id = client_identifier(request, x_api_key)
    allowed, retry_after = _rate_limiter.allow(client_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded: max {config.RATE_LIMIT_REQUESTS} requests "
                f"per {config.RATE_LIMIT_WINDOW_SECONDS}s. Retry after {retry_after}s."
            ),
            headers={"Retry-After": str(retry_after)},
        )
