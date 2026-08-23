import { useCallback, useEffect, useState } from "react"
import { AlertTriangle, Loader2 } from "lucide-react"
import { MetricCard } from "./MetricCard"
import { IndexTile } from "./IndexTile"
import { ScreenerTable } from "./ScreenerTable"
import { SignalFeed } from "./SignalFeed"
import { getHealth, getMarketMood, getStock, ApiError } from "@/lib/api"
import { SCREENER_BASKET } from "@/lib/basket"
import { formatDelta } from "@/lib/utils"
import { indexCards as demoIndexCards } from "@/lib/mock-data"
import type {
  ScreenerMetrics,
  SignalFeedItem,
  SignalType,
  StockItem,
} from "@/lib/types"

interface DashboardProps {
  /** Server-rendered fallback so the page isn't empty before hydration. */
  initialMetrics: ScreenerMetrics
  initialStocks: StockItem[]
  initialSignalFeed: SignalFeedItem[]
}

/**
 * Client-hydrated dashboard body. Talks to the real FastAPI backend
 * (server.py -> services.py) instead of the static mock-data.ts fixtures:
 *
 *   - GET /api/market-mood  -> per-ticker mood/signal for the basket, plus
 *                              basket-wide buy/sell/hold counts.
 *   - GET /api/stock/{tkr}  -> latest LTP / % change / volume / RSI per
 *                              ticker (market-mood doesn't include these).
 *   - GET /api/health       -> backend liveness, surfaced in the header.
 *
 * The index tiles (NIFTY 50 / BANK NIFTY / ...) stay on demo data: the
 * backend only serves individual NSE equities, not index quotes, so
 * there's nothing real to wire them to yet.
 */
