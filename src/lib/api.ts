// src/lib/api.ts
// ---------------------------------------------------------------------------
// Thin client for the FastAPI backend (server.py / services.py).
//
// In dev, requests to "/api/*" are proxied to PUBLIC_API_BASE_URL (or
// http://localhost:8000) by the Vite dev-server proxy configured in
// astro.config.mjs, so the browser never needs to deal with CORS.
//
// If PUBLIC_API_BASE_URL is set at build time (e.g. for a static build
// deployed separately from the API), requests go straight to that origin
// instead — the FastAPI app's CORS middleware already allows "*" by default.
// ---------------------------------------------------------------------------

const BASE = (import.meta.env.PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  code: string;
  detail: string;
  constructor(status: number, code: string, detail: string) {
    super(detail || code);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function request<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`${BASE}${path}`, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
    }
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000); // 30s timeout

  try {
    const res = await fetch(url.toString(), {
      headers: { Accept: "application/json" },
      signal: controller.signal
    });
    clearTimeout(timeoutId);

    if (!res.ok) {
      let code = "unknown_error";
      let detail = `Request failed with status ${res.status}`;
      try {
        const body = await res.json();
        code = body.error ?? code;
        detail = body.detail ?? detail;
      } catch {
        /* response wasn't JSON — keep defaults */
      }
      throw new ApiError(res.status, code, detail);
    }

    return res.json() as Promise<T>;
  } catch (err) {
    clearTimeout(timeoutId);
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Types (trimmed to the fields the UI actually reads — backend may send more)
// ---------------------------------------------------------------------------

export interface StockLatest {
  close: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  sma_20: number | null;
  sma_50: number | null;
  rsi_14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  bb_percent_b: number | null;
  atr_14: number | null;
  patterns: Record<string, boolean>;
}

export interface StockHistoryRow {
  Date: string;
  Open?: number | null;
  High?: number | null;
  Low?: number | null;
  Close?: number | null;
  Volume?: number | null;
  [key: string]: unknown;
}

export interface StockPayload {
  ticker: string;
  period: string;
  interval: string;
  rows: number;
  as_of_date: string;
  latest: StockLatest;
  history: StockHistoryRow[];
}

export type LeaderboardRow = Record<string, string | number | boolean | null>;

export interface ForecastRow {
  Date: string;
  Predicted_Close?: number | null;
  [key: string]: unknown;
}

export type MarketMood = "Bullish" | "Bearish" | "Sideways";
export type Signal = "BUY" | "HOLD" | "SELL";

export interface ForecastPayload {
  ticker: string;
  as_of_date: string;
  last_close: number | null;
  horizon_days: number;
  test_size_days: number;
  leaderboard: LeaderboardRow[];
  best_model: string;
  forecast: ForecastRow[];
  market_mood: MarketMood;
  signal: Signal;
  rationale: string[];
  disclaimer: string;
}

export interface MarketMoodTickerRow {
  ticker: string;
  last_close: number | null;
  mood: MarketMood;
  signal: Signal;
  forecast_pct_change: number | null;
  best_model: string;
}

export interface MarketMoodPayload {
  as_of: string;
  basket_size: number;
  overall_mood: MarketMood;
  mood_breakdown: Record<MarketMood, number>;
  signal_breakdown: Record<Signal, number>;
  bullish_pct: number;
  bearish_pct: number;
  sideways_pct: number;
  tickers: MarketMoodTickerRow[];
  failures: { ticker: string; error: string }[];
  disclaimer: string;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export interface HealthPayload {
  status: string;
  service: string;
}

export function getHealth() {
  return request<HealthPayload>(`/api/health`);
}

export function getStock(ticker: string, opts: { period?: string; interval?: string } = {}) {
  return request<StockPayload>(`/api/stock/${encodeURIComponent(ticker)}`, {
    period: opts.period ?? "1y",
    interval: opts.interval ?? "1d",
  });
}

export function getForecast(
  ticker: string,
  opts: { period?: string; interval?: string; horizon?: number; test_size?: number } = {}
) {
  return request<ForecastPayload>(`/api/forecast/${encodeURIComponent(ticker)}`, {
    period: opts.period ?? "2y",
    interval: opts.interval ?? "1d",
    horizon: opts.horizon ?? 5,
    test_size: opts.test_size ?? 30,
  });
}

export function getMarketMood(
  opts: { tickers?: string[]; period?: string; interval?: string; horizon?: number; test_size?: number } = {}
) {
  return request<MarketMoodPayload>(`/api/market-mood`, {
    tickers: opts.tickers?.join(","),
    period: opts.period ?? "1y",
    interval: opts.interval ?? "1d",
    horizon: opts.horizon ?? 5,
    test_size: opts.test_size ?? 20,
  });
}
