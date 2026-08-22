"""
services.py
================
Phase 3 core module for the NSE Stock Prediction project.

This is the orchestration layer sitting between the FastAPI HTTP layer
(server.py) and the Phase 1 / Phase 2 core modules:

    data_loader.py  -> fetch_stock_data, add_technical_indicators,
                        detect_candlestick_patterns
    models.py       -> run_forecast_pipeline (backtest -> best model ->
                        N-day forecast -> market mood + Buy/Hold/Sell signal)

Responsibilities
-----------------
1. Ticker resolution: normalize whatever the client passes in
   ("reliance", "RELIANCE", "reliance.ns", "RELIANCE.NS") into the
   Yahoo-Finance-compatible NSE symbol data_loader.py expects.
2. Fetch + feature-engineer OHLCV data (indicators + candlestick patterns).
3. Run the multi-model forecasting pipeline and shape the result into
   JSON-serializable dicts (no numpy/pandas types leak to the API layer).
4. Compute an aggregate "Market Mood" across a preset basket of top NSE
   tickers by running the forecasting pipeline per ticker and rolling up
   the individual moods/signals.
5. Small in-process TTL cache so repeated requests for the same
   ticker/params within a short window don't re-hit yfinance / re-train
   models on every call.

None of this is financial advice — see the `disclaimer` field returned
alongside forecast/market-mood payloads.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from data_loader import (
    fetch_stock_data,
    add_technical_indicators,
    detect_candlestick_patterns,
)
from models import run_forecast_pipeline, ForecastResult

logger = logging.getLogger("services")

# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class TickerNotFoundError(Exception):
    """Raised when a ticker can't be resolved / fetched from Yahoo Finance."""


class InsufficientDataError(Exception):
    """Raised when there isn't enough history to compute indicators / backtest."""


class ForecastError(Exception):
    """Raised when the modeling pipeline itself fails (e.g. all backtests error)."""


class DependencyMissingError(Exception):
    """Raised when an optional/required backend dependency (e.g. yfinance) is absent."""


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
NSE_SUFFIX = ".NS"

# Curated basket used by the market-mood endpoint when the caller doesn't
# supply their own ticker list. A mix of large-cap names across sectors.
MARKET_MOOD_PRESETS: list[str] = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS",
    "ICICIBANK.NS", "SBIN.NS", "ITC.NS", "LT.NS",
    "HINDUNILVR.NS", "BHARTIARTL.NS",
]

MIN_ROWS_FOR_INDICATORS = 60    # SMA_50 + warm-up buffer
MIN_ROWS_FOR_FORECAST = 120     # backtest window + tree/LSTM warm-up needs real history

_CACHE_TTL_SECONDS = 15 * 60    # 15 minutes
_stock_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_forecast_cache: dict[str, tuple[float, dict]] = {}


# --------------------------------------------------------------------------- #
# Ticker resolution
# --------------------------------------------------------------------------- #
def resolve_ticker(raw_ticker: str) -> str:
    """
    Normalize a user-supplied ticker into a Yahoo-Finance-compatible NSE symbol.

        "reliance"     -> "RELIANCE.NS"
        "RELIANCE"     -> "RELIANCE.NS"
        "reliance.ns"  -> "RELIANCE.NS"
        "RELIANCE.NS"  -> "RELIANCE.NS"
        "  tcs  "      -> "TCS.NS"

    Raises
    ------
    ValueError
        If the input is empty/blank after stripping.
    """
    if raw_ticker is None or not raw_ticker.strip():
        raise ValueError("Ticker must not be empty.")

    t = raw_ticker.strip().upper()
    if not t.endswith(NSE_SUFFIX):
        t = f"{t}{NSE_SUFFIX}"
    return t


# --------------------------------------------------------------------------- #
# JSON-safety helpers
# --------------------------------------------------------------------------- #
def _clean_scalar(v):
    """Convert a single pandas/numpy scalar into a JSON-safe native Python value."""
    if v is None:
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        f = float(v)
        return None if (np.isnan(f) or np.isinf(f)) else f
    if isinstance(v, float):
        return None if (np.isnan(v) or np.isinf(v)) else v
    return v


def _df_to_records(df: pd.DataFrame, date_col_name: str = "Date") -> list[dict]:
    """Convert an indicator/OHLCV DataFrame (DatetimeIndex) into JSON-safe records."""
    out = df.copy()
    out = out.reset_index()
    out = out.rename(columns={out.columns[0]: date_col_name})

    records = []
    for row in out.to_dict(orient="records"):
        records.append({k: _clean_scalar(v) for k, v in row.items()})
    return records


def _safe_float(value) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(f) or np.isinf(f)) else f


# --------------------------------------------------------------------------- #
# Cache helpers
# --------------------------------------------------------------------------- #
def _cache_get(cache: dict, key: str):
    entry = cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        cache.pop(key, None)
        return None
    return value


def _cache_set(cache: dict, key: str, value) -> None:
    cache[key] = (time.time(), value)


