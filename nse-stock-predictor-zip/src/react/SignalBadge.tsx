import { cn } from "@/lib/utils"
import type { SignalType } from "@/lib/types"

const styles: Record<SignalType, string> = {
  BUY: "bg-bullish-muted text-bullish",
  SELL: "bg-bearish-muted text-bearish",
  HOLD: "bg-neutral-signal text-neutral-signal-foreground",
}

interface SignalBadgeProps {
  signal: SignalType
  className?: string
}

export function SignalBadge({ signal, className }: SignalBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-md px-2.5 py-1 text-[11px] font-semibold tracking-wide",
        styles[signal],
        className,
      )}
    >
      {signal}
    </span>
  )
}
