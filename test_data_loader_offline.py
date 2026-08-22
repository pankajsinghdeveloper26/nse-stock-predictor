"""
Offline validation for data_loader.py using synthetic OHLCV data
(no network / yfinance call required). Run directly with:

    python tests/test_data_loader_offline.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data_loader import (  # noqa: E402
    add_technical_indicators,
    detect_candlestick_patterns,
    compute_rsi,
    compute_macd,
    compute_bollinger_bands,
    compute_atr,
)


def make_synthetic_ohlcv(n=200, seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", periods=n, freq="B")

    # Random-walk close prices
    returns = rng.normal(loc=0.0006, scale=0.015, size=n)
    close = 2500 * np.cumprod(1 + returns)

    open_ = close * (1 + rng.normal(0, 0.004, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.006, n)))
    volume = rng.integers(1_000_000, 5_000_000, n)

    df = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    )
    df.index.name = "Date"
    return df


def inject_known_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Hand-craft a few candles so we KNOW what patterns should fire."""
    df = df.copy()

    # Row 50: Doji -> open ~= close, wide range
    i = 50
    df.iloc[i, df.columns.get_loc("Open")] = 100.0
    df.iloc[i, df.columns.get_loc("Close")] = 100.05
    df.iloc[i, df.columns.get_loc("High")] = 103.0
    df.iloc[i, df.columns.get_loc("Low")] = 97.0

    # Row 60: Hammer -> small body near top, long lower wick, tiny upper wick
    i = 60
    df.iloc[i, df.columns.get_loc("Open")] = 100.0
    df.iloc[i, df.columns.get_loc("Close")] = 101.0
    df.iloc[i, df.columns.get_loc("High")] = 101.2
    df.iloc[i, df.columns.get_loc("Low")] = 95.0

    # Rows 70-71: Bullish engulfing -> prev red candle, current green engulfs it
    i = 70
    df.iloc[i, df.columns.get_loc("Open")] = 105.0
    df.iloc[i, df.columns.get_loc("Close")] = 100.0
    df.iloc[i, df.columns.get_loc("High")] = 106.0
    df.iloc[i, df.columns.get_loc("Low")] = 99.5
    i = 71
    df.iloc[i, df.columns.get_loc("Open")] = 99.0
    df.iloc[i, df.columns.get_loc("Close")] = 106.5
    df.iloc[i, df.columns.get_loc("High")] = 107.0
    df.iloc[i, df.columns.get_loc("Low")] = 98.5

    return df


def main():
    print("=" * 70)
    print("OFFLINE VALIDATION: data_loader.py (synthetic OHLCV, no network)")
    print("=" * 70)

    df = make_synthetic_ohlcv(n=200)
    df = inject_known_patterns(df)

    # --- Indicators ---
    feat = add_technical_indicators(df)
    indicator_cols = [
        "SMA_20", "SMA_50", "RSI_14", "MACD", "MACD_Signal", "MACD_Hist",
        "BB_Middle", "BB_Upper", "BB_Lower", "BB_Width", "BB_PercentB", "ATR_14",
    ]
    missing = [c for c in indicator_cols if c not in feat.columns]
    assert not missing, f"Missing indicator columns: {missing}"
    print(f"\n[OK] All {len(indicator_cols)} indicator columns present.")

    # Sanity ranges
    rsi_valid = feat["RSI_14"].dropna()
    assert rsi_valid.between(0, 100).all(), "RSI out of [0,100] range!"
    print(f"[OK] RSI_14 within [0, 100]. Sample tail:\n{rsi_valid.tail(5).round(2)}")

    assert (feat["BB_Upper"].dropna() >= feat["BB_Lower"].dropna()).all(), "BB_Upper < BB_Lower somewhere!"
    print("[OK] Bollinger Upper >= Lower for all valid rows.")

    assert (feat["ATR_14"].dropna() >= 0).all(), "Negative ATR found!"
    print(f"[OK] ATR_14 non-negative. Last value: {feat['ATR_14'].iloc[-1]:.4f}")

    print(f"[OK] SMA_20 last value: {feat['SMA_20'].iloc[-1]:.2f}, "
          f"SMA_50 last value: {feat['SMA_50'].iloc[-1]:.2f}")
    print(f"[OK] MACD last value: {feat['MACD'].iloc[-1]:.4f}, "
          f"Signal: {feat['MACD_Signal'].iloc[-1]:.4f}")

    # --- Candlestick patterns ---
    patt = detect_candlestick_patterns(df)
    pattern_cols = ["Doji", "Hammer", "InvertedHammer", "Bullish_Engulfing", "Bearish_Engulfing"]
    missing = [c for c in pattern_cols if c not in patt.columns]
    assert not missing, f"Missing pattern columns: {missing}"
    print(f"\n[OK] All {len(pattern_cols)} pattern columns present.")

    assert patt["Doji"].iloc[50] == True, "Expected Doji at row 50 not detected!"  # noqa: E712
    print("[OK] Injected Doji at row 50 correctly detected.")

    assert patt["Hammer"].iloc[60] == True, "Expected Hammer at row 60 not detected!"  # noqa: E712
    print("[OK] Injected Hammer at row 60 correctly detected.")

    assert patt["Bullish_Engulfing"].iloc[71] == True, "Expected Bullish Engulfing at row 71 not detected!"  # noqa: E712
    print("[OK] Injected Bullish Engulfing at row 71 correctly detected.")

    assert patt["Bullish_Engulfing"].iloc[0] == False  # noqa: E712
    assert patt["Bearish_Engulfing"].iloc[0] == False  # noqa: E712
    print("[OK] First row correctly has no engulfing pattern (no prior candle).")

    counts = patt[pattern_cols].sum()
    print(f"\nPattern counts across {len(patt)} synthetic rows:\n{counts}")

    print("\n" + "=" * 70)
    print("ALL OFFLINE CHECKS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
