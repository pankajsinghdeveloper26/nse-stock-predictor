"""
server.py
================
Phase 3 core module for the NSE Stock Prediction project.

Production-ready FastAPI application exposing the Phase 1/2 pipeline
(data_loader.py + models.py, wired together in services.py) over HTTP.

Endpoints
---------
    GET  /                          -> API info
    GET  /api/health                -> liveness/readiness check
    GET  /api/stock/{ticker}        -> historical OHLCV + technical indicators
    GET  /api/forecast/{ticker}     -> 5-day (configurable) forecast, model
                                        leaderboard, best model, Buy/Hold/Sell
    GET  /api/market-mood           -> sentiment across a basket of NSE presets

Run locally
-----------
    uvicorn server:app --reload --host 0.0.0.0 --port 8000

Then browse the interactive docs at http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import services

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("server")

# --------------------------------------------------------------------------- #
# App setup
# --------------------------------------------------------------------------- #
app = FastAPI(
    title="NSE Stock Prediction API",
    description=(
        "Historical OHLCV + technical indicators, multi-model 5-day forecasts, "
        "and market-mood sentiment for NSE stocks. Educational demo — NOT "
        "financial advice."
    ),
    version="1.0.0",
    contact={"name": "NSE Stock Prediction Project"},
)

# CORS: configurable via CORS_ORIGINS env var (comma-separated). Defaults to
# "*" for local/demo use — tighten this for a real production deployment.
_cors_origins_env = os.getenv("CORS_ORIGINS", "*")
_allow_origins = (
    ["*"] if _cors_origins_env.strip() == "*"
    else [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=_allow_origins != ["*"],  # can't combine "*" with credentials
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Request timing / access log middleware
# --------------------------------------------------------------------------- #
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %d (%.1f ms)",
        request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


# --------------------------------------------------------------------------- #
# Centralized exception handling
# --------------------------------------------------------------------------- #
@app.exception_handler(services.TickerNotFoundError)
async def ticker_not_found_handler(request: Request, exc: services.TickerNotFoundError):
    return JSONResponse(status_code=404, content={"error": "ticker_not_found", "detail": str(exc)})


@app.exception_handler(services.InsufficientDataError)
async def insufficient_data_handler(request: Request, exc: services.InsufficientDataError):
    return JSONResponse(status_code=422, content={"error": "insufficient_data", "detail": str(exc)})


@app.exception_handler(services.ForecastError)
async def forecast_error_handler(request: Request, exc: services.ForecastError):
    return JSONResponse(status_code=500, content={"error": "forecast_failed", "detail": str(exc)})


@app.exception_handler(services.DependencyMissingError)
async def dependency_missing_handler(request: Request, exc: services.DependencyMissingError):
    return JSONResponse(
        status_code=503,
        content={
            "error": "dependency_missing",
            "detail": str(exc),
            "hint": "Install backend requirements: pip install -r requirements.txt",
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": "bad_request", "detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "detail": "An unexpected error occurred."},
    )


# --------------------------------------------------------------------------- #
# Health / info
# --------------------------------------------------------------------------- #
@app.get("/", tags=["meta"])
async def root():
    return {
        "name": "NSE Stock Prediction API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": [
            "/api/health",
            "/api/stock/{ticker}",
            "/api/forecast/{ticker}",
            "/api/market-mood",
        ],
        "disclaimer": "Educational demo. NOT financial advice.",
    }


@app.get("/api/health", tags=["meta"])
async def health():
    return {"status": "ok", "service": "nse-stock-prediction-api"}


# --------------------------------------------------------------------------- #
# GET /api/stock/{ticker}
# --------------------------------------------------------------------------- #
@app.get("/api/stock/{ticker}", tags=["stock"])
async def get_stock(
    ticker: str,
    period: str = Query(
        "1y", description="yfinance period, e.g. 6mo, 1y, 2y, 5y, max",
    ),
    interval: str = Query(
        "1d", description="yfinance interval, e.g. 1d, 1h, 15m",
    ),
):
    """
    Historical OHLCV data plus technical indicators (SMA 20/50, RSI, MACD,
    Bollinger Bands, ATR) and candlestick pattern flags for an NSE ticker.

    `ticker` accepts a bare symbol ("RELIANCE") or a full Yahoo Finance
    symbol ("RELIANCE.NS") — it will be normalized automatically.
    """
    try:
        return services.get_stock_payload(ticker, period=period, interval=interval)
    except (
        services.TickerNotFoundError,
        services.InsufficientDataError,
        services.DependencyMissingError,
        ValueError,
    ):
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in get_stock(%s)", ticker)
        raise HTTPException(status_code=500, detail=f"Failed to load stock data: {exc}") from exc


# --------------------------------------------------------------------------- #
# GET /api/forecast/{ticker}
# --------------------------------------------------------------------------- #
@app.get("/api/forecast/{ticker}", tags=["forecast"])
async def get_forecast(
    ticker: str,
    period: str = Query(
        "2y", description="History window used for backtesting + training, e.g. 1y, 2y, 5y",
    ),
    interval: str = Query("1d", description="yfinance interval (daily recommended: 1d)"),
    horizon: int = Query(5, ge=1, le=30, description="Number of trading days to forecast ahead"),
    test_size: int = Query(
        30, ge=10, le=250, description="Holdout window (trading days) for backtest/ranking",
    ),
):
    """
    Runs the full Phase 2 pipeline: backtests the Tree Ensemble, LSTM, and
    Baseline models on a held-out tail of the series, ranks them by
    RMSE/MAPE, refits the best model on the full history, and forecasts
    `horizon` trading days of Close/High/Low. Also derives a Market Mood
    (Bullish/Bearish/Sideways) and a Buy/Hold/Sell signal from the
    forecast trend plus RSI/MACD.

    NOT financial advice — see the `disclaimer` field in the response.
    """
    try:
        return services.get_forecast_payload(
            ticker, period=period, interval=interval, horizon=horizon, test_size=test_size,
        )
    except (
        services.TickerNotFoundError,
        services.InsufficientDataError,
        services.ForecastError,
        services.DependencyMissingError,
        ValueError,
    ):
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in get_forecast(%s)", ticker)
        raise HTTPException(status_code=500, detail=f"Failed to generate forecast: {exc}") from exc


# --------------------------------------------------------------------------- #
# GET /api/market-mood
# --------------------------------------------------------------------------- #
@app.get("/api/market-mood", tags=["forecast"])
async def get_market_mood(
    tickers: Optional[str] = Query(
        None,
        description=(
            "Optional comma-separated ticker list, e.g. 'RELIANCE,TCS,INFY'. "
            "Defaults to a preset basket of top NSE large-caps."
        ),
    ),
    period: str = Query("1y", description="History window for each ticker's pipeline"),
    interval: str = Query("1d", description="yfinance interval (daily recommended: 1d)"),
    horizon: int = Query(5, ge=1, le=30, description="Forecast horizon (trading days) per ticker"),
    test_size: int = Query(
        20, ge=10, le=250, description="Backtest holdout window (trading days) per ticker",
    ),
):
    """
    Aggregate market sentiment across a basket of NSE tickers. Runs the
    forecasting pipeline per ticker (skipping and reporting any that fail)
    and rolls the individual Bullish/Bearish/Sideways moods and
    Buy/Hold/Sell signals up into an overall market-mood reading.

    This can be slow for larger baskets since each ticker runs its own
    backtest + model fit — results are cached for a short TTL per ticker.
    """
    ticker_list = None
    if tickers:
        ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]

    try:
        return services.get_market_mood_payload(
            tickers=ticker_list, period=period, interval=interval,
            horizon=horizon, test_size=test_size,
        )
    except (services.ForecastError, ValueError):
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in get_market_mood()")
        raise HTTPException(status_code=500, detail=f"Failed to compute market mood: {exc}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
