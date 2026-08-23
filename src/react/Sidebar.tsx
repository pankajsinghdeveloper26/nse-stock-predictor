import { useState } from "react"
import {
  Activity,
  BarChart3,
  Cpu,
  Database,
  FlaskConical,
  LogOut,
  ScanSearch,
  Terminal,
  Zap,
  type LucideIcon,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type { NavItem, SystemHealthInfo } from "@/lib/types"

const iconMap: Record<NavItem["icon"], LucideIcon> = {
  "scan-search": ScanSearch,
  "bar-chart-3": BarChart3,
  cpu: Cpu,
  database: Database,
  "flask-conical": FlaskConical,
  terminal: Terminal,
}

interface SidebarProps {
  items: NavItem[]
  health: SystemHealthInfo
  user: { name: string; role: string; avatar: string }
}

export function Sidebar({ items, health, user }: SidebarProps) {
  const [activeId, setActiveId] = useState(items[0]?.id ?? "")

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 px-6 py-6">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
          <Activity className="size-5" aria-hidden="true" />
        </span>
        <div className="leading-tight">
          <p className="text-lg font-semibold tracking-tight">AlphaVision</p>
          <p className="text-lg font-semibold tracking-tight text-primary">
            Quant
          </p>
        </div>
      </div>

      <div className="px-4">
        <div className="flex items-center gap-2 rounded-xl bg-muted px-3 py-2.5">
          <span
            className="animate-pulse-dot size-1.5 shrink-0 rounded-full bg-bullish"
            aria-hidden="true"
          />
          <p className="truncate text-xs font-medium text-muted-foreground">
            NSE Local Parquet Engine
          </p>
        </div>
      </div>

      <nav
        aria-label="Primary"
        className="scrollbar-slim mt-6 flex-1 overflow-y-auto border-t border-border px-4 pt-6"
      >
        <p className="px-2 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
          Navigation
        </p>

        <ul className="mt-3 flex flex-col gap-1">
          {items.map((item) => {
            const Icon = iconMap[item.icon]
            const isActive = item.id === activeId

            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => setActiveId(item.id)}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition-colors",
                    isActive
                      ? "bg-accent font-semibold text-accent-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <Icon className="size-4 shrink-0" aria-hidden="true" />
                  <span className="flex-1 text-pretty">{item.label}</span>
                  {item.badge && isActive ? (
                    <span
                      className="size-1.5 shrink-0 rounded-full bg-primary"
                      aria-hidden="true"
                    />
                  ) : null}
                </button>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="border-t border-border p-4">
        <div className="rounded-xl bg-muted p-4">
          <p className="flex items-center gap-2 text-xs font-semibold text-foreground">
            <Zap className="size-3.5 text-primary" aria-hidden="true" />
            System Health
          </p>

          <p className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
            <span
              className={cn(
                "size-1.5 shrink-0 rounded-full",
                health.active ? "bg-bullish" : "bg-bearish",
              )}
              aria-hidden="true"
            />
            {`${health.engine}: ${health.active ? "Active" : "Idle"}`}
          </p>

          <dl className="mt-3 flex flex-col gap-1.5 text-xs">
            <div className="flex items-center justify-between gap-2">
              <dt className="text-muted-foreground">Cache Hit</dt>
              <dd className="tnum font-semibold text-primary">
                {`${health.cacheHitPct.toFixed(1)}%`}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-muted-foreground">Latency</dt>
              <dd className="tnum font-semibold text-primary">
                {`${health.latencyMs}ms`}
              </dd>
            </div>
          </dl>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <img
            src={user.avatar || "/placeholder.svg"}
            alt=""
            width={36}
            height={36}
            className="size-9 shrink-0 rounded-full object-cover"
          />
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-sm font-semibold">{user.name}</p>
            <p className="truncate text-xs text-muted-foreground">
              {user.role}
            </p>
          </div>
          <button
            type="button"
            className="flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <LogOut className="size-4" aria-hidden="true" />
            <span className="sr-only">Sign out</span>
          </button>
        </div>
      </div>
    </div>
  )
}
