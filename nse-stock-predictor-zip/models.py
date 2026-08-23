"""
models.py
==========
Phase 2 core module for the NSE Stock Prediction project.

Responsibilities
-----------------
1. Train and compare three forecasting models on a single ticker's
   feature-engineered OHLCV history (output of `data_loader.py`):
       - Tree ensemble: XGBoost if installed, else RandomForest (sklearn).
       - LSTM: a real Keras/TensorFlow LSTM if TensorFlow is installed,
         else an MLP-on-windowed-features fallback with the same interface
         (clearly labeled as a fallback in all reports).
       - Baseline: drift-based moving-average extrapolation.
2. Forecast the next N trading days' Close, and derive High/Low bands
   from ATR-scaled uncertainty that widens with the forecast horizon.
3. Backtest each model with one-step-ahead walk-forward evaluation on a
   held-out tail of the series, rank by RMSE/MAPE, and pick the best.
4. Derive a Market Mood (Bullish/Bearish/Sideways) from the winning
   model's forecast trend, and a simple Buy/Hold/Sell signal that also
   consults RSI and MACD.

IMPORTANT: The Buy/Hold/Sell signal and Market Mood are simple, rule-based
heuristics for educational/demo purposes. They are NOT financial advice.

Usage
-----
    from data_loader import fetch_stock_data, add_technical_indicators, detect_candlestick_patterns
    from models import run_forecast_pipeline

    df = fetch_stock_data("RELIANCE.NS", period="2y", interval="1d")
    df = add_technical_indicators(df)
    df = detect_candlestick_patterns(df)

    result = run_forecast_pipeline(df, ticker="RELIANCE.NS", horizon=5, test_size=30)
    print(result.leaderboard)
    print(result.forecast_df)
    print(result.market_mood, result.signal)
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("models")

# --------------------------------------------------------------------------- #
# Optional heavy dependencies — degrade gracefully if not installed
# --------------------------------------------------------------------------- #
try:
    from xgboost import XGBRegressor
    _XGBOOST_AVAILABLE = True
except ImportError:
    _XGBOOST_AVAILABLE = False

try:
    import tensorflow as tf
    from tensorflow.keras import Sequential
    from tensorflow.keras.layers import LSTM, Dense
    _TENSORFLOW_AVAILABLE = True
except ImportError:
    _TENSORFLOW_AVAILABLE = False


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
LAG_RETURNS = 5          # how many lagged daily returns to use as features
SEQ_WINDOW = 10          # LSTM lookback window (trading days)
DEFAULT_HORIZON = 5      # trading days to forecast
DEFAULT_TEST_SIZE = 30   # holdout days for backtest/ranking
RANDOM_STATE = 42

FEATURE_COLS_BASE = [
    "RSI_14", "MACD", "MACD_Signal", "MACD_Hist",
    "BB_PercentB", "BB_Width", "ATR_14",
]


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class BacktestScore:
    model_name: str
    rmse: float
    mape: float
    rank: int = 0
    note: str = ""


@dataclass
class ForecastResult:
    ticker: str
    as_of_date: pd.Timestamp
    last_close: float
    leaderboard: pd.DataFrame          # model comparison table
    best_model_name: str
    forecast_df: pd.DataFrame          # Day / Date / Predicted Close/High/Low
    market_mood: str
    signal: str
    rationale: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Feature engineering
# --------------------------------------------------------------------------- #
def _log_return(close: pd.Series) -> pd.Series:
    return np.log(close / close.shift(1))


def build_tabular_features(df: pd.DataFrame, n_lags: int = LAG_RETURNS) -> pd.DataFrame:
    """
    Build a tabular (row-per-day) feature set for the tree ensemble model.

    Assumes `df` already has technical indicator columns from
    `data_loader.add_technical_indicators()`.

    Target column `y_next_ret` = next day's log return of Close.
    """
    out = df.copy()
    out["log_ret"] = _log_return(out["Close"])

    for lag in range(1, n_lags + 1):
        out[f"lag_ret_{lag}"] = out["log_ret"].shift(lag)

    # Normalize trend indicators relative to price so they generalize across tickers
    out["sma20_rel"] = out["SMA_20"] / out["Close"] - 1
    out["sma50_rel"] = out["SMA_50"] / out["Close"] - 1
    out["atr_rel"] = out["ATR_14"] / out["Close"]

    feature_cols = (
        [f"lag_ret_{lag}" for lag in range(1, n_lags + 1)]
        + ["RSI_14", "MACD", "MACD_Signal", "MACD_Hist", "BB_PercentB", "BB_Width",
           "sma20_rel", "sma50_rel", "atr_rel"]
    )

    out["y_next_ret"] = out["log_ret"].shift(-1)

    keep = feature_cols + ["y_next_ret", "Close"]
    out = out[keep].dropna()
    out.attrs["feature_cols"] = feature_cols
    return out


def build_sequence_features(
    df: pd.DataFrame, window: int = SEQ_WINDOW
) -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex, StandardScaler, list[str]]:
    """
    Build windowed sequences for the LSTM (or its fallback) model.

    Returns
    -------
    X : np.ndarray, shape (n_samples, window, n_features)
    y : np.ndarray, shape (n_samples,)          -- next-day log return
    idx : DatetimeIndex aligned with y (the *target* day's date)
    scaler : fitted StandardScaler (fit on flattened training features)
    feature_cols : list of column names used
    """
    tmp = df.copy()
    tmp["log_ret"] = _log_return(tmp["Close"])
    tmp["sma20_rel"] = tmp["SMA_20"] / tmp["Close"] - 1
    tmp["sma50_rel"] = tmp["SMA_50"] / tmp["Close"] - 1
    tmp["atr_rel"] = tmp["ATR_14"] / tmp["Close"]

    feature_cols = ["log_ret", "RSI_14", "MACD_Hist", "BB_PercentB", "sma20_rel", "atr_rel"]
    tmp = tmp[feature_cols + ["Close"]].dropna()

    values = tmp[feature_cols].values
    closes = tmp["Close"].values
    dates = tmp.index

    X, y, idx = [], [], []
    for i in range(window, len(tmp) - 1):
        X.append(values[i - window:i])
        next_ret = np.log(closes[i + 1] / closes[i])
        y.append(next_ret)
        idx.append(dates[i + 1])

    X = np.array(X)
    y = np.array(y)
    idx = pd.DatetimeIndex(idx)

    scaler = StandardScaler()
    n_samples, win, n_feat = X.shape
    scaler.fit(X.reshape(-1, n_feat))

    return X, y, idx, scaler, feature_cols


def _scale_sequences(X: np.ndarray, scaler: StandardScaler) -> np.ndarray:
    n_samples, win, n_feat = X.shape
    flat = scaler.transform(X.reshape(-1, n_feat))
    return flat.reshape(n_samples, win, n_feat)


# --------------------------------------------------------------------------- #
# Model 1: Tree ensemble (XGBoost if available, else RandomForest)
# --------------------------------------------------------------------------- #
class TreeEnsembleForecaster:
    """
    Predicts next-day log return from lagged-return + indicator features.
    Uses XGBoost if installed (generally stronger on tabular data), else
    falls back to sklearn's RandomForestRegressor.
    """

    def __init__(self, random_state: int = RANDOM_STATE):
        self.random_state = random_state
        if _XGBOOST_AVAILABLE:
            self.backend_name = "XGBoost"
            self.model = XGBRegressor(
                n_estimators=400,
                max_depth=4,
                learning_rate=0.03,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=random_state,
                verbosity=0,
            )
        else:
            self.backend_name = "RandomForest (XGBoost not installed — fallback)"
            self.model = RandomForestRegressor(
                n_estimators=400,
                max_depth=8,
                min_samples_leaf=3,
                random_state=random_state,
                n_jobs=-1,
            )
        self.feature_cols: list[str] = []

    @property
    def display_name(self) -> str:
        return f"Tree Ensemble ({self.backend_name})"

    def fit(self, feat_df: pd.DataFrame) -> "TreeEnsembleForecaster":
        self.feature_cols = feat_df.attrs["feature_cols"]
        X = feat_df[self.feature_cols].values
        y = feat_df["y_next_ret"].values
        self.model.fit(X, y)
        return self

    def predict_return(self, feature_row: pd.Series) -> float:
        X = feature_row[self.feature_cols].values.reshape(1, -1)
        return float(self.model.predict(X)[0])

    def forecast_horizon(self, df: pd.DataFrame, horizon: int = DEFAULT_HORIZON) -> list[float]:
        """Recursive multi-step forecast: predict 1 day, roll lag features forward, repeat."""
        working = df.copy()
        preds = []
        for _ in range(horizon):
            feat = build_tabular_features(working, n_lags=LAG_RETURNS)
            last_row = feat.iloc[-1]
            next_ret = self.predict_return(last_row)
            preds.append(next_ret)

            next_close = working["Close"].iloc[-1] * np.exp(next_ret)
            new_row = working.iloc[-1:].copy()
            new_index = working.index[-1] + pd.tseries.offsets.BDay(1)
            new_row.index = [new_index]
            new_row["Close"] = next_close
            # Keep High/Low/Open/indicators approx. constant-shifted; ATR/RSI/MACD
            # recompute naturally on the next loop iteration via rolling windows.
            new_row["Open"] = next_close
            new_row["High"] = next_close
            new_row["Low"] = next_close
            working = pd.concat([working, new_row])
            # Recompute indicators so RSI/MACD/SMA/ATR adapt to the new synthetic bar
            working = _recompute_indicators_inplace(working)
        return preds


# --------------------------------------------------------------------------- #
# Model 2: LSTM (TensorFlow if available, else MLP-on-window fallback)
# --------------------------------------------------------------------------- #
class LSTMForecaster:
    """
    Predicts next-day log return from a sliding window of recent
    return/indicator features.

    If TensorFlow is installed, this is a genuine Keras LSTM:
        LSTM(32) -> Dense(16, relu) -> Dense(1)

    If TensorFlow is NOT installed (as in this sandbox), it falls back to
    an sklearn MLPRegressor trained on the flattened window — same
    interface, clearly labeled everywhere as a fallback. Install
    `tensorflow` and re-run to get the real recurrent model.
    """

    def __init__(self, window: int = SEQ_WINDOW, random_state: int = RANDOM_STATE):
        self.window = window
        self.random_state = random_state
        self.scaler: Optional[StandardScaler] = None
        self.feature_cols: list[str] = []
        self.uses_tensorflow = _TENSORFLOW_AVAILABLE
        self.model = None

    @property
    def display_name(self) -> str:
        if self.uses_tensorflow:
            return "LSTM (TensorFlow/Keras)"
        return "LSTM (MLP fallback — TensorFlow not installed)"

    def fit(self, df: pd.DataFrame) -> "LSTMForecaster":
        X, y, idx, scaler, feature_cols = build_sequence_features(df, window=self.window)
        self.scaler = scaler
        self.feature_cols = feature_cols
        Xs = _scale_sequences(X, scaler)

        if self.uses_tensorflow:
            tf.random.set_seed(self.random_state)
            self.model = Sequential([
                LSTM(32, input_shape=(Xs.shape[1], Xs.shape[2])),
                Dense(16, activation="relu"),
                Dense(1),
            ])
            self.model.compile(optimizer="adam", loss="mse")
            self.model.fit(Xs, y, epochs=30, batch_size=16, verbose=0)
        else:
            self.model = MLPRegressor(
                hidden_layer_sizes=(32, 16),
                activation="relu",
                max_iter=800,
                random_state=self.random_state,
            )
            flat = Xs.reshape(Xs.shape[0], -1)
            self.model.fit(flat, y)
        return self

    def _predict_batch(self, Xs: np.ndarray) -> np.ndarray:
        if self.uses_tensorflow:
            return self.model.predict(Xs, verbose=0).flatten()
        flat = Xs.reshape(Xs.shape[0], -1)
        return self.model.predict(flat)

    def predict_return_from_window(self, window_df: pd.DataFrame) -> float:
        tmp = window_df.copy()
        tmp["log_ret"] = _log_return(tmp["Close"])
        tmp["sma20_rel"] = tmp["SMA_20"] / tmp["Close"] - 1
        tmp["sma50_rel"] = tmp["SMA_50"] / tmp["Close"] - 1
        tmp["atr_rel"] = tmp["ATR_14"] / tmp["Close"]
        tmp = tmp[self.feature_cols].dropna()
        window_vals = tmp.values[-self.window:]
        X = window_vals.reshape(1, self.window, len(self.feature_cols))
        Xs = _scale_sequences(X, self.scaler)
        return float(self._predict_batch(Xs)[0])

    def forecast_horizon(self, df: pd.DataFrame, horizon: int = DEFAULT_HORIZON) -> list[float]:
        working = df.copy()
        preds = []
        for _ in range(horizon):
            next_ret = self.predict_return_from_window(working)
            preds.append(next_ret)

            next_close = working["Close"].iloc[-1] * np.exp(next_ret)
            new_row = working.iloc[-1:].copy()
            new_index = working.index[-1] + pd.tseries.offsets.BDay(1)
            new_row.index = [new_index]
            new_row["Close"] = next_close
            new_row["Open"] = next_close
            new_row["High"] = next_close
            new_row["Low"] = next_close
            working = pd.concat([working, new_row])
            working = _recompute_indicators_inplace(working)
        return preds


# --------------------------------------------------------------------------- #
# Model 3: Baseline — drift-based moving average extrapolation
# --------------------------------------------------------------------------- #
class BaselineMAForecaster:
    """
    No-ML baseline: extrapolates using the mean of recent daily log
    returns (drift) blended with the SMA20 vs SMA50 trend direction.
    Every real model must beat this to be worth using.
    """

    def __init__(self, drift_window: int = 10):
        self.drift_window = drift_window
        self.drift: float = 0.0

    @property
    def display_name(self) -> str:
        return "Baseline (Moving Average Drift)"

    def fit(self, df: pd.DataFrame) -> "BaselineMAForecaster":
        log_ret = _log_return(df["Close"]).dropna()
        recent_drift = log_ret.tail(self.drift_window).mean()
        sma20, sma50 = df["SMA_20"].iloc[-1], df["SMA_50"].iloc[-1]
        trend_adj = 0.0002 if sma20 > sma50 else (-0.0002 if sma20 < sma50 else 0.0)
        self.drift = float(recent_drift + trend_adj)
        return self

    def predict_return(self, *_args, **_kwargs) -> float:
        return self.drift

    def forecast_horizon(self, df: pd.DataFrame, horizon: int = DEFAULT_HORIZON) -> list[float]:
        return [self.drift] * horizon


# --------------------------------------------------------------------------- #
# Indicator recompute helper (used during recursive multi-step forecasting)
# --------------------------------------------------------------------------- #
def _recompute_indicators_inplace(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute RSI/MACD/SMA/BB/ATR after appending a synthetic forecast bar."""
    from data_loader import (
        compute_rsi, compute_macd, compute_sma, compute_bollinger_bands, compute_atr,
    )
    out = df.copy()
    out["SMA_20"] = compute_sma(out["Close"], 20)
    out["SMA_50"] = compute_sma(out["Close"], 50)
    out["RSI_14"] = compute_rsi(out["Close"], 14)
    macd_df = compute_macd(out["Close"])
    out[["MACD", "MACD_Signal", "MACD_Hist"]] = macd_df[["MACD", "MACD_Signal", "MACD_Hist"]]
    bb_df = compute_bollinger_bands(out["Close"])
    out[["BB_Middle", "BB_Upper", "BB_Lower", "BB_Width", "BB_PercentB"]] = bb_df
    out["ATR_14"] = compute_atr(out["High"], out["Low"], out["Close"], 14)
    return out


# --------------------------------------------------------------------------- #
# Backtesting / ranking
# --------------------------------------------------------------------------- #
def _rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def _mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    mask = actual != 0
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


def backtest_tree(df: pd.DataFrame, test_size: int) -> BacktestScore:
    feat = build_tabular_features(df)
    if len(feat) <= test_size + 20:
        raise ValueError("Not enough data for a reliable backtest; use a longer period.")

    train_feat, test_feat = feat.iloc[:-test_size], feat.iloc[-test_size:]
    model = TreeEnsembleForecaster().fit(train_feat)

    X_test = test_feat[model.feature_cols].values
    pred_ret = model.model.predict(X_test)

    # Convert returns -> price level using the *actual* previous close (one-step-ahead)
    prev_close = df["Close"].reindex(test_feat.index).shift(0)  # placeholder, replaced below
    close_series = df["Close"]
    actual_prev_close = np.array([
        close_series.loc[:d].iloc[-2] if len(close_series.loc[:d]) >= 2 else close_series.loc[d]
        for d in test_feat.index
    ])
    pred_close = actual_prev_close * np.exp(pred_ret)
    actual_close = test_feat["Close"].values

    return BacktestScore(
        model_name=model.display_name,
        rmse=_rmse(actual_close, pred_close),
        mape=_mape(actual_close, pred_close),
    )


def backtest_lstm(df: pd.DataFrame, test_size: int, window: int = SEQ_WINDOW) -> BacktestScore:
    X, y, idx, _, _ = build_sequence_features(df, window=window)
    if len(X) <= test_size + 20:
        raise ValueError("Not enough data for a reliable backtest; use a longer period.")

    X_train, y_train = X[:-test_size], y[:-test_size]
    X_test, y_test = X[-test_size:], y[-test_size:]
    idx_test = idx[-test_size:]

    scaler = StandardScaler()
    n_feat = X_train.shape[2]
    scaler.fit(X_train.reshape(-1, n_feat))
    Xs_train = _scale_sequences(X_train, scaler)
    Xs_test = _scale_sequences(X_test, scaler)

    lstm = LSTMForecaster(window=window)
    lstm.scaler = scaler
    lstm.feature_cols = ["log_ret", "RSI_14", "MACD_Hist", "BB_PercentB", "sma20_rel", "atr_rel"]

    if _TENSORFLOW_AVAILABLE:
        tf.random.set_seed(RANDOM_STATE)
        lstm.model = Sequential([
            LSTM(32, input_shape=(Xs_train.shape[1], Xs_train.shape[2])),
            Dense(16, activation="relu"),
            Dense(1),
        ])
        lstm.model.compile(optimizer="adam", loss="mse")
        lstm.model.fit(Xs_train, y_train, epochs=30, batch_size=16, verbose=0)
    else:
        lstm.model = MLPRegressor(hidden_layer_sizes=(32, 16), max_iter=800, random_state=RANDOM_STATE)
        lstm.model.fit(Xs_train.reshape(Xs_train.shape[0], -1), y_train)

    pred_ret = lstm._predict_batch(Xs_test)

    close_series = df["Close"]
    actual_prev_close = np.array([
        close_series.loc[:d].iloc[-2] if len(close_series.loc[:d]) >= 2 else close_series.loc[d]
        for d in idx_test
    ])
    pred_close = actual_prev_close * np.exp(pred_ret)
    actual_close = close_series.reindex(idx_test).values

    return BacktestScore(
        model_name=lstm.display_name,
        rmse=_rmse(actual_close, pred_close),
        mape=_mape(actual_close, pred_close),
    )


def backtest_baseline(df: pd.DataFrame, test_size: int) -> BacktestScore:
    close_series = df["Close"]
    dates = close_series.index[-test_size:]
    preds, actuals = [], []

    for d in dates:
        history = df.loc[:d].iloc[:-1]  # everything strictly before day d
        if len(history) < 15:
            continue
        baseline = BaselineMAForecaster().fit(history)
        prev_close = history["Close"].iloc[-1]
        pred_close = prev_close * np.exp(baseline.drift)
        preds.append(pred_close)
        actuals.append(close_series.loc[d])

    return BacktestScore(
        model_name=BaselineMAForecaster().display_name,
        rmse=_rmse(np.array(actuals), np.array(preds)),
        mape=_mape(np.array(actuals), np.array(preds)),
    )


def rank_models(scores: list[BacktestScore]) -> pd.DataFrame:
    """
    Rank by RMSE primarily (lower is better); MAPE shown alongside.
    Returns a leaderboard DataFrame sorted best-first with a Rank column.
    """
    df = pd.DataFrame([{"Model": s.model_name, "RMSE": s.rmse, "MAPE (%)": s.mape, "Note": s.note} for s in scores])
    df = df.sort_values("RMSE").reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))
    return df


