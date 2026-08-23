"""
storage.py
================
Persistent OHLCV storage: one Parquet file per ticker under
`data/parquet/`, queryable analytically through DuckDB (which reads
Parquet natively - no separate load/import step, no running database
server, still 100% free/local).

This is the layer that lets historical data survive process restarts
and avoids re-downloading a ticker's whole history on every request -
only the missing tail (since the last stored row) needs to be fetched.

Layout
------
    data/parquet/<TICKER>_<interval>.parquet   e.g. RELIANCE_NS_1d.parquet
    data/nse.duckdb                            (DuckDB catalog file, optional -
                                                 Parquet files are the source of
                                                 truth; DuckDB is used in-process
                                                 for ad-hoc SQL over them.)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

import config

logger = logging.getLogger("storage")

try:
    import duckdb

    _DUCKDB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _DUCKDB_AVAILABLE = False
    logger.warning(
        "storage.py: `duckdb` not installed - analytical SQL queries "
        "(query_history_sql) will be unavailable, but Parquet read/write "
        "still works via pandas/pyarrow."
    )


def _safe_name(ticker: str, interval: str) -> str:
    return f"{ticker.replace('.', '_').upper()}_{interval}"


def parquet_path(ticker: str, interval: str = "1d") -> Path:
    return config.PARQUET_DIR / f"{_safe_name(ticker, interval)}.parquet"


# --------------------------------------------------------------------------- #
# Read / write
# --------------------------------------------------------------------------- #
def load_parquet(ticker: str, interval: str = "1d") -> Optional[pd.DataFrame]:
    """Return the stored OHLCV history for `ticker`, or None if not stored yet."""
    path = parquet_path(ticker, interval)
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        df.index.name = "Date"
        return df.sort_index()
    except Exception:  # noqa: BLE001 - corrupt/partial file, treat as absent
        logger.exception("storage.load_parquet: failed reading %s, ignoring stale file", path)
        return None


def save_parquet(ticker: str, df: pd.DataFrame, interval: str = "1d") -> Path:
    """Overwrite the stored history for `ticker` with `df`."""
    path = parquet_path(ticker, interval)
    out = df.sort_index()
    out.to_parquet(path, engine="pyarrow")
    logger.info("storage.save_parquet: wrote %d rows -> %s", len(out), path)
    return path


def upsert_parquet(ticker: str, new_df: pd.DataFrame, interval: str = "1d") -> pd.DataFrame:
    """
    Merge `new_df` into whatever is already stored for `ticker` (deduping
    by date, new rows win) and persist the result. Returns the full,
    merged DataFrame.
    """
    from cleaner import merge_ohlcv  # local import: avoids a cache<->cleaner<->storage cycle

    existing = load_parquet(ticker, interval)
    merged = merge_ohlcv(existing, new_df)
    save_parquet(ticker, merged, interval)
    return merged


def last_stored_date(ticker: str, interval: str = "1d") -> Optional[pd.Timestamp]:
    """Latest date present in the Parquet store for `ticker`, or None."""
    df = load_parquet(ticker, interval)
    if df is None or df.empty:
        return None
    return df.index[-1]


def is_fresh(ticker: str, interval: str = "1d", max_stale_days: Optional[int] = None) -> bool:
    """
    Whether the stored history for `ticker` is recent enough to serve
    without hitting the external provider again (accounts for weekends/
    market holidays via `max_stale_days`, not just "is it exactly today").
    """
    max_stale_days = max_stale_days if max_stale_days is not None else config.MAX_STALE_DAYS
    last = last_stored_date(ticker, interval)
    if last is None:
        return False
    age = datetime.now() - last.to_pydatetime().replace(tzinfo=None)
    return age <= timedelta(days=max_stale_days)


# --------------------------------------------------------------------------- #
# DuckDB analytical queries
# --------------------------------------------------------------------------- #
def query_history_sql(sql: str) -> pd.DataFrame:
    """
    Run an arbitrary DuckDB SQL query over every stored ticker's Parquet
    file at once, exposed as a single virtual table `history`, e.g.:

        query_history_sql('''
            SELECT ticker, AVG(Close) AS avg_close
            FROM history
            WHERE Date >= '2025-01-01'
            GROUP BY ticker
            ORDER BY avg_close DESC
        ''')

    Each row's `ticker` column is derived from its source filename.
    Raises RuntimeError if `duckdb` isn't installed.
    """
    if not _DUCKDB_AVAILABLE:
        raise RuntimeError(
            "duckdb is not installed. Run `pip install duckdb` to enable "
            "SQL queries over the Parquet store."
        )

    glob_path = str(config.PARQUET_DIR / "*.parquet")
    con = duckdb.connect(database=":memory:")
    try:
        con.execute(
            f"""
            CREATE VIEW history AS
            SELECT
                regexp_replace(parse_filename(filename, true), '_[0-9a-z]+$', '') AS ticker,
                *
            FROM read_parquet('{glob_path}', filename = true, union_by_name = true)
            """
        )
        return con.execute(sql).fetchdf()
    finally:
        con.close()


def list_stored_tickers(interval: str = "1d") -> list[str]:
    """All tickers currently persisted for `interval`, derived from filenames."""
    suffix = f"_{interval}.parquet"
    return sorted(
        p.name[: -len(suffix)].replace("_", ".", 1) if p.name.endswith(suffix) else p.stem
        for p in config.PARQUET_DIR.glob(f"*{suffix}")
    )
