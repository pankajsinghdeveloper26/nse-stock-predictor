# Backend upgrade: persistent storage, caching, features, auth

## Adaptation note

Your project's Python backend is currently **flat** (`data_loader.py`,
`services.py`, `server.py`, `models.py` all live at the repo root — there's
no `backend/` package). Restructuring into `backend/data/...`,
`backend/services/...` as literally requested would touch every import
across the whole backend, which conflicts with "keep existing code
working" / "make changes incrementally". So the new modules below follow
your existing flat convention instead. Nothing existing moved.

## New files (all at repo root, next to server.py)

| File | Role |
|---|---|
| `config.py` | Central env-var settings: cache TTLs, storage paths, auth keys, rate limits. Everything defaults to "off"/back-compat — the app behaves exactly as before with zero `.env` changes. |
| `cleaner.py` | Validates/cleans raw OHLCV: dedupes dates, fixes High<Low glitches, limited forward-fill, drops unfillable gaps. |
| `storage.py` | Parquet persistence (`data/parquet/<TICKER>_<interval>.parquet`) + DuckDB SQL over all of them at once (`query_history_sql`). |
| `cache.py` | `diskcache`-backed key/value cache, with an automatic pure-pickle fallback if `diskcache` isn't installed. |
| `loader.py` | The new orchestrator: `get_historical()` (cache → Parquet → yfinance, incremental) and `get_live_quote()` (short-TTL cache → yfinance only, never persisted). |
| `features.py` | pandas-ta-backed RSI, MACD, Bollinger Bands, Supertrend, EMA(9/21/50), ATR, VWAP — additive, doesn't touch `data_loader.py`'s existing indicator columns. Falls back to pure-pandas math if `pandas-ta` isn't installed. |
| `auth.py` | API-key check + in-memory sliding-window rate limiter. |

## Changed files

- **`services.py`**: `get_stock_dataframe()` now calls `loader.get_historical()` instead of `data_loader.fetch_stock_data()` directly, and additively runs `features.add_features()` after the existing indicator/pattern steps. The old in-memory `_stock_cache` dict is gone (superseded by `loader.py`'s cache+Parquet); the forecast-result cache is unchanged. `get_stock_payload()`'s `latest` dict gained `ema_9/21/50`, `supertrend`, `supertrend_direction`, `vwap`.
- **`server.py`**: added an `auth_and_rate_limit` middleware (checks `X-API-Key` + a per-client rate limit on every `/api/*` route except `/api/health`, `/`, `/docs`, `/redoc`, `/openapi.json`), and a new `GET /api/live/{ticker}` endpoint for live-only quotes.
- **`requirements.txt`**: added `pyarrow`, `duckdb`, `diskcache`, `pandas-ta`, `python-dotenv`.
- **`.env.example`**: documented every new setting (all commented out / off by default).
- **`.gitignore`**: excludes `data/parquet/`, `data/cache/`, `data/*.duckdb` (generated at runtime, not source-controlled).

## New data flow

```
GET /api/stock/{ticker}
        │
        ▼
  auth_and_rate_limit middleware  (server.py)
        │  401 if API_KEYS is set and key missing/invalid
        │  429 if over the per-client rate limit
        ▼
  services.get_stock_dataframe(ticker, period, interval)
        │
        ▼
  loader.get_historical(ticker, period, interval)
        │
        ├─ 1. cache.cache_get("hist:...")          -- fast path, short TTL
        │        └─ HIT → return immediately
        │
        ├─ 2. storage.load_parquet(ticker)          -- Parquet store
        │        └─ fresh (≤ MAX_STALE_DAYS old) → cache it, return
        │
        └─ 3. data_loader.fetch_stock_data(...)     -- yfinance
                 - full history on cold start, else just the last ~1mo
                   tail (incremental)
                 - cleaner.clean_ohlcv(...)
                 - storage.upsert_parquet(...)        -- merge + persist
                 - cache.cache_set(...)
                 - any failure here + stale Parquet exists → serve the
                   stale data anyway rather than a hard error
        │
        ▼
  data_loader.add_technical_indicators()  +  detect_candlestick_patterns()
        │  (unchanged — SMA/RSI/MACD/BB/ATR, candlestick flags)
        ▼
  features.add_features(prefer_pandas_ta=False)
        │  (additive — EMA(9/21/50), Supertrend, VWAP via pandas-ta)
        ▼
  JSON response
```

```
GET /api/live/{ticker}
        │
        ▼
  loader.get_live_quote(ticker)
        │
        ├─ cache.cache_get("live:...")   -- 60s TTL, never Parquet-persisted
        │        └─ HIT → return immediately
        │
        └─ yfinance fast_info            -- price / previous_close / change_pct
                 - failure (market closed, provider down) → clean 503
                   "data_unavailable" JSON, not a stack trace
```

## Auth & rate limiting — how to turn them on

Both are **off by default** so nothing breaks for you today.

```bash
# .env
API_KEYS=your-secret-key-here,another-key-for-a-teammate
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
```

Once `API_KEYS` is set, every `/api/*` route (except `/api/health`) requires:
```
X-API-Key: your-secret-key-here
```
Missing/invalid key → `401`. Over the rate limit → `429` with a `Retry-After` header.

## Verified in this sandbox

This sandbox has no route to Yahoo Finance's hosts (`query1/query2.finance.yahoo.com`
are blocked at the network layer here), so a real end-to-end live fetch
couldn't be tested from inside this environment. Everything else was
tested directly and confirmed working:

- `cleaner.clean_ohlcv` — cleaned synthetic OHLCV, zero NaN leakage, fixed injected High<Low glitches.
- `storage.py` — Parquet write/read round-trip, `upsert_parquet` correctly deduped/merged a new row, `query_history_sql` (DuckDB) grouped/aggregated correctly.
- `cache.py` — set/get round-trip, correct miss on unknown key.
- `features.add_features` — added `EMA_9/21/50`, `Supertrend`, `Supertrend_Direction`, `VWAP` without disturbing existing indicator columns; fallback path (no pandas-ta) also verified.
- **Auth**: no key → `401`; wrong key → `401`; correct key → passes through to the real logic; `/api/health` exempt (`200` with no key).
- **Rate limiting**: with a limit of 3 req/60s, the 3rd+ request in a burst correctly returned `429 Too Many Requests` with a `Retry-After` header.
- **Graceful fallback**: with yfinance network-blocked, `/api/stock/{ticker}` returned a clean `404 ticker_not_found` and `/api/live/{ticker}` returned a clean `503 data_unavailable` — both proper JSON, never a raw exception.
- Frontend (`npm run build`) still builds cleanly on top of these backend changes — nothing in the frontend needed to change for this upgrade.

Run this for yourself once you have real internet access to Yahoo Finance,
to confirm the live end-to-end fetch → Parquet write → cache path:
```bash
uvicorn server:app --reload --port 8000
curl http://localhost:8000/api/stock/RELIANCE
ls data/parquet/            # should now contain RELIANCE_NS_1d.parquet
curl http://localhost:8000/api/stock/RELIANCE   # second call should be much faster (cache hit)
```