# --------------------------------------------------------------------------- #
# High / Low band construction from a Close forecast
# --------------------------------------------------------------------------- #
def _build_high_low_bands(
    df: pd.DataFrame, pred_returns: list[float], k: float = 0.6
) -> pd.DataFrame:
    """
    Convert a sequence of predicted daily log-returns into predicted
    Close/High/Low, with the High/Low band widening by sqrt(day) — the
    standard random-walk scaling for multi-step uncertainty — scaled by
    the latest ATR.
    """
    last_close = df["Close"].iloc[-1]
    last_atr = df["ATR_14"].iloc[-1]
    last_date = df.index[-1]

    rows = []
    close = last_close
    for day_idx, ret in enumerate(pred_returns, start=1):
        close = close * np.exp(ret)
        band = k * last_atr * np.sqrt(day_idx)
        rows.append({
            "Day": day_idx,
            "Date": (last_date + pd.tseries.offsets.BDay(day_idx)).date(),
            "Predicted_Close": round(close, 2),
            "Predicted_High": round(close + band, 2),
            "Predicted_Low": round(max(close - band, 0.01), 2),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Market mood & Buy/Hold/Sell signal
# --------------------------------------------------------------------------- #
def derive_market_mood(pct_change_5d: float, bullish_th: float = 1.5, bearish_th: float = -1.5) -> str:
    if pct_change_5d >= bullish_th:
        return "Bullish"
    if pct_change_5d <= bearish_th:
        return "Bearish"
    return "Sideways"


def derive_signal(mood: str, rsi: float, macd_hist: float) -> tuple[str, list[str]]:
    """
    Simple rule-based Buy/Hold/Sell heuristic combining forecast mood,
    RSI, and MACD histogram. NOT financial advice — for educational/demo
    use only.
    """
    rationale = []
    if mood == "Bullish" and rsi < 70 and macd_hist > 0:
        signal = "BUY"
        rationale.append(f"5-day forecast is Bullish, RSI ({rsi:.1f}) is not overbought, MACD histogram is positive.")
    elif mood == "Bearish" and rsi > 30 and macd_hist < 0:
        signal = "SELL"
        rationale.append(f"5-day forecast is Bearish, RSI ({rsi:.1f}) is not oversold, MACD histogram is negative.")
    else:
        signal = "HOLD"
        if mood == "Bullish" and rsi >= 70:
            rationale.append(f"Forecast is Bullish but RSI ({rsi:.1f}) suggests overbought conditions — caution.")
        elif mood == "Bearish" and rsi <= 30:
            rationale.append(f"Forecast is Bearish but RSI ({rsi:.1f}) suggests oversold conditions — caution.")
        else:
            rationale.append(f"Forecast mood is {mood} without strong RSI/MACD confirmation.")
    return signal, rationale


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_forecast_pipeline(
    df: pd.DataFrame,
    ticker: str = "UNKNOWN",
    horizon: int = DEFAULT_HORIZON,
    test_size: int = DEFAULT_TEST_SIZE,
) -> ForecastResult:
    """
    Full Phase 2 pipeline: backtest & rank the 3 models, pick the best,
    forecast `horizon` trading days ahead, and derive market mood + signal.

    `df` must already have technical indicators from
    `data_loader.add_technical_indicators()` (SMA_20/50, RSI_14, MACD*,
    BB_*, ATR_14) and a DatetimeIndex.
    """
    required_cols = ["Close", "High", "Low", "Open", "SMA_20", "SMA_50", "RSI_14",
                      "MACD", "MACD_Signal", "MACD_Hist", "BB_PercentB", "BB_Width", "ATR_14"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"Input DataFrame is missing required columns: {missing}. "
            "Run data_loader.add_technical_indicators() first."
        )

    logger.info("Backtesting models (test_size=%d trading days)...", test_size)
    scores = []
    for name, fn in [
        ("Tree Ensemble", backtest_tree),
        ("LSTM", backtest_lstm),
        ("Baseline", backtest_baseline),
    ]:
        try:
            scores.append(fn(df, test_size))
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s backtest failed (%s); excluding from leaderboard.", name, exc)

    if not scores:
        raise RuntimeError("All model backtests failed — check data quality/length.")

    leaderboard = rank_models(scores)
    best_model_name = leaderboard.iloc[0]["Model"]
    logger.info("Leaderboard:\n%s", leaderboard.to_string(index=False))
    logger.info("Best model: %s", best_model_name)

    # Fit the winning model on FULL data and forecast forward
    if best_model_name.startswith("Tree Ensemble"):
        feat = build_tabular_features(df)
        model = TreeEnsembleForecaster().fit(feat)
    elif best_model_name.startswith("LSTM"):
        model = LSTMForecaster().fit(df)
    else:
        model = BaselineMAForecaster().fit(df)

    pred_returns = model.forecast_horizon(df, horizon=horizon)
    forecast_df = _build_high_low_bands(df, pred_returns)

    pct_change_5d = (forecast_df["Predicted_Close"].iloc[-1] / df["Close"].iloc[-1] - 1) * 100
    mood = derive_market_mood(pct_change_5d)
    rsi_now = float(df["RSI_14"].iloc[-1])
    macd_hist_now = float(df["MACD_Hist"].iloc[-1])
    signal, rationale = derive_signal(mood, rsi_now, macd_hist_now)
    rationale.insert(0, f"{horizon}-day forecast implies a {pct_change_5d:+.2f}% move in Close "
                         f"(best model: {best_model_name}).")

    return ForecastResult(
        ticker=ticker,
        as_of_date=df.index[-1],
        last_close=float(df["Close"].iloc[-1]),
        leaderboard=leaderboard,
        best_model_name=best_model_name,
        forecast_df=forecast_df,
        market_mood=mood,
        signal=signal,
        rationale=rationale,
    )