# --------------------------------------------------------------------------- #
# Core: fetch + feature-engineer
# --------------------------------------------------------------------------- #
def get_stock_dataframe(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Fetch OHLCV for a ticker and append technical indicators + candlestick
    patterns. This is the shared building block for both the /api/stock
    and /api/forecast endpoints.

    Raises
    ------
    TickerNotFoundError
        Bad symbol, delisted, or no data returned.
    InsufficientDataError
        Data returned but too short to compute indicators reliably.
    DependencyMissingError
        yfinance isn't installed in this environment.
    """
    resolved = resolve_ticker(ticker)
    cache_key = f"{resolved}|{period}|{interval}"

    if use_cache:
        cached = _cache_get(_stock_cache, cache_key)
        if cached is not None:
            return cached.copy()

    try:
        df = fetch_stock_data(resolved, period=period, interval=interval, save_raw=False)
    except ImportError as exc:
        raise DependencyMissingError(str(exc)) from exc
    except ValueError as exc:
        # data_loader raises ValueError for bad symbol / empty response
        raise TickerNotFoundError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - network/yfinance surprises
        raise TickerNotFoundError(f"Could not fetch data for '{resolved}': {exc}") from exc

    if len(df) < MIN_ROWS_FOR_INDICATORS:
        raise InsufficientDataError(
            f"Only {len(df)} rows of history for '{resolved}' — need at least "
            f"{MIN_ROWS_FOR_INDICATORS} to compute indicators reliably. "
            "Try a longer `period` (e.g. '1y' or '2y')."
        )

    df = add_technical_indicators(df)
    df = detect_candlestick_patterns(df)

    if use_cache:
        _cache_set(_stock_cache, cache_key, df)

    return df.copy()


# --------------------------------------------------------------------------- #
# GET /api/stock/{ticker}
# --------------------------------------------------------------------------- #
def get_stock_payload(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
) -> dict:
    """
    Service backing GET /api/stock/{ticker}.
    Returns historical OHLCV + technical indicators + candlestick pattern
    flags, plus a "latest" snapshot for quick display.
    """
    resolved = resolve_ticker(ticker)
    df = get_stock_dataframe(resolved, period=period, interval=interval)
    latest = df.iloc[-1]

    return {
        "ticker": resolved,
        "period": period,
        "interval": interval,
        "rows": len(df),
        "as_of_date": df.index[-1].strftime("%Y-%m-%d"),
        "latest": {
            "close": _safe_float(latest.get("Close")),
            "open": _safe_float(latest.get("Open")),
            "high": _safe_float(latest.get("High")),
            "low": _safe_float(latest.get("Low")),
            "volume": _safe_float(latest.get("Volume")),
            "sma_20": _safe_float(latest.get("SMA_20")),
            "sma_50": _safe_float(latest.get("SMA_50")),
            "rsi_14": _safe_float(latest.get("RSI_14")),
            "macd": _safe_float(latest.get("MACD")),
            "macd_signal": _safe_float(latest.get("MACD_Signal")),
            "macd_hist": _safe_float(latest.get("MACD_Hist")),
            "bb_upper": _safe_float(latest.get("BB_Upper")),
            "bb_lower": _safe_float(latest.get("BB_Lower")),
            "bb_percent_b": _safe_float(latest.get("BB_PercentB")),
            "atr_14": _safe_float(latest.get("ATR_14")),
            "patterns": {
                "doji": bool(latest.get("Doji", False)),
                "hammer": bool(latest.get("Hammer", False)),
                "inverted_hammer": bool(latest.get("InvertedHammer", False)),
                "bullish_engulfing": bool(latest.get("Bullish_Engulfing", False)),
                "bearish_engulfing": bool(latest.get("Bearish_Engulfing", False)),
            },
        },
        "history": _df_to_records(df),
    }


# --------------------------------------------------------------------------- #
# GET /api/forecast/{ticker}
# --------------------------------------------------------------------------- #
def get_forecast_payload(
    ticker: str,
    period: str = "2y",
    interval: str = "1d",
    horizon: int = 5,
    test_size: int = 30,
    use_cache: bool = True,
) -> dict:
    """
    Service backing GET /api/forecast/{ticker}.
    Runs the Phase 2 pipeline (backtest 3 models -> pick best -> forecast
    `horizon` trading days -> derive market mood + Buy/Hold/Sell signal)
    and returns a fully JSON-serializable payload.

    Raises
    ------
    TickerNotFoundError, InsufficientDataError, DependencyMissingError
        See get_stock_dataframe().
    ForecastError
        The modeling pipeline itself failed (e.g. every backtest errored).
    """
    resolved = resolve_ticker(ticker)
    cache_key = f"{resolved}|{period}|{interval}|{horizon}|{test_size}"

    if use_cache:
        cached = _cache_get(_forecast_cache, cache_key)
        if cached is not None:
            return cached

    df = get_stock_dataframe(resolved, period=period, interval=interval, use_cache=use_cache)

    if len(df) < MIN_ROWS_FOR_FORECAST:
        raise InsufficientDataError(
            f"Only {len(df)} rows of indicator-ready history for '{resolved}' — "
            f"need at least {MIN_ROWS_FOR_FORECAST} for a reliable backtest/forecast. "
            "Try `period='2y'` or longer."
        )

    try:
        result: ForecastResult = run_forecast_pipeline(
            df, ticker=resolved, horizon=horizon, test_size=test_size
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Forecast pipeline failed for %s", resolved)
        raise ForecastError(f"Forecast failed for '{resolved}': {exc}") from exc

    leaderboard_records = [
        {k: _clean_scalar(v) for k, v in row.items()}
        for row in result.leaderboard.to_dict(orient="records")
    ]

    forecast_records = []
    for row in result.forecast_df.to_dict(orient="records"):
        r = dict(row)
        d = r.get("Date")
        r["Date"] = d.isoformat() if hasattr(d, "isoformat") else str(d)
        forecast_records.append({k: _clean_scalar(v) for k, v in r.items()})

    payload = {
        "ticker": result.ticker,
        "as_of_date": result.as_of_date.strftime("%Y-%m-%d"),
        "last_close": _safe_float(result.last_close),
        "horizon_days": horizon,
        "test_size_days": test_size,
        "leaderboard": leaderboard_records,
        "best_model": result.best_model_name,
        "forecast": forecast_records,
        "market_mood": result.market_mood,
        "signal": result.signal,
        "rationale": result.rationale,
        "disclaimer": (
            "This forecast and Buy/Hold/Sell signal are generated by simple, "
            "rule-based/ML heuristics for educational purposes only. They are "
            "NOT financial advice."
        ),
    }

    if use_cache:
        _cache_set(_forecast_cache, cache_key, payload)

    return payload


# --------------------------------------------------------------------------- #
# GET /api/market-mood
# --------------------------------------------------------------------------- #
def get_market_mood_payload(
    tickers: Optional[list[str]] = None,
    period: str = "1y",
    interval: str = "1d",
    horizon: int = 5,
    test_size: int = 20,
) -> dict:
    """
    Service backing GET /api/market-mood.
    Runs the forecasting pipeline across a basket of NSE tickers (a preset
    top-10 by default, or a caller-supplied list) and aggregates the
    individual moods/signals into an overall market sentiment reading.

    Per-ticker failures (bad symbol, insufficient history, etc.) are
    skipped and reported under `failures` rather than failing the whole
    request — unless every ticker in the basket fails.
    """
    raw_basket = tickers if tickers else MARKET_MOOD_PRESETS
    basket = []
    for t in raw_basket:
        try:
            basket.append(resolve_ticker(t))
        except ValueError:
            continue

    if not basket:
        raise ValueError("No valid tickers supplied for market-mood basket.")

    per_ticker: list[dict] = []
    failures: list[dict] = []
    mood_counts = {"Bullish": 0, "Bearish": 0, "Sideways": 0}
    signal_counts = {"BUY": 0, "HOLD": 0, "SELL": 0}

    for tkr in basket:
        try:
            payload = get_forecast_payload(
                tkr, period=period, interval=interval, horizon=horizon, test_size=test_size
            )
            mood = payload["market_mood"]
            signal = payload["signal"]
            mood_counts[mood] = mood_counts.get(mood, 0) + 1
            signal_counts[signal] = signal_counts.get(signal, 0) + 1

            forecast_close = payload["forecast"][-1]["Predicted_Close"] if payload["forecast"] else None
            pct_change = None
            if forecast_close is not None and payload["last_close"]:
                pct_change = _safe_float((forecast_close / payload["last_close"] - 1) * 100)

            per_ticker.append({
                "ticker": tkr,
                "last_close": payload["last_close"],
                "mood": mood,
                "signal": signal,
                "forecast_pct_change": pct_change,
                "best_model": payload["best_model"],
            })
        except Exception as exc:  # noqa: BLE001 - keep the basket resilient
            logger.warning("Skipping %s in market-mood basket: %s", tkr, exc)
            failures.append({"ticker": tkr, "error": str(exc)})

    if not per_ticker:
        raise ForecastError("Market mood calculation failed for every ticker in the basket.")

    total = len(per_ticker)
    if mood_counts["Bullish"] > mood_counts["Bearish"] and mood_counts["Bullish"] >= mood_counts["Sideways"]:
        overall_mood = "Bullish"
    elif mood_counts["Bearish"] > mood_counts["Bullish"] and mood_counts["Bearish"] >= mood_counts["Sideways"]:
        overall_mood = "Bearish"
    else:
        overall_mood = "Sideways"

    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "basket_size": total,
        "overall_mood": overall_mood,
        "mood_breakdown": mood_counts,
        "signal_breakdown": signal_counts,
        "bullish_pct": round(100 * mood_counts["Bullish"] / total, 1),
        "bearish_pct": round(100 * mood_counts["Bearish"] / total, 1),
        "sideways_pct": round(100 * mood_counts["Sideways"] / total, 1),
        "tickers": per_ticker,
        "failures": failures,
        "disclaimer": (
            "Aggregated from simple, rule-based/ML forecasting heuristics across "
            "a basket of NSE tickers for educational purposes only. NOT financial advice."
        ),
    }
