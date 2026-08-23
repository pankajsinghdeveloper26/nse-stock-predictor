import { useEffect, useRef, useState } from "react"
import { Bell, ChevronRight, Search, Settings } from "lucide-react"

export function TopBar() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState("")

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [])

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-4 border-b border-border bg-background/85 px-6 backdrop-blur-md">
      <nav aria-label="Breadcrumb" className="min-w-0">
        <ol className="flex items-center gap-2 text-sm">
          <li className="hidden truncate text-muted-foreground sm:block">
            AlphaVision NSE Analytics
          </li>
          <li className="hidden sm:block" aria-hidden="true">
            <ChevronRight className="size-4 text-muted-foreground" />
          </li>
          <li className="truncate font-semibold text-foreground">
            Market Screener
          </li>
        </ol>
      </nav>

      <div className="ml-auto flex items-center gap-2">
        <div className="relative hidden md:block">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search ticker, signal..."
            aria-label="Search ticker or signal"
            className="h-10 w-64 rounded-xl border border-border bg-card pl-9 pr-12 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/20"
          />
          <kbd className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            K
          </kbd>
        </div>

        <button
          type="button"
          className="flex size-10 items-center justify-center rounded-xl border border-border bg-card text-muted-foreground transition-colors hover:text-foreground"
        >
          <Bell className="size-4" aria-hidden="true" />
          <span className="sr-only">Notifications</span>
        </button>

        <button
          type="button"
          className="flex size-10 items-center justify-center rounded-xl border border-border bg-card text-muted-foreground transition-colors hover:text-foreground"
        >
          <Settings className="size-4" aria-hidden="true" />
          <span className="sr-only">Settings</span>
        </button>

        <span className="flex h-10 items-center gap-2 rounded-xl bg-accent px-3 text-xs font-semibold text-accent-foreground">
          <span
            className="animate-pulse-dot size-1.5 rounded-full bg-bullish"
            aria-hidden="true"
          />
          NSE Live
        </span>
      </div>
    </header>
  )
}
