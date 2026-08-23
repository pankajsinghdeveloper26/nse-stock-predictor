# Fix notes — frontend/backend connection

## What was broken

1. **The root Astro app (`/src`) had zero connection to the FastAPI backend.**
   It was a later "v0"-generated redesign merged on top of the original project,
   and it rendered everything from static `src/lib/mock-data.ts` — no `fetch()`
   calls at all. `nse-frontend/` (the original app) *was* correctly wired, so
   the repo effectively shipped two frontends: one pretty and fake, one plain
   and real.

2. **`npm install` failed outright** in the root project: `package.json` pinned
   `react@^19` / `@types/react@^19`, but `@astrojs/react@^3.6.3` only supports
   React 17/18 types, so npm's dependency resolver errored with `ERESOLVE`.

## What was fixed

- `package.json`: pinned `react`/`react-dom`/`@types/react*` to `^18.3.x` to
  match what the installed `@astrojs/react` actually supports.
- `astro.config.mjs`: added the same dev-server `/api` → `http://localhost:8000`
  proxy pattern `nse-frontend` already used, so the browser can call `/api/...`
  with no CORS setup needed.
- Added `src/lib/api.ts` (ported from `nse-frontend/src/lib/api.ts`) — a typed
  fetch client for `GET /api/health`, `/api/stock/{ticker}`,
  `/api/forecast/{ticker}`, `/api/market-mood`.
- Added `src/lib/basket.ts` — the 10-ticker basket the dashboard screens,
  mirroring the backend's own `MARKET_MOOD_PRESETS` in `services.py`.
- Added `src/components/react/Dashboard.tsx` — replaces the static
  MetricCard/ScreenerTable/SignalFeed wiring in `index.astro` with live data:
  fetches `/api/market-mood` + per-ticker `/api/stock/{ticker}` on load, on a
  5-minute interval, and on "Refresh" click; shows a clear banner if the
  backend is unreachable; falls back to the mock data only as a
  pre-hydration placeholder.
- `ScreenerActions.tsx`: "Refresh" now dispatches a real
  `window` event the dashboard listens for, instead of a fake 1.2s spinner.
- `.env.example` + `src/env.d.ts`: added `PUBLIC_API_BASE_URL` typing, same
  pattern as `nse-frontend`.

## Known limitation

The NIFTY 50 / BANK NIFTY / NIFTY IT / NIFTY FMCG index tiles still use demo
data — the FastAPI backend only serves individual NSE equities
(`resolve_ticker()` in `services.py` appends `.NS`), not index quotes, so
there's nothing real to wire them to without adding a new backend endpoint.

## How to run it

Terminal 1 — backend:
```bash
python -m venv venv
source venv/bin/activate      # venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

Terminal 2 — root dashboard (the fixed one):
```bash
npm install
npm run dev
```
Open http://localhost:3000 — it proxies `/api/*` to the backend automatically.

The original `nse-frontend/` app (chart + ticker marquee UI) still works the
same way, on its own port:
```bash
cd nse-frontend
npm install
npm run dev
```
