import { useMemo, useState } from "react"
import { ArrowUpDown, Download, ScanSearch, SlidersHorizontal } from "lucide-react"
import { SignalBadge } from "./SignalBadge"
import { cn, formatInr, formatPct, formatVolume } from "@/lib/utils"
import type { SignalType, StockItem } from "@/lib/types"

type SortKey = "ticker" | "ltp" | "changePct" | "volume" | "rsi"
type SortDir = "asc" | "desc"

const signalFilters: Array<SignalType | "ALL"> = ["ALL", "BUY", "HOLD", "SELL"]

interface ScreenerTableProps {
  stocks: StockItem[]
  universeSize: number
}

export function ScreenerTable({ stocks, universeSize }: ScreenerTableProps) {
  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>("desc")
  const [filter, setFilter] = useState<SignalType | "ALL">("ALL")
  const [showFilters, setShowFilters] = useState(false)

  const rows = useMemo(() => {
    const filtered =
      filter === "ALL" ? stocks : stocks.filter((s) => s.signal === filter)

    if (!sortKey) return filtered

    return [...filtered].sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      const cmp =
        typeof av === "string" && typeof bv === "string"
          ? av.localeCompare(bv)
          : Number(av) - Number(bv)
      return sortDir === "asc" ? cmp : -cmp
    })
  }, [stocks, sortKey, sortDir, filter])

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortKey(key)
      setSortDir("desc")
    }
  }

  function exportCsv() {
    const header = ["Ticker", "Name", "Sector", "LTP", "Change %", "Volume", "RSI", "Signal"]
    const body = rows.map((r) => [
      r.ticker,
      r.name,
      r.sector,
      r.ltp,
      r.changePct,
      r.volume,
      r.rsi,
      r.signal,
    ])
    const csv = [header, ...body].map((line) => line.join(",")).join("\n")
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }))
    const a = document.createElement("a")
    a.href = url
    a.download = "nse-screener.csv"
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-4">
        <span className="flex size-8 items-center justify-center rounded-lg bg-accent text-accent-foreground">
          <ScanSearch className="size-4" aria-hidden="true" />
        </span>
        <h2 className="text-sm font-semibold text-card-foreground">
          Live Market Screener
        </h2>
        <span className="tnum rounded-md bg-accent px-2 py-1 text-[11px] font-medium text-accent-foreground">
          {`NSE · ${universeSize.toLocaleString("en-IN")} stocks`}
        </span>

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowFilters((v) => !v)}
            aria-expanded={showFilters}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors",
              showFilters
                ? "bg-accent text-accent-foreground"
                : "bg-muted text-muted-foreground hover:text-foreground",
            )}
          >
            <SlidersHorizontal className="size-3.5" aria-hidden="true" />
            Filters
          </button>
          <button
            type="button"
            onClick={exportCsv}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-xs font-medium text-accent-foreground transition-colors hover:bg-primary hover:text-primary-foreground"
          >
            <Download className="size-3.5" aria-hidden="true" />
            Export CSV
          </button>
        </div>
      </header>

      {showFilters ? (
        <div className="animate-fade-slide-in flex flex-wrap items-center gap-2 border-b border-border bg-muted/50 px-5 py-3">
          <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
            Signal
          </span>
          {signalFilters.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setFilter(option)}
              aria-pressed={filter === option}
              className={cn(
                "rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors",
                filter === option
                  ? "bg-primary text-primary-foreground"
                  : "bg-card text-muted-foreground hover:text-foreground",
              )}
            >
              {option}
            </button>
          ))}
        </div>
      ) : null}

      <div className="scrollbar-slim overflow-x-auto">
        <table className="w-full min-w-[52rem] border-collapse text-sm">
          <caption className="sr-only">
            NSE equities with last traded price, change, volume, RSI and model
            signal
          </caption>
          <thead>
            <tr className="border-b border-border bg-muted/60">
              <Th onSort={() => toggleSort("ticker")} active={sortKey === "ticker"}>
                Ticker / Name
              </Th>
              <Th>Sector</Th>
              <Th align="right" onSort={() => toggleSort("ltp")} active={sortKey === "ltp"}>
                LTP (₹)
              </Th>
              <Th
                align="right"
                onSort={() => toggleSort("changePct")}
                active={sortKey === "changePct"}
              >
                Chg %
              </Th>
              <Th align="right" onSort={() => toggleSort("volume")} active={sortKey === "volume"}>
                Volume
              </Th>
              <Th align="right" onSort={() => toggleSort("rsi")} active={sortKey === "rsi"}>
                RSI (14)
              </Th>
              <Th>Signal</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((stock) => (
              <tr
                key={stock.ticker}
                className="border-b border-border last:border-0 transition-colors hover:bg-muted/60"
              >
                <td className="px-5 py-4">
                  <p className="font-semibold text-card-foreground">
                    {stock.ticker}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {stock.name}
                  </p>
                </td>
                <td className="px-5 py-4">
                  <span className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
                    {stock.sector}
                  </span>
                </td>
                <td className="tnum px-5 py-4 text-right font-medium text-card-foreground">
                  {formatInr(stock.ltp)}
                </td>
                <td
                  className={cn(
                    "tnum px-5 py-4 text-right font-semibold",
                    stock.changePct >= 0 ? "text-bullish" : "text-bearish",
                  )}
                >
                  {formatPct(stock.changePct)}
                </td>
                <td className="tnum px-5 py-4 text-right text-muted-foreground">
                  {formatVolume(stock.volume)}
                </td>
                <td
                  className={cn(
                    "tnum px-5 py-4 text-right font-semibold",
                    stock.rsi >= 70 && "text-bearish",
                    stock.rsi <= 40 && "text-bullish",
                    stock.rsi > 40 && stock.rsi < 70 && "text-card-foreground",
                  )}
                >
                  {stock.rsi.toFixed(1)}
                </td>
                <td className="px-5 py-4">
                  <SignalBadge signal={stock.signal} />
                </td>
              </tr>
            ))}
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="px-5 py-12 text-center text-sm text-muted-foreground"
                >
                  {`No stocks match the ${filter} signal filter.`}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function Th({
  children,
  align = "left",
  onSort,
  active,
}: {
  children: React.ReactNode
  align?: "left" | "right"
  onSort?: () => void
  active?: boolean
}) {
  return (
    <th
      scope="col"
      className={cn(
        "px-5 py-3 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      {onSort ? (
        <button
          type="button"
          onClick={onSort}
          className={cn(
            "inline-flex items-center gap-1 transition-colors hover:text-foreground",
            align === "right" && "flex-row-reverse",
            active && "text-primary",
          )}
        >
          {children}
          <ArrowUpDown className="size-3" aria-hidden="true" />
        </button>
      ) : (
        children
      )}
    </th>
  )
}
