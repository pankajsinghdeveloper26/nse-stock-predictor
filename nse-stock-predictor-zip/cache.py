"""
cache.py
================
File-based caching so the backend never hits yfinance (or re-runs the
model pipeline) on every single request.

Backed by `diskcache` when it's installed (persists across restarts,
thread/process-safe). Falls back automatically to a simple pickle-file
cache if `diskcache` isn't available, so this module never becomes a
hard blocker — same philosophy as models.py's optional xgboost/tensorflow
fallback.

Usage
-----
    from cache import cache_get, cache_set, cached

    # Manual:
    value = cache_get("stock:RELIANCE.NS:1y:1d")
    if value is None:
        value = expensive_call()
        cache_set("stock:RELIANCE.NS:1y:1d", value, ttl=3600)

    # Decorator:
    @cached(ttl=900, key_fn=lambda ticker, **kw: f"forecast:{ticker}")
    def get_forecast(ticker, ...): ...
"""

from __future__ import annotations

import functools
import hashlib
import logging
import pickle
import time
from pathlib import Path
from typing import Any, Callable, Optional

import config

logger = logging.getLogger("cache")

try:
    import diskcache

    _dc = diskcache.Cache(str(config.CACHE_DIR / "diskcache"))
    _BACKEND = "diskcache"
    logger.info("cache.py: using diskcache backend at %s", config.CACHE_DIR / "diskcache")
except ImportError:  # pragma: no cover
    _dc = None
    _BACKEND = "file-fallback"
    _FALLBACK_DIR = config.CACHE_DIR / "fallback"
    _FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    logger.warning(
        "cache.py: `diskcache` not installed - falling back to a plain pickle-file "
        "cache. Run `pip install diskcache` for a faster, safer cache backend."
    )


def _fallback_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return config.CACHE_DIR / "fallback" / f"{digest}.pkl"


def cache_get(key: str) -> Optional[Any]:
    """Return the cached value for `key`, or None on miss/expiry."""
    if _dc is not None:
        return _dc.get(key, default=None)

    path = _fallback_path(key)
    if not path.exists():
        return None
    try:
        with path.open("rb") as fh:
            expires_at, value = pickle.load(fh)
        if expires_at is not None and time.time() > expires_at:
            path.unlink(missing_ok=True)
            return None
        return value
    except Exception:  # noqa: BLE001 - corrupt cache file, treat as a miss
        path.unlink(missing_ok=True)
        return None


def cache_set(key: str, value: Any, ttl: Optional[int] = None) -> None:
    """Store `value` under `key`, expiring after `ttl` seconds (None = never)."""
    if _dc is not None:
        _dc.set(key, value, expire=ttl)
        return

    path = _fallback_path(key)
    expires_at = (time.time() + ttl) if ttl else None
    with path.open("wb") as fh:
        pickle.dump((expires_at, value), fh)


def cache_delete(key: str) -> None:
    if _dc is not None:
        _dc.delete(key)
        return
    _fallback_path(key).unlink(missing_ok=True)


def cache_clear() -> None:
    """Wipe the entire cache. Useful for tests / manual invalidation."""
    if _dc is not None:
        _dc.clear()
        return
    for f in (config.CACHE_DIR / "fallback").glob("*.pkl"):
        f.unlink(missing_ok=True)


def cached(ttl: int, key_fn: Optional[Callable[..., str]] = None):
    """
    Decorator: cache a function's return value on disk for `ttl` seconds.

    `key_fn(*args, **kwargs) -> str` builds the cache key from the call's
    arguments. If omitted, the key is derived from the function's
    qualified name plus a repr of its arguments (fine for simple
    hashable/stringable args like tickers, periods, ints).
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if key_fn is not None:
                key = key_fn(*args, **kwargs)
            else:
                key = f"{fn.__module__}.{fn.__qualname__}:{args}:{sorted(kwargs.items())}"

            cached_value = cache_get(key)
            if cached_value is not None:
                return cached_value

            result = fn(*args, **kwargs)
            cache_set(key, result, ttl=ttl)
            return result

        return wrapper

    return decorator
