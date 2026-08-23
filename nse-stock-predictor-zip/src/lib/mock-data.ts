import type {
  IndexCard,
  NavItem,
  ScreenerMetrics,
  SignalFeedItem,
  StockItem,
  SystemHealthInfo,
} from "./types"

export const navItems: NavItem[] = [
  { id: "screener", label: "Market Screener", icon: "scan-search", badge: true },
  {
    id: "indicators",
    label: "Technical Indicators (pandas-ta)",
    icon: "bar-chart-3",
  },
  { id: "ml", label: "ML Signal Predictor", icon: "cpu" },
  { id: "sql", label: "DuckDB SQL Studio", icon: "database" },
  { id: "backtest", label: "Alpha Backtest Hub", icon: "flask-conical" },
  { id: "logs", label: "Pipeline & Cache Logs", icon: "terminal" },
]

export const screenerMetrics: ScreenerMetrics = {
  nseUniverse: 2147,
  universeDelta: 12,
  buySignals: 487,
  buyDelta: 38,
  sellSignals: 231,
  sellDelta: 14,
  avgRsi: 53.8,
  avgRsiDelta: 1.4,
  lastSync: "10:47 AM",
}

export const indexCards: IndexCard[] = [
  {
    id: "nifty50",
    label: "NIFTY 50",
    value: 22471.2,
    changePct: 0.74,
    sparkline: [28, 34, 30, 38, 33, 46, 52, 44, 58, 63, 55, 70, 66, 78, 100],
  },
  {
    id: "banknifty",
    label: "BANK NIFTY",
    value: 48112.5,
    changePct: 0.31,
    sparkline: [22, 26, 31, 27, 40, 36, 48, 43, 52, 47, 60, 56, 68, 72, 100],
  },
  {
    id: "niftyit",
    label: "NIFTY IT",
    value: 33756.8,
    changePct: -0.52,
    sparkline: [30, 38, 35, 44, 41, 52, 48, 57, 54, 63, 60, 70, 66, 74, 100],
  },
  {
    id: "niftyfmcg",
    label: "NIFTY FMCG",
    value: 55298.0,
    changePct: 1.08,
    sparkline: [24, 29, 27, 35, 32, 42, 39, 49, 46, 56, 53, 64, 61, 76, 100],
  },
]

export const stocks: StockItem[] = [
  {
    ticker: "RELIANCE",
    name: "Reliance Industries",
    sector: "Energy",
    ltp: 2847.3,
    changePct: 1.24,
    volume: 12_400_000,
    rsi: 62.4,
    signal: "BUY",
  },
  {
    ticker: "TCS",
    name: "Tata Consultancy Services",
    sector: "IT",
    ltp: 3412.55,
    changePct: 0.87,
    volume: 5_100_000,
    rsi: 58.2,
    signal: "BUY",
  },
  {
    ticker: "HDFCBANK",
    name: "HDFC Bank",
    sector: "Banking",
    ltp: 1654.2,
    changePct: -0.43,
    volume: 8_700_000,
    rsi: 44.1,
    signal: "HOLD",
  },
  {
    ticker: "INFY",
    name: "Infosys Limited",
    sector: "IT",
    ltp: 1512.8,
    changePct: 2.11,
    volume: 9_200_000,
    rsi: 71.3,
    signal: "BUY",
  },
  {
    ticker: "BAJFINANCE",
    name: "Bajaj Finance Ltd",
    sector: "NBFC",
    ltp: 6893.1,
    changePct: -1.76,
    volume: 3_400_000,
    rsi: 35.7,
    signal: "SELL",
  },
  {
    ticker: "WIPRO",
    name: "Wipro Limited",
    sector: "IT",
    ltp: 452.35,
    changePct: 0.33,
    volume: 11_000_000,
    rsi: 50.8,
    signal: "HOLD",
  },
  {
    ticker: "ICICIBANK",
    name: "ICICI Bank Ltd",
    sector: "Banking",
    ltp: 1078.9,
    changePct: 1.58,
    volume: 14_600_000,
    rsi: 65.9,
    signal: "BUY",
  },
]

export const signalFeed: SignalFeedItem[] = [
  {
    id: "s1",
    ticker: "LTIM",
    signal: "BUY",
    confidence: 91.4,
    model: "XGBoost v2",
    time: "09:32",
  },
  {
    id: "s2",
    ticker: "SBIN",
    signal: "SELL",
    confidence: 87.2,
    model: "LSTM-Seq",
    time: "09:28",
  },
  {
    id: "s3",
    ticker: "ADANIENT",
    signal: "BUY",
    confidence: 78.9,
    model: "RF Ensemble",
    time: "09:21",
  },
  {
    id: "s4",
    ticker: "NIFTYBANK",
    signal: "HOLD",
    confidence: 65.1,
    model: "CatBoost",
    time: "09:15",
  },
]

export const systemHealth: SystemHealthInfo = {
  engine: "DuckDB In-Memory",
  active: true,
  cacheHitPct: 99.2,
  latencyMs: 14,
}

export const currentUser = {
  name: "Rajesh Kumar",
  role: "Quantitative Lead",
  avatar: "/avatar-rajesh.png",
}
