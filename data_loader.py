"""
data_loader.py
================
Phase 1 core module for the NSE Stock Prediction project.

Responsibilities
-----------------
1. Fetch NSE stock history via yfinance (e.g. RELIANCE.NS, TCS.NS).
2. Compute technical indicators: RSI, MACD, SMA 20/50, Bollinger Bands, ATR.
3. Detect candlestick patterns: Doji, Hammer, (Bullish/Bearish) Engulfing.

All indicator math is implemented by hand with pandas/numpy (no TA-Lib C
dependency required), so the module works even in environments where
TA-Lib can't be compiled.

Usage
-----
    from data_loader import fetch_stock_data, add_technical_indicators, detect_candlestick_patterns

    df = fetch_stock_data("RELIANCE.NS", period="2y", interval="1d")
    df = add_technical_indicators(df)
    df = detect_candlestick_patterns(df)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

try:
    import yfinance as yf
    _YFINANCE_AVAILABLE = True
except ImportError:  # pragma: no cover - environment without yfinance installed
    _YFINANCE_AVAILABLE = False

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("data_loader")

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
DEFAULT_TICKERS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]
RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

REQUIRED_OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]


# --------------------------------------------------------------------------- #
# 1. DATA INGESTION
# --------------------------------------------------------------------------- #
def fetch_stock_data(
    ticker: str,
    period: str = "2y",
    interval: str = "1d",
    auto_adjust: bool = True,
    save_raw: bool = True,
) -> pd.DataFrame:
    """
    Fetch OHLCV history for an NSE ticker via yfinance.

    Parameters
    ----------
    ticker : str
        NSE ticker with Yahoo Finance suffix, e.g. "RELIANCE.NS", "TCS.NS".
    period : str
        yfinance period string, e.g. "6mo", "1y", "2y", "5y", "max".
    interval : str
        yfinance interval string, e.g. "1d", "1h", "15m".
    auto_adjust : bool
        Adjust OHLC for splits/dividends (recommended for indicator calc).
    save_raw : bool
        If True, cache the raw fetch to data/raw/<ticker>_<interval>.csv.

    Returns
    -------
    pd.DataFrame
        Indexed by Date, columns: Open, High, Low, Close, Volume
        (plus Dividends/Stock Splits if present).

    Raises
    ------
    ImportError
        If yfinance is not installed.
    ValueError
        If no data is returned for the ticker (bad symbol / no network / delisted).
    """
    if not _YFINANCE_AVAILABLE:
        raise ImportError(
            "yfinance is not installed. Run `pip install -r requirements.txt` "
            "in an environment with internet access before calling fetch_stock_data()."
        )

    logger.info("Fetching %s | period=%s interval=%s", ticker, period, interval)

    df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=auto_adjust)

    if df is None or df.empty:
        raise ValueError(
            f"No data returned for '{ticker}'. Check the symbol (NSE tickers need "
            f"the '.NS' suffix, e.g. 'RELIANCE.NS') and your network connection."
        )

    df.index.name = "Date"
    df = df[[c for c in df.columns if c in REQUIRED_OHLCV_COLS + ["Dividends", "Stock Splits"]]]

    missing = [c for c in REQUIRED_OHLCV_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Fetched data for {ticker} is missing expected columns: {missing}")

    df = df.dropna(subset=REQUIRED_OHLCV_COLS)

    if save_raw:
        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_path = RAW_DATA_DIR / f"{ticker.replace('.', '_')}_{interval}.csv"
        df.to_csv(out_path)
        logger.info("Saved raw data -> %s (%d rows)", out_path, len(df))

    return df


def fetch_multiple(
    tickers: Iterable[str] = DEFAULT_TICKERS,
    period: str = "2y",
    interval: str = "1d",
) -> dict[str, pd.DataFrame]:
    """Fetch multiple tickers, skipping (and logging) any that fail."""
    results: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            results[ticker] = fetch_stock_data(ticker, period=period, interval=interval)
        except Exception as exc:  # noqa: BLE001 - we want to continue on any per-ticker failure
            logger.warning("Skipping %s: %s", ticker, exc)
    return results


# --------------------------------------------------------------------------- #
# 2. TECHNICAL INDICATORS
# --------------------------------------------------------------------------- #
def _validate_ohlcv(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_OHLCV_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"DataFrame missing required OHLCV columns: {missing}")
    if len(df) == 0:
        raise ValueError("DataFrame is empty.")


def compute_sma(close: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average."""
    return close.rolling(window=window, min_periods=window).mean()


