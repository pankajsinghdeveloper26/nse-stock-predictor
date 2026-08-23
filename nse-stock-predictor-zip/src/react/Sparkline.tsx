import { cn } from "@/lib/utils"

interface SparklineProps {
  /** Normalised values, oldest → newest. Last bar is highlighted. */
  data: number[]
  /** Bullish bars are lilac, bearish bars are washed red. */
  trend: "up" | "down"
  className?: string
}

export function Sparkline({ data, trend, className }: SparklineProps) {
  const max = Math.max(...data, 1)

  return (
    <div
      className={cn("flex h-16 items-end gap-1.5", className)}
      aria-hidden="true"
    >
      {data.map((value, i) => {
        const isLast = i === data.length - 1
        const heightPct = Math.max((value / max) * 100, 6)

        return (
          <span
            key={i}
            className={cn(
              "flex-1 rounded-full animate-bar-rise",
              isLast
                ? "bg-primary"
                : trend === "up"
                  ? "bg-accent"
                  : "bg-bearish-muted",
            )}
            style={{
              height: `${heightPct}%`,
              animationDelay: `${i * 35}ms`,
            }}
          />
        )
      })}
    </div>
  )
}
