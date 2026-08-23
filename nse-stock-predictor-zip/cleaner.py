"""
cleaner.py
================
OHLCV cleaning/validation, run right after a raw fetch and before data
is written to the Parquet store or handed to the feature-engineering
layer. Keeps bad rows (data-provider glitches, holidays, zero-volume
rows) from silently corrupting indicators or the model pipeline.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger("cleaner")

REQUIRED_OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]


def clean_ohlcv(df: pd.DataFrame, ticker: str = "") -> pd.DataFrame:
    """
    Validate and clean a raw OHLCV DataFrame (DatetimeIndex, Open/High/Low/
    Close/Volume columns). Returns a new, cleaned DataFrame — never
    mutates the input.

    Steps
    -----
    1. Drop duplicate dates (keep the last occurrence).
    2. Sort by date ascending.
    3. Drop rows missing any of Open/High/Low/Close.
    4. Fix High/Low sanity: High = max(O,H,L,C), Low = min(O,H,L,C) — some
       providers occasionally return High < Low on glitchy bars.
    5. Clip negative prices/volume (bad data, not real values) to NaN then
       forward-fill (limited to 2 rows, so we don't paper over real gaps).
    6. Ensure a timezone-naive DatetimeIndex named "Date" (Parquet + DuckDB
       are happiest with a plain index rather than tz-aware timestamps).
    """
    if df is None or df.empty:
        raise ValueError(f"clean_ohlcv: empty DataFrame for '{ticker or 'unknown ticker'}'")

    out = df.copy()

    missing = [c for c in REQUIRED_OHLCV_COLS if c not in out.columns]
    if missing:
        raise ValueError(f"clean_ohlcv: missing required columns {missing} for '{ticker}'")

    # Timezone-naive DatetimeIndex
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index)
    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    out.index.name = "Date"

    # 1-2. Dedupe + sort
    before = len(out)
    out = out[~out.index.duplicated(keep="last")]
    out = out.sort_index()
    if len(out) != before:
        logger.info("clean_ohlcv(%s): dropped %d duplicate-date rows", ticker, before - len(out))

    # 3. Drop rows with no usable price data at all
    before = len(out)
    out = out.dropna(subset=["Open", "High", "Low", "Close"], how="all")
    if len(out) != before:
        logger.info("clean_ohlcv(%s): dropped %d fully-empty rows", ticker, before - len(out))

    # 4. High/Low sanity fix
    row_max = out[["Open", "High", "Low", "Close"]].max(axis=1)
    row_min = out[["Open", "High", "Low", "Close"]].min(axis=1)
    bad_hl = (out["High"] < row_min) | (out["Low"] > row_max)
    if bad_hl.any():
        logger.warning(
            "clean_ohlcv(%s): fixing %d rows with High/Low inconsistent with O/C",
            ticker, int(bad_hl.sum()),
        )
        out.loc[bad_hl, "High"] = row_max[bad_hl]
        out.loc[bad_hl, "Low"] = row_min[bad_hl]

    # 5. Clip impossible negative values, then limited forward-fill
    price_cols = ["Open", "High", "Low", "Close"]
    for col in price_cols + ["Volume"]:
        neg = out[col] < 0
        if neg.any():
            logger.warning("clean_ohlcv(%s): clearing %d negative %s values", ticker, int(neg.sum()), col)
            out.loc[neg, col] = np.nan

    out[price_cols] = out[price_cols].ffill(limit=2)
    out["Volume"] = out["Volume"].fillna(0)

    # Anything still NaN after limited ffill is a real gap — drop it rather
    # than fabricate data.
    before = len(out)
    out = out.dropna(subset=price_cols)
    if len(out) != before:
        logger.info(
            "clean_ohlcv(%s): dropped %d rows with unfillable gaps (>2 consecutive missing)",
            ticker, before - len(out),
        )

    if out.empty:
        raise ValueError(f"clean_ohlcv: no valid rows left for '{ticker}' after cleaning")

    return out


def merge_ohlcv(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """
    Merge freshly-fetched OHLCV rows into an existing (parquet-loaded)
    history, deduping by date (new rows win on overlap — e.g. a
    yesterday's-close bar that gets revised) and keeping the result sorted.
    """
    if existing is None or existing.empty:
        return new.sort_index()
    if new is None or new.empty:
        return existing.sort_index()

    combined = pd.concat([existing, new])
    combined = combined[~combined.index.duplicated(keep="last")]
    return combined.sort_index()
