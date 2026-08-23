import { Sparkline } from "./Sparkline"
import { cn, formatIndex, formatPct } from "@/lib/utils"
import type { IndexCard } from "@/lib/types"

export function IndexTile({ index }: { index: IndexCard }) {
  const isUp = index.changePct >= 0

  return (
    <div className="rounded-2xl border border-border bg-card p-5 transition-shadow hover:shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
          {index.label}
        </p>
        <span
          className={cn(
            "tnum rounded-md px-2 py-0.5 text-[11px] font-semibold",
            isUp
              ? "bg-bullish-muted text-bullish"
              : "bg-bearish-muted text-bearish",
          )}
        >
          {formatPct(index.changePct)}
        </span>
      </div>

      <p className="tnum mt-3 text-2xl font-semibold tracking-tight text-card-foreground">
        {formatIndex(index.value)}
      </p>

      <Sparkline
        data={index.sparkline}
        trend={isUp ? "up" : "down"}
        className="mt-5"
      />
    </div>
  )
}
