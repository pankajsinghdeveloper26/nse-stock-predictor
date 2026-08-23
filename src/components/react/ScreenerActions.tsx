import { useState } from "react"
import { Play, RefreshCw } from "lucide-react"
import { cn } from "@/lib/utils"

export function ScreenerActions() {
  const [refreshing, setRefreshing] = useState(false)
  const [running, setRunning] = useState(false)

  function simulate(setter: (v: boolean) => void) {
    setter(true)
    window.setTimeout(() => setter(false), 1200)
  }

  function refresh() {
    setRefreshing(true)
    // Dashboard.tsx listens for this and re-fetches from the live backend.
    window.dispatchEvent(new CustomEvent("screener:refresh"))
    window.setTimeout(() => setRefreshing(false), 1200)
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        onClick={refresh}
        disabled={refreshing}
        className="flex h-11 items-center gap-2 rounded-xl border border-border bg-card px-4 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-70"
      >
        <RefreshCw
          className={cn("size-4", refreshing && "animate-spin")}
          aria-hidden="true"
        />
        {refreshing ? "Syncing..." : "Refresh"}
      </button>

      <button
        type="button"
        onClick={() => simulate(setRunning)}
        disabled={running}
        className="flex h-11 items-center gap-2 rounded-xl bg-primary px-5 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-70"
      >
        <Play className="size-4" aria-hidden="true" />
        {running ? "Running..." : "Run Screener"}
      </button>
    </div>
  )
}
