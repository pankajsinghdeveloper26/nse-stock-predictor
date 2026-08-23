import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Format an INR price with the ₹ symbol and 2 decimals. */
export function formatInr(value: number) {
  return `₹${value.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

/** Format a raw share count as a compact string, e.g. 12.4M. */
export function formatVolume(value: number) {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return String(value)
}

/** Format a signed percentage, e.g. +1.24% / -0.43% */
export function formatPct(value: number, digits = 2) {
  const sign = value > 0 ? "+" : ""
  return `${sign}${value.toFixed(digits)}%`
}

/** Format a signed integer delta, e.g. +38 / -14 */
export function formatDelta(value: number) {
  const sign = value > 0 ? "+" : ""
  return `${sign}${value}`
}

/** Format an index level with thousands separators and 1 decimal. */
export function formatIndex(value: number) {
  return value.toLocaleString("en-IN", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })
}
