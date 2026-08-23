/**
 * Curated basket of NSE large-caps the dashboard screens live.
 *
 * The FastAPI backend (services.py) doesn't expose a company-metadata
 * endpoint (name/sector), so that part stays a small static lookup here.
 * Everything else shown for these tickers (LTP, % change, volume, RSI,
 * signal, mood) comes straight from the backend at request time.
 */
export interface TickerMeta {
  ticker: string
  name: string
  sector: string
}

// Mirrors services.MARKET_MOOD_PRESETS on the backend (order + tickers),
// so the default /api/market-mood request the dashboard makes reuses the
// backend's own basket instead of triggering a second, different one.
export const SCREENER_BASKET: TickerMeta[] = [
  { ticker: "RELIANCE", name: "Reliance Industries", sector: "Energy" },
  { ticker: "TCS", name: "Tata Consultancy Services", sector: "IT" },
  { ticker: "INFY", name: "Infosys Limited", sector: "IT" },
  { ticker: "HDFCBANK", name: "HDFC Bank", sector: "Banking" },
  { ticker: "ICICIBANK", name: "ICICI Bank Ltd", sector: "Banking" },
  { ticker: "SBIN", name: "State Bank of India", sector: "Banking" },
  { ticker: "ITC", name: "ITC Limited", sector: "FMCG" },
  { ticker: "LT", name: "Larsen & Toubro", sector: "Infrastructure" },
  { ticker: "HINDUNILVR", name: "Hindustan Unilever", sector: "FMCG" },
  { ticker: "BHARTIARTL", name: "Bharti Airtel", sector: "Telecom" },
]
