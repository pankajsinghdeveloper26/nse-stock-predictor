/**
 * Shared domain types for the AlphaVision Quant dashboard.
 * These mirror the Pydantic models exposed by the FastAPI backend.
 */

export type SignalType = "BUY" | "SELL" | "HOLD"

export type TrendDirection = "up" | "down" | "flat"

/** A single row in the live market screener table. */
export interface StockItem {
  ticker: string
  name: string
  sector: string
  /** Last traded price in INR. */
  ltp: number
  /** Percentage change vs previous close. */
  changePct: number
  /** Raw traded volume (shares). */
  volume: number
  /** 14-period Relative Strength Index. */
  rsi: number
  signal: SignalType
}

/** Headline metrics rendered in the top metric cards. */
export interface ScreenerMetrics {
  nseUniverse: number
  universeDelta: number
  buySignals: number
  buyDelta: number
  sellSignals: number
  sellDelta: number
  avgRsi: number
  avgRsiDelta: number
  /** ISO timestamp or pre-formatted clock string of the last parquet sync. */
  lastSync: string
}

/** An index tile (NIFTY 50, BANK NIFTY, ...) with sparkline series. */
export interface IndexCard {
  id: string
  label: string
  value: number
  changePct: number
  /** Normalised sparkline series, oldest → newest. */
  sparkline: number[]
}

/** A single ML model prediction in the right-hand live feed. */
export interface SignalFeedItem {
  id: string
  ticker: string
  signal: SignalType
  /** Model confidence as a percentage, e.g. 91.4 */
  confidence: number
  model: string
  /** HH:MM timestamp of the prediction. */
  time: string
}

/** Engine/runtime health surfaced in the sidebar footer. */
export interface SystemHealthInfo {
  engine: string
  active: boolean
  cacheHitPct: number
  latencyMs: number
}

/** Response payload of GET /api/v1/screener */
export interface ScreenerResponse {
  metrics: ScreenerMetrics
  stocks: StockItem[]
  indexes: IndexCard[]
}

export interface NavItem {
  id: string
  label: string
  /** Lucide icon name used by the sidebar. */
  icon:
    | "scan-search"
    | "bar-chart-3"
    | "cpu"
    | "database"
    | "flask-conical"
    | "terminal"
  badge?: boolean
}

export type AsyncState = "idle" | "loading" | "error"
