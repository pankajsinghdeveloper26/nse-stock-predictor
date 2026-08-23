"""
loader.py
================
The new "Analysis Orchestrator" data-access entry point: Cache ->
Parquet/DuckDB -> external provider (yfinance, via data_loader.py), in
that order, so the backend never re-downloads a ticker's whole history
just to serve one request.

This sits ABOVE data_loader.py (which still owns the actual yfinance
call + indicator math) and BELOW services.py (which still owns
request/response shaping for the API). Nothing in data_loader.py or
services.py's public function signatures changes - see services.py for
the one-line call-site swap.

Historical vs. live
--------------------
    get_historical(ticker, ...)  -> OHLCV bars up to (and including) the
                                     last *closed* trading session. Served
                                     from the Parquet store whenever it's
                                     fresh; only the missing tail is fetched.
    get_live_quote(ticker)       -> today's live/last price snapshot.
                                     Always short-TTL cached (never
                                     persisted to Parquet - it's not a
                                     closed bar yet).
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

import cache
import config
import storage
from cleaner import clean_ohlcv
from data_loader import fetch_stock_data

logger = logging.getLogger("loader")

try:
    import yfinance as yf

    _YFINANCE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YFINANCE_AVAILABLE = False


class DataUnavailableError(Exception):
    """Raised when neither the Parquet store nor the external provider has data."""


# --------------------------------------------------------------------------- #
# Historical OHLCV: Cache -> Parquet/DuckDB -> yfinance
# --------------------------------------------------------------------------- #
def get_historical(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Return cleaned OHLCV history for `ticker`, preferring (in order):

    1. The short-TTL in-memory-speed disk cache (avoids re-reading Parquet
       on every request within the TTL window).
    2. The Parquet store, if it's fresh enough (see config.MAX_STALE_DAYS) -
       and if it covers less history than `period` asks for, only the
       missing older range... in practice yfinance doesn't support partial
       backfill cheaply, so on a full cache miss we fetch the full `period`
       once and let subsequent calls hit the cheap paths.
    3. yfinance, fetching just the *new* tail since the last stored row
       when the store has *some* data but it's stale, or the full `period`
       when the store is empty.

    Every path is cleaned via cleaner.clean_ohlcv() before being returned
    or persisted, so callers always get sane OHLCV data.
    """
    cache_key = f"hist:{ticker}:{period}:{interval}"

    if not force_refresh:
        hit = cache.cache_get(cache_key)
        if hit is not None:
            return hit.copy()

    stored = storage.load_parquet(ticker, interval)

    if not force_refresh and stored is not None and storage.is_fresh(ticker, interval):
        logger.info("loader.get_historical(%s): served from fresh Parquet store", ticker)
        cache.cache_set(cache_key, stored, ttl=config.HISTORICAL_CACHE_TTL_SECONDS)
        return stored.copy()

    # Need to talk to the provider - either nothing stored yet, or it's stale.
    if not _YFINANCE_AVAILABLE:
        if stored is not None:
            logger.warning(
                "loader.get_historical(%s): yfinance unavailable, serving stale Parquet data",
                ticker,
            )
            return stored.copy()
        raise DataUnavailableError(
            f"No stored data for '{ticker}' and yfinance is not installed. "
            "Run `pip install -r requirements.txt` with internet access."
        )

    try:
        if stored is not None and not stored.empty:
            # Incremental: only fetch what's missing since the last stored bar.
            fresh = fetch_stock_data(ticker, period="1mo", interval=interval, save_raw=False)
        else:
            # Cold start: fetch the full requested window.
            fresh = fetch_stock_data(ticker, period=period, interval=interval, save_raw=False)
    except Exception as exc:  # noqa: BLE001
        if stored is not None:
            logger.warning(
                "loader.get_historical(%s): provider fetch failed (%s), serving stale Parquet data",
                ticker, exc,
            )
            cache.cache_set(cache_key, stored, ttl=60)  # short TTL: retry soon
            return stored.copy()
        raise

    fresh = clean_ohlcv(fresh, ticker=ticker)
    merged = storage.upsert_parquet(ticker, fresh, interval)

    # Trim to whatever window `period` implies isn't precise (yfinance
    # period strings aren't simple day counts, e.g. "max"/"ytd"), so we
    # just return everything the store now has for that interval - the
    # caller can slice further if it needs an exact window.
    cache.cache_set(cache_key, merged, ttl=config.HISTORICAL_CACHE_TTL_SECONDS)
    return merged.copy()


# --------------------------------------------------------------------------- #
# Live quote: short-TTL cache -> yfinance only (never Parquet-persisted)
# --------------------------------------------------------------------------- #
def get_live_quote(ticker: str) -> dict:
    """
    Best-effort *current* price snapshot for `ticker`. Cached for
    `config.LIVE_QUOTE_CACHE_TTL_SECONDS` so a burst of requests for the
    same ticker doesn't hammer yfinance.

    Returns a dict with `price`, `previous_close`, `change_pct`,
    `market_state` ("OPEN" / "CLOSED" / "UNKNOWN"), and `as_of`. Any field
    that can't be determined is None rather than raising, since live
    quotes are inherently best-effort (market-closed, provider hiccups).
    """
    cache_key = f"live:{ticker}"
    hit = cache.cache_get(cache_key)
    if hit is not None:
        return hit

    if not _YFINANCE_AVAILABLE:
        raise DataUnavailableError("yfinance is not installed; live quotes are unavailable.")

    try:
        info = yf.Ticker(ticker).fast_info
        price = getattr(info, "last_price", None)
        prev_close = getattr(info, "previous_close", None)
        change_pct = (
            round((price / prev_close - 1) * 100, 2)
            if price is not None and prev_close
            else None
        )
        quote = {
            "ticker": ticker,
            "price": float(price) if price is not None else None,
            "previous_close": float(prev_close) if prev_close is not None else None,
            "change_pct": change_pct,
            "market_state": "UNKNOWN",  # yfinance's fast_info doesn't expose this reliably
            "as_of": pd.Timestamp.utcnow().isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("loader.get_live_quote(%s): provider call failed: %s", ticker, exc)
        raise

    cache.cache_set(cache_key, quote, ttl=config.LIVE_QUOTE_CACHE_TTL_SECONDS)
    return quote
