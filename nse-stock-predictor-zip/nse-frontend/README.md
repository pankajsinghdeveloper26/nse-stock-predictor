# NSE Pulse — Phase 4: Astro Frontend & Launch Automation

A dashboard UI for the NSE Stock Prediction project: interactive candlestick
chart with a 5-day forecast overlay, live ticker tape, market-mood badge,
Buy/Hold/Sell signal, and a model leaderboard — all wired to the Phase 3
FastAPI backend (`server.py` + `services.py`).

> Educational demo. Nothing here is financial advice.

---

## 1. Project layout

This deliverable is the **frontend** only. Drop it next to your existing
backend so the launch scripts can find both:

```
project-root/
├── backend/                 ← your existing Phase 3 code
│   ├── server.py
│   ├── services.py
│   ├── data_loader.py
│   ├── models.py
│   └── requirements.txt     ← must exist (fastapi, uvicorn, yfinance, etc.)
├── frontend/                ← this folder
│   ├── src/
│   ├── package.json
│   ├── astro.config.mjs
│   └── ...
├── start.sh                 ← Linux/Mac launcher
└── start.bat                ← Windows launcher
```

If your folders are named differently, edit the `BACKEND_DIR` /
`FRONTEND_DIR` variables at the top of `start.sh` / `start.bat` — everything
else works unchanged. (`start.sh` / `start.bat` currently live inside the
`frontend/` folder in this download — move them up to `project-root/`
alongside `backend/` to match the layout above, or just adjust the paths.)

---

## 2. Prerequisites

- **Node.js 18+** and npm (for the Astro frontend)
- **Python 3.10+** (for the FastAPI backend)
- A `requirements.txt` in `backend/` covering `fastapi`, `uvicorn`,
  `yfinance`, `pandas`, `numpy`, `scikit-learn`, and whatever `models.py` /
  `data_loader.py` need — this was part of Phases 1–3 and isn't included here.

---

## 3. Quick start (recommended)

From `project-root/`:

**Linux / Mac**
```bash
chmod +x start.sh
./start.sh
```

**Windows**
```bat
start.bat
```

Each script will, on first run:
1. Create a Python virtual environment in `backend/.venv` and install
   `requirements.txt`.
2. Launch FastAPI at **http://localhost:8000** (docs at `/docs`).
3. Run `npm install` in `frontend/`.
4. Launch the Astro dev server at **http://localhost:4321**.

Open **http://localhost:4321** — the dashboard loads RELIANCE.NS by default.

Stop everything with `Ctrl+C` (Linux/Mac) or by closing the two spawned
terminal windows (Windows).

---

## 4. Manual setup

If you'd rather run each piece yourself:

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn server:app --reload --host 0.0.0.0 --port 8000

# Frontend (in a second terminal)
cd frontend
npm install
npm run dev
```

---

## 5. How the frontend talks to the backend

In dev, the Astro Vite server proxies any request to `/api/*` straight to
`http://localhost:8000` (see `astro.config.mjs`), so the browser only ever
calls same-origin URLs and never has to worry about CORS.

If you deploy the built frontend (`npm run build`) somewhere separate from
the API — e.g. a static host — set `PUBLIC_API_BASE_URL` before building so
requests go straight to your API's real origin:

```bash
# frontend/.env  (copy from .env.example)
PUBLIC_API_BASE_URL=https://your-api.example.com
```

`server.py`'s CORS middleware already defaults to allowing all origins
(`CORS_ORIGINS` env var), so this works out of the box; tighten
`CORS_ORIGINS` for a real production deployment.

---

## 6. What's in the UI

| Area | Source endpoint(s) |
|---|---|
| Candlestick chart + technical stats (RSI, MACD, SMA, ATR) | `GET /api/stock/{ticker}` |
| 5-day forecast overlay (dashed line), model leaderboard, Buy/Hold/Sell signal | `GET /api/forecast/{ticker}` |
| Live ticker marquee, market-mood badge, market pulse bar | `GET /api/market-mood` |
| Header search bar + presets | RELIANCE.NS, TCS.NS, INFY.NS, HDFCBANK.NS |
| Dark/light toggle | Persisted to `localStorage`, defaults to dark (terminal theme) |
| About modal (footer) | Static — developer credits below |

Design direction: a dark, data-dense "trading terminal" aesthetic (IBM Plex
Mono for data, Inter for UI copy) with a signature dashed-line forecast that
extends directly out of the last real candle, colored by the model's
Buy/Hold/Sell signal.

---

## 7. Build for production

```bash
cd frontend
npm run build      # outputs to frontend/dist/
npm run preview    # sanity-check the production build locally
```

Serve `dist/` with any static host (Nginx, Vercel, Netlify, etc.), pointed
at your deployed FastAPI backend via `PUBLIC_API_BASE_URL`.

---

## 8. Troubleshooting

- **"Couldn't reach the backend"** in the chart panel → confirm
  `uvicorn` is running on port 8000 and `http://localhost:8000/api/health`
  returns `{"status": "ok"}`.
- **Ticker not found** → the backend normalizes bare symbols to `.NS`
  automatically (`reliance` → `RELIANCE.NS`); this error means Yahoo
  Finance itself doesn't recognize the symbol.
- **Forecast panel stays empty but the chart loads** → that ticker likely
  has fewer than ~120 rows of history for the requested `period`; try a
  longer period (`2y`, `5y`) — this mirrors `InsufficientDataError` from
  `services.py`.
- **Port already in use** → set `BACKEND_PORT` / `FRONTEND_PORT` env vars
  before running `start.sh`, or edit the `set` lines in `start.bat`.

---

## Credits

**Developer:** Pankaj Singh
**Mail:** pankajsinghdeveloper26@gmail.com
**LinkedIn:** [pankaj-singh-053a2a364](https://www.linkedin.com/in/pankaj-singh-053a2a364)
