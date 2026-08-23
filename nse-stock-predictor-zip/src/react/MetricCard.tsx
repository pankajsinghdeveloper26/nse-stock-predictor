import {
  Activity,
  Database,
  TrendingDown,
  TrendingUp,
  type LucideIcon,
} from "lucide-react"
import { cn } from "@/lib/utils"

const icons: Record<string, LucideIcon> = {
  database: Database,
  "trending-up": TrendingUp,
  "trending-down": TrendingDown,
  activity: Activity,
}

interface MetricCardProps {
  label: string
  value: string
  delta: string
  deltaLabel: string
  deltaTone: "bullish" | "bearish" | "muted"
  icon: keyof typeof icons
}

export function MetricCard({
  label,
  value,
  delta,
  deltaLabel,
  deltaTone,
  icon,
}: MetricCardProps) {
  const Icon = icons[icon] ?? Activity

  return (
    <div className="rounded-2xl border border-border bg-card p-5 transition-shadow hover:shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
          {label}
        </p>
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
          <Icon className="size-4" aria-hidden="true" />
        </span>
      </div>

      <p className="tnum mt-4 text-3xl font-semibold tracking-tight text-card-foreground">
        {value}
      </p>

      <p className="mt-2 flex items-center gap-1.5 text-xs">
        <span
          className={cn(
            "tnum font-semibold",
            deltaTone === "bullish" && "text-bullish",
            deltaTone === "bearish" && "text-bearish",
            deltaTone === "muted" && "text-muted-foreground",
          )}
        >
          {delta}
        </span>
        <span className="text-muted-foreground">{deltaLabel}</span>
      </p>
    </div>
  )
}
