# NSE Stock Prediction Engine

A modular Python framework for end-to-end stock prediction on the National Stock Exchange (NSE) of India. Features automated data ingestion, custom technical indicator calculation, candlestick pattern detection, and a multi-model ML forecasting pipeline with walking backtests and interactive CLI reporting.

---

## Features

- **Automated Data Pipeline**: Direct integration with `yfinance` to fetch high-frequency OHLCV data for standard NSE tickers (`.NS`).
- **Feature Engineering**: Built-in, high-performance implementations of popular technical indicators (RSI, MACD, Bollinger Bands, ATR, SMAs).
- **Candlestick Pattern Recognition**: Automated detection of Doji, Hammer, Inverted Hammer, and Engulfing patterns.
- **Multi-Model Forecasting Engine**: Dynamic evaluation engine comparing Tree Ensembles (XGBoost / RandomForest), LSTMs (TensorFlow / MLP), and Baseline models.
- **Realistic Walk-Forward Backtesting**: One-step-ahead walk-forward validation scored by RMSE and MAPE.
- **Uncertainty Band Modeling**: ATR-scaled band projections for High/Low values scaled by a sqrt(t) factor.
- **CLI & Visual Reporting**: Color-coded summary dashboards, backtest leaderboards, and market mood heuristics.
- **Offline Reliability**: Full synthetic testing suite allowing pipeline execution without an active internet connection.

---

## Project Structure

```text
nse_stock_prediction/
├── config/                  # Ticker configurations & model hyperparameter files
├── data/
│   ├── raw/                 # Ingested raw OHLCV datasets
│   └── processed/           # Feature-engineered datasets
├── logs/                    # Application and runtime execution logs
├── models/                  # Saved binary model artifacts
├── notebooks/               # Prototyping, statistical analysis, and EDA
├── src/
│   ├── cli.py               # Command-Line Interface execution tool
│   ├── data_loader.py       # Fetching, indicator math, and pattern engineering
│   └── models.py            # Forecasting engines, backtesting, and mood heuristics
├── tests/
│   └── test_data_loader_offline.py  # Synthetic-data offline validation suite
├── README.md
└── requirements.txt

Installation & Setup
Prerequisites
 * Python 3.9+
 * Virtual environment tool (venv or conda)
Quick Setup
 * Clone the repository:
   git clone [https://github.com/your-username/nse_stock_prediction.git](https://github.com/your-username/nse_stock_prediction.git)
cd nse_stock_prediction

 * Set up a virtual environment:
   python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

 * Install dependencies:
   pip install --upgrade pip
pip install -r requirements.txt

Data & Feature Pipeline
Supported Indicators
| Indicator | Column Name | Configuration Defaults | Description |
|---|---|---|---|
| Simple Moving Average | SMA_20, SMA_50 | 20, 50 periods | Trend direction indicators |
| Relative Strength Index | RSI_14 | 14 periods (Wilder's Smoothing) | Momentum oscillator |
| MACD | MACD, MACD_Signal, MACD_Hist | 12, 26, 9 EMA periods | Moving Average Convergence Divergence |
| Bollinger Bands | BB_Upper, BB_Middle, BB_Lower, BB_Width, BB_PercentB | 20 periods, 2 std dev | Volatility bands |
| Average True Range | ATR_14 | 14 periods | Absolute volatility metric |
Candlestick Patterns
| Pattern | Column Name | Condition Summary |
|---|---|---|
| Doji | Doji | Body height <= 5% of total candle range |
| Hammer | Hammer | Small upper body, long lower shadow, minimal upper wick |
| Inverted Hammer | InvertedHammer | Small lower body, long upper shadow, minimal lower wick |
| Bullish Engulfing | Bullish_Engulfing | Bullish candle body fully overlaps prior bearish body |
| Bearish Engulfing | Bearish_Engulfing | Bearish candle body fully overlaps prior bullish body |
Usage Guide
1. Python API
from src.data_loader import build_feature_dataset, fetch_stock_data, add_technical_indicators

# Option A: Run the end-to-end automated pipeline
df_tcs = build_feature_dataset("TCS.NS", period="2y", interval="1d")

# Option B: Step-by-step modular pipeline
df = fetch_stock_data("RELIANCE.NS", period="2y", interval="1d")
df = add_technical_indicators(df)

2. Command Line Interface (CLI)
The engine provides a built-in interactive CLI interface via src/cli.py.
cd src

# Run live forecast for an NSE ticker (Requires Internet)
python cli.py forecast --ticker RELIANCE.NS --period 2y

# Run forecast using a local CSV input file
python cli.py forecast --csv ../data/raw/RELIANCE_NS_1d.csv

# Run an end-to-end demo mode (Synthetic data, offline ready)
python cli.py forecast --demo

# Customize parameters and output destination
python cli.py forecast --ticker TCS.NS --horizon 7 --test-size 45 --save ../data/processed/tcs_forecast.csv

ML Forecasting Engine Details
The model execution suite continuously backtests three distinct algorithm choices per target ticker:
 * Tree Ensemble Engine: Native XGBoost Regressor (falls back to RandomForestRegressor if XGBoost is absent).
 * Sequential Neural Engine: TensorFlow/Keras LSTM(32) -> Dense(16) -> Dense(1) (falls back to MLPRegressor on windowed arrays).
 * Baseline Extrapolation Engine: Drift-based moving average baseline for baseline performance verification.
Signal Generation Heuristics
 * Forecast High/Low Limits: Calculated by applying ATR volatility buffers expanding dynamically over horizon t by \sqrt{t}.
 * Market Mood: Derived from the projected 5-day return trajectory (>= +1.5% Bullish, <= -1.5% Bearish, otherwise Sideways).
 * Trading Signal: Rule-based synthesis combining market mood, overbought/oversold RSI readings, and MACD histogram trends.
Offline Testing & Validation
To test technical indicators, pattern recognition rules, and model scripts without making external network calls, run the offline verification test suite:
python tests/test_data_loader_offline.py

This generates synthetic multi-day price series, injects pre-determined candlestick patterns, and verifies feature output metrics deterministically.
Disclaimer
> Disclaimer: This codebase and generated trading signals are intended strictly for educational, analytical, and demonstration purposes. Market models and mood heuristics provided do not constitute financial advice. Real trading involves significant risk of capital loss.
>
