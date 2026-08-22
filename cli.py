#!/usr/bin/env python3
"""
cli.py
=======
Interactive terminal CLI for the NSE Stock Prediction project (Phase 2).

Fetches (or loads) OHLCV data, engineers features, trains/backtests the
three forecasting models, and prints a leaderboard + 5-day forecast +
market mood/signal as pretty terminal tables.

Examples
--------
    # Live NSE ticker (requires internet + yfinance)
    python cli.py forecast --ticker RELIANCE.NS --period 2y

    # From a previously saved CSV (e.g. data/raw/RELIANCE_NS_1d.csv)
    python cli.py forecast --csv data/raw/RELIANCE_NS_1d.csv

    # Offline demo with synthetic data — no network or file needed.
    # Useful for verifying the CLI works in an environment without
    # internet access.
    python cli.py forecast --demo

    # Custom horizon / backtest window
    python cli.py forecast --ticker TCS.NS --horizon 7 --test-size 45
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    _COLOR = True
except ImportError:  # pragma: no cover
    _COLOR = False

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data_loader import (  # noqa: E402
    fetch_stock_data,
    add_technical_indicators,
    detect_candlestick_patterns,
)
from models import run_forecast_pipeline, DEFAULT_HORIZON, DEFAULT_TEST_SIZE  # noqa: E402


# --------------------------------------------------------------------------- #
# Color helpers (fall back to plain text if colorama isn't available)
# --------------------------------------------------------------------------- #
def _c(text: str, color: str) -> str:
    if not _COLOR:
        return text
    mapping = {
        "green": Fore.GREEN,
        "red": Fore.RED,
        "yellow": Fore.YELLOW,
        "cyan": Fore.CYAN,
        "bold": Style.BRIGHT,
    }
    return f"{mapping.get(color, '')}{text}{Style.RESET_ALL}"


def _mood_color(mood: str) -> str:
    return {"Bullish": "green", "Bearish": "red", "Sideways": "yellow"}.get(mood, "cyan")


def _signal_color(signal: str) -> str:
    return {"BUY": "green", "SELL": "red", "HOLD": "yellow"}.get(signal, "cyan")


# --------------------------------------------------------------------------- #
# Synthetic data generator (for --demo, mirrors tests/test_data_loader_offline.py)
# --------------------------------------------------------------------------- #
def make_synthetic_ohlcv(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n)

    returns = rng.normal(loc=0.0007, scale=0.014, size=n)
    close = 1500 * np.cumprod(1 + returns)

    open_ = close * (1 + rng.normal(0, 0.004, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.006, n)))
    volume = rng.integers(500_000, 4_000_000, n)

    df = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    )
    df.index.name = "Date"
    return df


# --------------------------------------------------------------------------- #
# Data loading dispatch
# --------------------------------------------------------------------------- #
def load_data(args: argparse.Namespace) -> tuple[pd.DataFrame, str]:
    if args.demo:
        print(_c("→ Running in offline DEMO mode with synthetic OHLCV data "
                  "(no network call made).", "yellow"))
        df = make_synthetic_ohlcv()
        return df, "DEMO.SYNTH"

    if args.csv:
        print(f"→ Loading local CSV: {args.csv}")
        df = pd.read_csv(args.csv, index_col=0, parse_dates=True)
        df.index.name = "Date"
        ticker = Path(args.csv).stem
        return df, ticker

    if args.ticker:
        print(f"→ Fetching {args.ticker} from yfinance (period={args.period}, interval={args.interval})...")
        df = fetch_stock_data(args.ticker, period=args.period, interval=args.interval)
        return df, args.ticker

    raise SystemExit("Provide one of --ticker, --csv, or --demo. See --help.")


# --------------------------------------------------------------------------- #
# Pretty printing
# --------------------------------------------------------------------------- #
def print_header(ticker: str, as_of, last_close: float) -> None:
    title = f" NSE STOCK FORECAST — {ticker} "
    bar = "=" * max(len(title), 60)
    print("\n" + bar)
    print(_c(title.center(len(bar)), "bold"))
    print(bar)
    print(f"As of: {as_of.date() if hasattr(as_of, 'date') else as_of}   "
          f"Last Close: {_c(f'{last_close:.2f}', 'cyan')}")


def print_leaderboard(leaderboard: pd.DataFrame) -> None:
    print("\n" + _c("MODEL LEADERBOARD (backtest, lower RMSE/MAPE = better)", "bold"))
    display = leaderboard.copy()
    display["RMSE"] = display["RMSE"].map(lambda v: f"{v:.3f}")
    display["MAPE (%)"] = display["MAPE (%)"].map(lambda v: f"{v:.2f}")
    display = display.drop(columns=["Note"]) if "Note" in display.columns else display
    print(tabulate(display, headers="keys", tablefmt="fancy_grid", showindex=False))


def print_forecast(forecast_df: pd.DataFrame, best_model: str) -> None:
    print("\n" + _c(f"5-DAY FORECAST — best model: {best_model}", "bold"))
    print(tabulate(forecast_df, headers="keys", tablefmt="fancy_grid", showindex=False))


def print_mood_and_signal(mood: str, signal: str, rationale: list[str]) -> None:
    print("\n" + _c("MARKET MOOD & SIGNAL", "bold"))
    summary = [
        ["Market Mood", _c(mood, _mood_color(mood))],
        ["Signal", _c(signal, _signal_color(signal))],
    ]
    print(tabulate(summary, tablefmt="fancy_grid"))
    print("\nRationale:")
    for r in rationale:
        print(f"  • {r}")
    print(_c(
        "\nDisclaimer: This signal is a rule-based heuristic for educational/demo "
        "purposes only. It is NOT financial advice.", "yellow"
    ))


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="NSE Stock Prediction — interactive forecasting CLI (Phase 2).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fc = sub.add_parser("forecast", help="Run the full forecast pipeline and print results.")
    src = fc.add_mutually_exclusive_group(required=False)
    src.add_argument("--ticker", type=str, help="NSE ticker, e.g. RELIANCE.NS, TCS.NS")
    src.add_argument("--csv", type=str, help="Path to a local OHLCV CSV (Date-indexed)")
    src.add_argument("--demo", action="store_true", help="Use synthetic data (no network needed)")

    fc.add_argument("--period", type=str, default="2y", help="yfinance period (default: 2y)")
    fc.add_argument("--interval", type=str, default="1d", help="yfinance interval (default: 1d)")
    fc.add_argument("--horizon", type=int, default=DEFAULT_HORIZON, help="Trading days to forecast (default: 5)")
    fc.add_argument("--test-size", type=int, default=DEFAULT_TEST_SIZE,
                     help="Holdout days for backtest/ranking (default: 30)")
    fc.add_argument("--save", type=str, default=None, help="Optional path to save the forecast as CSV")

    return parser


def cmd_forecast(args: argparse.Namespace) -> None:
    try:
        df, ticker = load_data(args)
    except ImportError as exc:
        print(_c(f"\n✗ {exc}", "red"))
        print(_c("  Tip: try `python cli.py forecast --demo` to run offline "
                  "with synthetic data instead.", "yellow"))
        sys.exit(1)
    except (ValueError, FileNotFoundError) as exc:
        print(_c(f"\n✗ Could not load data: {exc}", "red"))
        sys.exit(1)

    try:
        print("→ Computing technical indicators & candlestick patterns...")
        df = add_technical_indicators(df)
        df = detect_candlestick_patterns(df)
        df = df.dropna(subset=["SMA_50"])  # ensure indicator warm-up is complete

        if len(df) < args.test_size + 60:
            print(_c(
                f"\n✗ Not enough data after indicator warm-up ({len(df)} rows) for a "
                f"test-size of {args.test_size}. Use a longer --period or a smaller --test-size.",
                "red",
            ))
            sys.exit(1)

        print("→ Backtesting Tree Ensemble, LSTM, and Baseline models...")
        result = run_forecast_pipeline(
            df, ticker=ticker, horizon=args.horizon, test_size=args.test_size
        )
    except Exception as exc:  # noqa: BLE001
        print(_c(f"\n✗ Forecast pipeline failed: {exc}", "red"))
        sys.exit(1)

    print_header(result.ticker, result.as_of_date, result.last_close)
    print_leaderboard(result.leaderboard)
    print_forecast(result.forecast_df, result.best_model_name)
    print_mood_and_signal(result.market_mood, result.signal, result.rationale)

    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        result.forecast_df.to_csv(args.save, index=False)
        print(f"\n→ Forecast saved to {args.save}")

    print()


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.command == "forecast":
        cmd_forecast(args)


if __name__ == "__main__":
    main()
