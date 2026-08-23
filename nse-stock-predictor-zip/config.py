"""
config.py
================
Central configuration for the storage / caching / auth layer added on top
of the existing Phase 1-3 modules (data_loader.py, services.py, server.py).

Everything here is read from environment variables (see .env.example),
with sane defaults so the project still runs out of the box with zero
config — API-key auth and rate limiting are OFF by default, exactly like
before this layer was added.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# .env loading (optional - falls back to plain os.environ if python-dotenv
# isn't installed, so this never becomes a hard dependency).
# --------------------------------------------------------------------------- #
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or not val.strip():
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    val = os.getenv(name)
    if val is None or not val.strip():
        return default
    return [v.strip() for v in val.split(",") if v.strip()]


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
PARQUET_DIR = DATA_DIR / "parquet"
DUCKDB_PATH = Path(os.getenv("DUCKDB_PATH", str(DATA_DIR / "nse.duckdb")))
CACHE_DIR = Path(os.getenv("CACHE_DIR", str(DATA_DIR / "cache")))

for _dir in (PARQUET_DIR, CACHE_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
# Caching
# --------------------------------------------------------------------------- #
# Historical OHLCV (parquet-backed) rarely needs re-fetching same-day.
HISTORICAL_CACHE_TTL_SECONDS = _env_int("HISTORICAL_CACHE_TTL_SECONDS", 6 * 60 * 60)   # 6h
# Live quotes change constantly; keep this short.
LIVE_QUOTE_CACHE_TTL_SECONDS = _env_int("LIVE_QUOTE_CACHE_TTL_SECONDS", 60)             # 1 min
# Forecast pipeline is expensive (trains models); keep the existing 15 min default.
FORECAST_CACHE_TTL_SECONDS = _env_int("FORECAST_CACHE_TTL_SECONDS", 15 * 60)

# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
# Comma-separated list of accepted API keys. Empty (default) = auth disabled,
# so the API behaves exactly as it did before this layer existed.
API_KEYS = set(_env_list("API_KEYS", []))
AUTH_ENABLED = len(API_KEYS) > 0
API_KEY_HEADER_NAME = os.getenv("API_KEY_HEADER_NAME", "X-API-Key")

# --------------------------------------------------------------------------- #
# Rate limiting (simple in-memory, per API key or per client IP if auth is off)
# --------------------------------------------------------------------------- #
RATE_LIMIT_ENABLED = _env_bool("RATE_LIMIT_ENABLED", True)
RATE_LIMIT_REQUESTS = _env_int("RATE_LIMIT_REQUESTS", 60)     # requests...
RATE_LIMIT_WINDOW_SECONDS = _env_int("RATE_LIMIT_WINDOW_SECONDS", 60)  # ...per this many seconds

# --------------------------------------------------------------------------- #
# Data provider behaviour
# --------------------------------------------------------------------------- #
# Trading holidays / weekends mean "today's" bar may not exist yet — treat
# parquet data as fresh if its last row is within this many calendar days.
MAX_STALE_DAYS = _env_int("MAX_STALE_DAYS", 3)

MARKET_TZ = os.getenv("MARKET_TZ", "Asia/Kolkata")
