"""
features.py
================
Feature-engineering layer built on `pandas-ta`: RSI, MACD, Bollinger
Bands, Supertrend, EMA, SMA, ATR, VWAP.

Relationship to data_loader.py
-------------------------------
data_loader.add_technical_indicators() already hand-computes RSI, MACD,
SMA 20/50, Bollinger Bands, and ATR (no C-extension dependency, so it
works even where pandas-ta/TA-Lib can't be installed) - that keeps
working exactly as before, unchanged.

This module ADDS the indicators the existing pipeline didn't have
(Supertrend, VWAP, extra EMA spans) via pandas-ta, and can optionally
recompute the "classic" set through pandas-ta too when you want the
pandas-ta implementation specifically (`add_features(df, prefer_pandas_ta=True)`).
Either way, nothing here overwrites data_loader.py's existing column
names, so services.py's response shape (`latest.rsi_14`, `latest.macd`,
etc.) is unaffected unless you opt in.

If `pandas-ta` isn't installed, every function degrades to a pure-pandas
implementation so the app still runs - the same graceful-degradation
pattern models.py uses for xgboost/tensorflow.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger("features")

try:
    import pandas_ta as ta  # noqa: F401

    _PANDAS_TA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PANDAS_TA_AVAILABLE = False
    logger.warning(
        "features.py: `pandas-ta` not installed - falling back to pure-pandas "
        "implementations for every indicator. Run `pip install pandas-ta` for "
        "the full library (adds Supertrend natively, etc.)."
    )

REQUIRED_OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]


def _validate(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_OHLCV_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"features.py: DataFrame missing required columns: {missing}")
    if df.empty:
        raise ValueError("features.py: DataFrame is empty.")


# --------------------------------------------------------------------------- #
# Individual indicators (each: pandas-ta if available, else pure-pandas)
# --------------------------------------------------------------------------- #
def sma(close: pd.Series, length: int = 20) -> pd.Series:
    if _PANDAS_TA_AVAILABLE:
        return ta.sma(close, length=length)
    return close.rolling(window=length, min_periods=length).mean()


def ema(close: pd.Series, length: int = 20) -> pd.Series:
    if _PANDAS_TA_AVAILABLE:
        return ta.ema(close, length=length)
    return close.ewm(span=length, adjust=False, min_periods=length).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    if _PANDAS_TA_AVAILABLE:
        return ta.rsi(close, length=length)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.where(avg_loss != 0, 100)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    if _PANDAS_TA_AVAILABLE:
        result = ta.macd(close, fast=fast, slow=slow, signal=signal)
        if result is not None:
            result.columns = ["MACD", "MACD_Signal", "MACD_Hist"]
            return result
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({
        "MACD": macd_line,
        "MACD_Signal": signal_line,
        "MACD_Hist": macd_line - signal_line,
    })


def bollinger_bands(close: pd.Series, length: int = 20, std: float = 2.0) -> pd.DataFrame:
    if _PANDAS_TA_AVAILABLE:
        result = ta.bbands(close, length=length, std=std)
        if result is not None:
            cols = [c for c in result.columns if c.startswith(("BBL", "BBM", "BBU"))]
            renamed = result[cols].copy()
            renamed.columns = ["BB_Lower", "BB_Middle", "BB_Upper"]
            renamed["BB_Width"] = (renamed["BB_Upper"] - renamed["BB_Lower"]) / renamed["BB_Middle"]
            renamed["BB_PercentB"] = (close - renamed["BB_Lower"]) / (renamed["BB_Upper"] - renamed["BB_Lower"])
            return renamed
    middle = sma(close, length)
    stdev = close.rolling(window=length, min_periods=length).std()
    upper = middle + std * stdev
    lower = middle - std * stdev
    return pd.DataFrame({
        "BB_Middle": middle,
        "BB_Upper": upper,
        "BB_Lower": lower,
        "BB_Width": (upper - lower) / middle,
        "BB_PercentB": (close - lower) / (upper - lower),
    })


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    if _PANDAS_TA_AVAILABLE:
        result = ta.atr(high, low, close, length=length)
        if result is not None:
            return result
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def supertrend(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int = 10, multiplier: float = 3.0
) -> pd.DataFrame:
    """
    Supertrend indicator. Returns a DataFrame with columns:
        Supertrend        - the trailing stop/trend line itself
        Supertrend_Direction - +1 (uptrend / price above line) or -1 (downtrend)

    pandas-ta's native implementation is used when available; otherwise a
    standard pure-pandas Supertrend (ATR-band flip logic) is computed.
    """
    if _PANDAS_TA_AVAILABLE:
        result = ta.supertrend(high, low, close, length=length, multiplier=multiplier)
        if result is not None:
            cols = list(result.columns)
            trend_col = next((c for c in cols if c.startswith("SUPERT_")), None)
            dir_col = next((c for c in cols if c.startswith("SUPERTd_")), None)
            if trend_col and dir_col:
                return pd.DataFrame({
                    "Supertrend": result[trend_col],
                    "Supertrend_Direction": result[dir_col],
                })

    # Pure-pandas fallback implementation
    atr_series = atr(high, low, close, length)
    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr_series
    lower_band = hl2 - multiplier * atr_series

    trend = pd.Series(index=close.index, dtype=float)
    direction = pd.Series(index=close.index, dtype=int)

    for i in range(len(close)):
        if i == 0 or pd.isna(atr_series.iloc[i]):
            trend.iloc[i] = np.nan
            direction.iloc[i] = 1
            continue

        prev_trend = trend.iloc[i - 1]
        prev_dir = direction.iloc[i - 1]

        if pd.isna(prev_trend):
            direction.iloc[i] = 1 if close.iloc[i] > upper_band.iloc[i] else -1
            trend.iloc[i] = lower_band.iloc[i] if direction.iloc[i] == 1 else upper_band.iloc[i]
            continue

        if prev_dir == 1:
            cur_lower = max(lower_band.iloc[i], prev_trend) if close.iloc[i - 1] > prev_trend else lower_band.iloc[i]
            if close.iloc[i] < cur_lower:
                direction.iloc[i] = -1
                trend.iloc[i] = upper_band.iloc[i]
            else:
                direction.iloc[i] = 1
                trend.iloc[i] = cur_lower
        else:
            cur_upper = min(upper_band.iloc[i], prev_trend) if close.iloc[i - 1] < prev_trend else upper_band.iloc[i]
            if close.iloc[i] > cur_upper:
                direction.iloc[i] = 1
                trend.iloc[i] = lower_band.iloc[i]
            else:
                direction.iloc[i] = -1
                trend.iloc[i] = cur_upper

    return pd.DataFrame({"Supertrend": trend, "Supertrend_Direction": direction})


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """
    Volume-Weighted Average Price, cumulative from the start of the
    series. VWAP is most meaningful intraday (reset each session); for
    daily bars this is a running cumulative VWAP across the whole
    history, which is still a useful "value area" reference line.
    """
    if _PANDAS_TA_AVAILABLE:
        try:
            result = ta.vwap(high, low, close, volume)
            if result is not None:
                return result
        except Exception:  # noqa: BLE001 - pandas-ta's vwap wants a DatetimeIndex; fall back below
            pass
    typical_price = (high + low + close) / 3
    cum_vol = volume.cumsum().replace(0, np.nan)
    return (typical_price * volume).cumsum() / cum_vol


# --------------------------------------------------------------------------- #
# Orchestration: add every feature to an OHLCV DataFrame in one call
# --------------------------------------------------------------------------- #
def add_features(
    df: pd.DataFrame,
    prefer_pandas_ta: bool = False,
    ema_spans: tuple[int, ...] = (9, 21, 50),
) -> pd.DataFrame:
    """
    Append the full indicator set to a copy of an OHLCV DataFrame:
    SMA(20), EMA(9/21/50 by default), RSI(14), MACD, Bollinger Bands,
    ATR(14), Supertrend(10, 3.0), VWAP.

    If `prefer_pandas_ta` is False (default), columns that
    data_loader.add_technical_indicators() already produces (SMA_20,
    RSI_14, MACD*, BB_*, ATR_14) are NOT recomputed here - only the new
    indicators (EMA_*, Supertrend*, VWAP) are added, so this is safe to
    call on top of data_loader's output without clobbering anything
    services.py already reads. Set `prefer_pandas_ta=True` to also
    recompute the classic set via pandas-ta into the same column names
    (overwriting data_loader's hand-rolled versions with pandas-ta's).
    """
    _validate(df)
    out = df.copy()

    for span in ema_spans:
        out[f"EMA_{span}"] = ema(out["Close"], span)

    st = supertrend(out["High"], out["Low"], out["Close"])
    out = pd.concat([out, st], axis=1)

    out["VWAP"] = vwap(out["High"], out["Low"], out["Close"], out["Volume"])

    if prefer_pandas_ta or "SMA_20" not in out.columns:
        out["SMA_20"] = sma(out["Close"], 20)
    if prefer_pandas_ta or "RSI_14" not in out.columns:
        out["RSI_14"] = rsi(out["Close"], 14)
    if prefer_pandas_ta or "MACD" not in out.columns:
        macd_df = macd(out["Close"])
        for col in macd_df.columns:
            out[col] = macd_df[col]
    if prefer_pandas_ta or "BB_Middle" not in out.columns:
        bb_df = bollinger_bands(out["Close"])
        for col in bb_df.columns:
            out[col] = bb_df[col]
    if prefer_pandas_ta or "ATR_14" not in out.columns:
        out["ATR_14"] = atr(out["High"], out["Low"], out["Close"], 14)

    logger.info(
        "features.add_features: pandas_ta=%s, prefer_pandas_ta=%s, added/updated %d columns",
        _PANDAS_TA_AVAILABLE, prefer_pandas_ta, len(out.columns) - len(df.columns),
    )
    return out