export function Dashboard({
  initialMetrics,
  initialStocks,
  initialSignalFeed,
}: DashboardProps) {
  const [metrics, setMetrics] = useState<ScreenerMetrics>(initialMetrics)
  const [stocks, setStocks] = useState<StockItem[]>(initialStocks)
  const [signalFeed, setSignalFeed] = useState<SignalFeedItem[]>(initialSignalFeed)
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "ready">("idle")
  const [error, setError] = useState<string | null>(null)
  const [backendUp, setBackendUp] = useState<boolean | null>(null)

  const load = useCallback(async () => {
    setStatus("loading")
    setError(null)

    try {
      await getHealth()
      setBackendUp(true)
    } catch {
      setBackendUp(false)
    }

    try {
      const tickers = SCREENER_BASKET.map((t) => t.ticker)

      const [mood, stockResults] = await Promise.all([
        getMarketMood({ tickers }),
        Promise.allSettled(tickers.map((t) => getStock(t, { period: "3mo" }))),
      ])

      const moodByTicker = new Map(mood.tickers.map((row) => [row.ticker.replace(/\.NS$/, ""), row]))

      const nextStocks: StockItem[] = []
      let rsiSum = 0
      let rsiCount = 0

      SCREENER_BASKET.forEach((meta, i) => {
        const result = stockResults[i]
        const moodRow = moodByTicker.get(meta.ticker)
        if (result.status !== "fulfilled") return

        const latest = result.value.latest

        // % change vs previous session: pull the prior row's Close from
        // the history the backend already returned.
        const history = result.value.history
        const prevRow = history.length >= 2 ? history[history.length - 2] : null
        const prevCloseVal = (prevRow?.Close as number | null | undefined) ?? null
        const changePct =
          latest.close != null && prevCloseVal
            ? ((latest.close - prevCloseVal) / prevCloseVal) * 100
            : 0

        if (latest.rsi_14 != null) {
          rsiSum += latest.rsi_14
          rsiCount += 1
        }

        nextStocks.push({
          ticker: meta.ticker,
          name: meta.name,
          sector: meta.sector,
          ltp: latest.close ?? 0,
          changePct,
          volume: latest.volume ?? 0,
          rsi: latest.rsi_14 ?? 0,
          signal: (moodRow?.signal as SignalType) ?? "HOLD",
        })
      })

      if (nextStocks.length > 0) {
        setStocks(nextStocks)
      }

      const buy = mood.signal_breakdown.BUY ?? 0
      const hold = mood.signal_breakdown.HOLD ?? 0
      const sell = mood.signal_breakdown.SELL ?? 0

      setMetrics((prev) => ({
        ...prev,
        nseUniverse: mood.basket_size,
        buySignals: buy,
        sellSignals: sell,
        avgRsi: rsiCount > 0 ? rsiSum / rsiCount : prev.avgRsi,
        lastSync: new Date(mood.as_of.replace(" UTC", "Z").replace(" ", "T")).toLocaleTimeString(
          "en-IN",
          { hour: "2-digit", minute: "2-digit" },
        ),
      }))

      const feed: SignalFeedItem[] = mood.tickers
        .slice()
        .sort((a, b) => Math.abs(b.forecast_pct_change ?? 0) - Math.abs(a.forecast_pct_change ?? 0))
        .slice(0, 6)
        .map((row, i) => ({
          id: `${row.ticker}-${i}`,
          ticker: row.ticker.replace(/\.NS$/, ""),
          signal: row.signal as SignalType,
          // Proxy for model conviction, derived from the size of the
          // predicted move — the backend doesn't return a calibrated
          // probability, so treat this as directional strength, not a
          // true confidence percentage.
          confidence: Math.min(99, 50 + Math.abs(row.forecast_pct_change ?? 0) * 8),
          model: row.best_model,
          time: new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }),
        }))

      if (feed.length > 0) setSignalFeed(feed)

      if (mood.failures.length > 0 && nextStocks.length === 0) {
        setError(
          `Backend reached, but every ticker in the basket failed (e.g. ${mood.failures[0].ticker}: ${mood.failures[0].error}). Showing last known data.`,
        )
      }

      setStatus("ready")
    } catch (err) {
      const message =
        err instanceof ApiError
          ? `${err.code}: ${err.detail}`
          : err instanceof Error
            ? err.message
            : "Unknown error"
      setError(
        `Couldn't reach the backend at /api (${message}). Is the FastAPI server running? See README: uvicorn server:app --reload.`,
      )
      setStatus("error")
    }
  }, [])

  useEffect(() => {
    load()

    function onRefresh() {
      load()
    }
    window.addEventListener("screener:refresh", onRefresh)

    // Light polling so the screen stays reasonably live without hammering
    // yfinance on every render.
    const interval = window.setInterval(load, 5 * 60 * 1000)

    return () => {
      window.removeEventListener("screener:refresh", onRefresh)
      window.clearInterval(interval)
    }
  }, [load])

  const m = metrics
  const metricCards = [
    {
      label: "Screener Basket",
      value: m.nseUniverse.toLocaleString("en-IN"),
      delta: formatDelta(m.universeDelta),
      deltaLabel: "tickers tracked",
      deltaTone: "bullish" as const,
      icon: "database" as const,
    },
    {
      label: "Buy Signals",
      value: m.buySignals.toLocaleString("en-IN"),
      delta: formatDelta(m.buyDelta),
      deltaLabel: "vs prev session",
      deltaTone: "bullish" as const,
      icon: "trending-up" as const,
    },
    {
      label: "Sell Signals",
      value: m.sellSignals.toLocaleString("en-IN"),
      delta: formatDelta(m.sellDelta),
      deltaLabel: "vs prev session",
      deltaTone: "bearish" as const,
      icon: "trending-down" as const,
    },
    {
      label: "Avg RSI",
      value: m.avgRsi.toFixed(1),
      delta: formatDelta(m.avgRsiDelta),
      deltaLabel: "across basket",
      deltaTone: "bullish" as const,
      icon: "activity" as const,
    },
  ]

  return (
    <>
      {backendUp === false && (
        <div className="mt-6 flex items-start gap-3 rounded-2xl border border-bearish/30 bg-bearish-muted px-4 py-3 text-sm text-bearish">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-semibold">Backend unreachable</p>
            <p className="mt-0.5 text-bearish/90">
              Couldn't reach the FastAPI backend at <code>/api/health</code>. Start it with{" "}
              <code>uvicorn server:app --reload --port 8000</code> from the project root, then
              refresh. Showing the last data available.
            </p>
          </div>
        </div>
      )}

      {status === "loading" && stocks === initialStocks && (
        <div className="mt-6 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          Fetching live data from the backend…
        </div>
      )}

      {error && (
        <div className="mt-6 rounded-2xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
          {error}
        </div>
      )}

      <section className="mt-8" aria-label="Screener metrics">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {metricCards.map((metric) => (
            <MetricCard key={metric.label} {...metric} />
          ))}
        </div>
      </section>

      <section className="mt-4" aria-label="Index performance (demo data)">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {demoIndexCards.map((index) => (
            <IndexTile key={index.id} index={index} />
          ))}
        </div>
      </section>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <ScreenerTable stocks={stocks} universeSize={m.nseUniverse} />
        <SignalFeed items={signalFeed} />
      </div>
    </>
  )
}