def compute_ema(close: pd.Series, span: int) -> pd.Series:
    """Exponential Moving Average."""
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


def compute_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """
    Relative Strength Index using Wilder's smoothing (the standard RSI definition).

    RSI = 100 - 100 / (1 + RS), RS = avg_gain / avg_loss over `window` periods.
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder's smoothing == an EMA with alpha = 1/window
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    # Where avg_loss is 0 (all gains), RSI should be 100
    rsi = rsi.where(avg_loss != 0, 100)
    return rsi


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """
    MACD (Moving Average Convergence Divergence).

    Returns a DataFrame with columns: MACD, MACD_Signal, MACD_Hist.
    """
    ema_fast = compute_ema(close, fast)
    ema_slow = compute_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame(
        {"MACD": macd_line, "MACD_Signal": signal_line, "MACD_Hist": histogram}
    )


def compute_bollinger_bands(
    close: pd.Series,
    window: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    """
    Bollinger Bands. Returns DataFrame with columns:
    BB_Middle, BB_Upper, BB_Lower, BB_Width, BB_PercentB
    """
    middle = compute_sma(close, window)
    std = close.rolling(window=window, min_periods=window).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    width = (upper - lower) / middle
    percent_b = (close - lower) / (upper - lower)
    return pd.DataFrame(
        {
            "BB_Middle": middle,
            "BB_Upper": upper,
            "BB_Lower": lower,
            "BB_Width": width,
            "BB_PercentB": percent_b,
        }
    )


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 14,
) -> pd.Series:
    """
    Average True Range (Wilder's smoothing).

    True Range = max(high-low, |high-prev_close|, |low-prev_close|)
    """
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    return atr


def add_technical_indicators(
    df: pd.DataFrame,
    rsi_window: int = 14,
    sma_windows: tuple[int, int] = (20, 50),
    macd_params: tuple[int, int, int] = (12, 26, 9),
    bb_window: int = 20,
    bb_std: float = 2.0,
    atr_window: int = 14,
) -> pd.DataFrame:
    """
    Compute RSI, MACD, SMA(20/50), Bollinger Bands, and ATR, and append them
    as new columns to a copy of the input OHLCV DataFrame.
    """
    _validate_ohlcv(df)
    out = df.copy()

    # SMA 20 / 50
    fast_w, slow_w = sma_windows
    out[f"SMA_{fast_w}"] = compute_sma(out["Close"], fast_w)
    out[f"SMA_{slow_w}"] = compute_sma(out["Close"], slow_w)

    # RSI
    out[f"RSI_{rsi_window}"] = compute_rsi(out["Close"], rsi_window)

    # MACD
    fast, slow, signal = macd_params
    macd_df = compute_macd(out["Close"], fast, slow, signal)
    out = pd.concat([out, macd_df], axis=1)

    # Bollinger Bands
    bb_df = compute_bollinger_bands(out["Close"], bb_window, bb_std)
    out = pd.concat([out, bb_df], axis=1)

    # ATR
    out[f"ATR_{atr_window}"] = compute_atr(out["High"], out["Low"], out["Close"], atr_window)

    logger.info("Added technical indicators: %s", [c for c in out.columns if c not in df.columns])
    return out


# --------------------------------------------------------------------------- #
# 3. CANDLESTICK PATTERN DETECTION
# --------------------------------------------------------------------------- #
def detect_candlestick_patterns(
    df: pd.DataFrame,
    doji_body_ratio: float = 0.05,
    hammer_body_ratio: float = 0.3,
    hammer_wick_ratio: float = 2.0,
) -> pd.DataFrame:
    """
    Detect simple, rule-based candlestick patterns and append boolean columns:

        Doji, Hammer, InvertedHammer, Bullish_Engulfing, Bearish_Engulfing

    Definitions (standard technical-analysis heuristics)
    -----------------------------------------------------
    Doji:
        Body (|close-open|) is tiny relative to the candle's total range
        (<= doji_body_ratio of High-Low). Signals indecision.

    Hammer:
        Small body near the top of the range, little/no upper wick, and a
        lower wick at least `hammer_wick_ratio` times the body size.
        Bullish reversal signal after a downtrend.

    Inverted Hammer:
        Mirror of Hammer - small body near the bottom of the range with a
        long upper wick. Potential bullish reversal after a downtrend.

    Bullish Engulfing:
        Prior candle is bearish (red), current candle is bullish (green),
        and the current candle's body fully engulfs the prior candle's body.

    Bearish Engulfing:
        Prior candle is bullish (green), current candle is bearish (red),
        and the current candle's body fully engulfs the prior candle's body.
    """
    _validate_ohlcv(df)
    out = df.copy()

    o, h, l, c = out["Open"], out["High"], out["Low"], out["Close"]

    body = (c - o).abs()
    candle_range = (h - l).replace(0, np.nan)  # avoid div-by-zero on flat candles
    upper_wick = h - out[["Open", "Close"]].max(axis=1)
    lower_wick = out[["Open", "Close"]].min(axis=1) - l

    is_bullish = c > o
    is_bearish = c < o

    # --- Doji: tiny body relative to full range ---
    out["Doji"] = (body / candle_range) <= doji_body_ratio

    # --- Hammer: small body, long lower wick, short/no upper wick ---
    small_body = (body / candle_range) <= hammer_body_ratio
    long_lower_wick = lower_wick >= hammer_wick_ratio * body.replace(0, np.nan)
    short_upper_wick = upper_wick <= body.replace(0, np.nan)  # upper wick no bigger than body
    out["Hammer"] = small_body & long_lower_wick & short_upper_wick

    # --- Inverted Hammer: small body, long upper wick, short/no lower wick ---
    long_upper_wick = upper_wick >= hammer_wick_ratio * body.replace(0, np.nan)
    short_lower_wick = lower_wick <= body.replace(0, np.nan)
    out["InvertedHammer"] = small_body & long_upper_wick & short_lower_wick

    # --- Engulfing patterns (need previous candle) ---
    prev_open = o.shift(1)
    prev_close = c.shift(1)
    prev_bullish = prev_close > prev_open
    prev_bearish = prev_close < prev_open

    bullish_engulf = (
        prev_bearish
        & is_bullish
        & (o <= prev_close)
        & (c >= prev_open)
    )
    bearish_engulf = (
        prev_bullish
        & is_bearish
        & (o >= prev_close)
        & (c <= prev_open)
    )

    out["Bullish_Engulfing"] = bullish_engulf.fillna(False)
    out["Bearish_Engulfing"] = bearish_engulf.fillna(False)

    # First row can't have an engulfing pattern (no previous candle)
    out.iloc[0, out.columns.get_loc("Bullish_Engulfing")] = False
    out.iloc[0, out.columns.get_loc("Bearish_Engulfing")] = False

    pattern_cols = ["Doji", "Hammer", "InvertedHammer", "Bullish_Engulfing", "Bearish_Engulfing"]
    for col in pattern_cols:
        out[col] = out[col].fillna(False).astype(bool)

    logger.info(
        "Detected patterns -> Doji: %d, Hammer: %d, InvertedHammer: %d, "
        "Bullish_Engulfing: %d, Bearish_Engulfing: %d",
        out["Doji"].sum(),
        out["Hammer"].sum(),
        out["InvertedHammer"].sum(),
        out["Bullish_Engulfing"].sum(),
        out["Bearish_Engulfing"].sum(),
    )
    return out


# --------------------------------------------------------------------------- #
# 4. PIPELINE ORCHESTRATION
# --------------------------------------------------------------------------- #
def build_feature_dataset(
    ticker: str,
    period: str = "2y",
    interval: str = "1d",
    save_processed: bool = True,
) -> pd.DataFrame:
    """
    End-to-end Phase 1 pipeline: fetch -> indicators -> candlestick patterns.
    Saves the final feature-engineered DataFrame to data/processed/ as CSV.
    """
    df = fetch_stock_data(ticker, period=period, interval=interval)
    df = add_technical_indicators(df)
    df = detect_candlestick_patterns(df)

    if save_processed:
        PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_path = PROCESSED_DATA_DIR / f"{ticker.replace('.', '_')}_{interval}_features.csv"
        df.to_csv(out_path)
        logger.info("Saved processed feature set -> %s (%d rows, %d cols)", out_path, *df.shape)

    return df


if __name__ == "__main__":
    # Simple smoke test when run directly (requires internet + yfinance installed).
    for tkr in ["RELIANCE.NS", "TCS.NS"]:
        try:
            feature_df = build_feature_dataset(tkr, period="1y", interval="1d")
            print(f"\n{tkr} -> shape={feature_df.shape}")
            print(feature_df.tail(3))
        except Exception as e:  # noqa: BLE001
            print(f"{tkr} failed: {e}")
