# NSE Stock Prediction — Phase 1

Data ingestion & feature engineering foundation for an NSE (National Stock
Exchange, India) stock prediction project.

## Project structure

```
nse_stock_prediction/
├── requirements.txt
├── README.md
├── src/
│   └── data_loader.py        # fetch + indicators + candlestick patterns
├── tests/
│   └── test_data_loader_offline.py   # synthetic-data validation, no network needed
├── data/
│   ├── raw/                  # raw yfinance OHLCV pulls land here
│   └── processed/            # feature-engineered datasets land here
├── notebooks/                # for EDA / prototyping
├── models/                   # trained model artifacts (Phase 2+)
├── config/                   # config files (tickers, hyperparams, etc.)
└── logs/
```

## Setup

```bash
cd nse_stock_prediction
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Quick start

```python
from src.data_loader import fetch_stock_data, add_technical_indicators, detect_candlestick_patterns

df = fetch_stock_data("RELIANCE.NS", period="2y", interval="1d")
df = add_technical_indicators(df)     # SMA20/50, RSI, MACD, Bollinger Bands, ATR
df = detect_candlestick_patterns(df)  # Doji, Hammer, InvertedHammer, Engulfing
```

Or run the full pipeline end-to-end (fetch → indicators → patterns → save CSV):

```python
from src.data_loader import build_feature_dataset

df = build_feature_dataset("TCS.NS", period="2y", interval="1d")
```

## Validating without network access

`src/data_loader.py` needs internet access (via `yfinance`) to pull real
NSE data. To sanity-check the indicator math and pattern-detection logic
without any network call, run:

```bash
python tests/test_data_loader_offline.py
```

This generates synthetic OHLCV data, injects hand-crafted candles with known
patterns, and asserts the indicators/patterns are computed correctly.

## Indicators implemented

| Indicator | Column(s) | Notes |
|---|---|---|
| SMA | `SMA_20`, `SMA_50` | Simple moving average |
| RSI | `RSI_14` | Wilder's smoothing, 14-period default |
| MACD | `MACD`, `MACD_Signal`, `MACD_Hist` | 12/26/9 default (EMA-based) |
| Bollinger Bands | `BB_Middle/Upper/Lower/Width/PercentB` | 20-period, 2 std dev default |
| ATR | `ATR_14` | Wilder's smoothing, 14-period default |

## Candlestick patterns implemented

| Pattern | Column | Logic summary |
|---|---|---|
| Doji | `Doji` | Body ≤ 5% of full candle range |
| Hammer | `Hammer` | Small body, long lower wick, short upper wick |
| Inverted Hammer | `InvertedHammer` | Small body, long upper wick, short lower wick |
| Bullish Engulfing | `Bullish_Engulfing` | Green candle body fully engulfs prior red candle body |
| Bearish Engulfing | `Bearish_Engulfing` | Red candle body fully engulfs prior green candle body |

## A note on the requested setup commands

Three commands from the original task list weren't run here since this
sandbox has no network access and isn't a Claude Code / CLI context:

- `npx skills add lombiq/tailwind-agent-skills --skill tailwind-4-docs`
- `npx getdesign add vercel --force`
- `claude mcp add astro https://mcp.docs.astro.build/mcp`

Run these yourself in your local terminal when you're ready to wire up the
frontend/MCP tooling — they're unrelated to the Python data pipeline above
and don't block Phase 1.

## Phase 2 — ML Forecasting Engine & CLI

`src/models.py` trains and compares three forecasting models per ticker:

| Model | Backend | Fallback (if backend not installed) |
|---|---|---|
| Tree Ensemble | XGBoost | `sklearn.RandomForestRegressor` |
| LSTM | TensorFlow/Keras `LSTM(32)→Dense(16)→Dense(1)` | `sklearn.MLPRegressor` on flattened windows |
| Baseline | — | Drift-based moving-average extrapolation (no ML) |

**This environment has neither XGBoost nor TensorFlow installed**, so both
fallbacks are active — this is stated explicitly in the leaderboard's Model
column (e.g. `"LSTM (MLP fallback — TensorFlow not installed)"`) so it's
never ambiguous which backend actually ran. Install `xgboost` and
`tensorflow` from `requirements.txt` in an environment with the wheels
available to get the full-strength versions; no code changes needed.

### Pipeline

1. Each model is backtested with one-step-ahead walk-forward evaluation on
   a held-out tail (`--test-size`, default 30 trading days), scored by
   **RMSE** and **MAPE** on the reconstructed Close price.
2. Models are ranked by RMSE; the best one is refit on the full series and
   used to forecast the next `--horizon` (default 5) trading days.
3. Predicted **Close** comes from the model's forecast; **High/Low** are
   derived as an ATR-scaled band around Close that widens with
   `sqrt(day)` — the standard random-walk uncertainty scaling.
4. **Market Mood** (Bullish/Bearish/Sideways) comes from the forecast's
   5-day % change vs configurable thresholds (±1.5% by default).
5. **Buy/Hold/Sell signal** combines Market Mood with current RSI and MACD
   histogram via simple rules (see `derive_signal()` in `models.py`).

> **Not financial advice.** The mood/signal logic is a simple, transparent
> heuristic for educational and demo purposes — it is not investment advice
> and shouldn't be the basis for real trading decisions.

### CLI (`src/cli.py`)

```bash
cd src

# Live NSE ticker (needs internet + yfinance)
python cli.py forecast --ticker RELIANCE.NS --period 2y

# From a local CSV (e.g. one saved by fetch_stock_data in Phase 1)
python cli.py forecast --csv ../data/raw/RELIANCE_NS_1d.csv

# Fully offline demo — synthetic data, no network required.
# This is what was used to verify the CLI runs end-to-end in this sandbox.
python cli.py forecast --demo

# Custom horizon / backtest window, and save the forecast
python cli.py forecast --ticker TCS.NS --horizon 7 --test-size 45 --save ../data/processed/tcs_forecast.csv
```

Output includes: a model leaderboard table, a 5-day Close/High/Low forecast
table, and a Market Mood + Buy/Hold/Sell panel with rationale — all rendered
with `tabulate` (+ `colorama` coloring when available).

Verified in this sandbox with `python cli.py forecast --demo`, including
`--csv` input and `--save` output, and a clean (non-traceback) error message
when `--ticker` is used without `yfinance`/network available.

## Status

**Phase 1: complete. Phase 2: complete.** Awaiting confirmation before Phase 3.
