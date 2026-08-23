import { Cpu } from "lucide-react"
import { SignalBadge } from "./SignalBadge"
import type { SignalFeedItem } from "@/lib/types"

export function SignalFeed({ items }: { items: SignalFeedItem[] }) {
  return (
    <section className="rounded-2xl border border-border bg-card">
      <header className="flex items-center gap-3 border-b border-border px-5 py-4">
        <span className="flex size-8 items-center justify-center rounded-lg bg-accent text-accent-foreground">
          <Cpu className="size-4" aria-hidden="true" />
        </span>
        <h2 className="text-sm font-semibold text-card-foreground">
          ML Signal Feed
        </h2>
        <span className="ml-auto flex items-center gap-1.5 text-xs font-medium text-bullish">
          <span
            className="animate-pulse-dot size-1.5 rounded-full bg-bullish"
            aria-hidden="true"
          />
          Live
        </span>
      </header>

      <ul className="divide-y divide-border">
        {items.map((item, i) => (
          <li
            key={item.id}
            className="animate-fade-slide-in flex items-center gap-3 px-5 py-4"
            style={{ animationDelay: `${i * 70}ms` }}
          >
            <SignalBadge signal={item.signal} className="w-14 shrink-0" />

            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-card-foreground">
                {item.ticker}
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {item.model}
              </p>
            </div>

            <div className="shrink-0 text-right">
              <p className="tnum text-sm font-semibold text-card-foreground">
                {`${item.confidence.toFixed(1)}%`}
              </p>
              <p className="tnum text-xs text-muted-foreground">{item.time}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
