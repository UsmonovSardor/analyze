import os

# Watchlist: liquid Binance spot pairs (broad coverage — the screener filters cheaply)
SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "LINK/USDT", "AVAX/USDT", "TON/USDT",
    "DOT/USDT", "NEAR/USDT", "SUI/USDT", "APT/USDT", "LTC/USDT",
    "TRX/USDT", "MATIC/USDT", "ATOM/USDT", "UNI/USDT", "FIL/USDT",
    "INJ/USDT", "ARB/USDT", "OP/USDT", "AAVE/USDT", "RNDR/USDT",
    "SEI/USDT", "TIA/USDT", "FET/USDT", "RUNE/USDT", "ICP/USDT",
    "HBAR/USDT", "ALGO/USDT", "STX/USDT", "GALA/USDT", "SAND/USDT",
]

ENTRY_TF = "1h"
CONTEXT_TF = "4h"
CANDLES = 300  # bars fetched per timeframe

SCAN_INTERVAL_SEC = 15 * 60       # screener cadence
OUTCOME_CHECK_SEC = 10 * 60       # open-signal TP/SL checker cadence

# Risk engine gates (deterministic, independent of the model)
MIN_SCORE = 7
MIN_RR_TP2 = 2.0                  # entry->TP2 must be >= 2R
MAX_SIGNALS_PER_DAY = 5
MAX_OPEN_SIGNALS = 4
COOLDOWN_HOURS_PER_SYMBOL = 12    # no repeat signal on same symbol within this window

# Claude
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_CLAUDE_CALLS_PER_DAY = int(os.getenv("MAX_CLAUDE_CALLS_PER_DAY", "40"))

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Binance live trading (optional). Empty key => trading disabled, signals only.
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
# "semi" = ask for confirmation button before each trade; "auto" = execute automatically;
# "off" = never trade. Defaults to semi when keys exist, else off.
TRADING_MODE = os.getenv("TRADING_MODE", "semi")
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))   # 1% of quote balance
MAX_TRADE_QUOTE = float(os.getenv("MAX_TRADE_QUOTE", "100"))  # hard cap per position (USDT)
DAILY_LOSS_STOP_R = float(os.getenv("DAILY_LOSS_STOP_R", "-3"))  # halt trading for the day at -3R
BINANCE_HOSTNAME = os.getenv("BINANCE_HOSTNAME", "api.binance.com")

def trading_enabled() -> bool:
    return bool(BINANCE_API_KEY and BINANCE_API_SECRET) and TRADING_MODE in ("semi", "auto")

# Storage (attach a Railway volume at /data in production)
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "journal.db"))

SKILL_DIR = os.path.join(os.path.dirname(__file__), "..", "skill")

# ── TradingView integration ─────────────────────────────────────────────────

# Use tradingview-ta as the screener instead of ccxt-based indicators.
# Set to "true" in .env to enable.
USE_TV_SCREENER = os.getenv("USE_TV_SCREENER", "false").lower() == "true"

# Webhook server for TradingView Pine Script alerts (Pro+ plan required).
WEBHOOK_ENABLED = os.getenv("WEBHOOK_ENABLED", "false").lower() == "true"
WEBHOOK_PORT    = int(os.getenv("WEBHOOK_PORT", "8080"))
WEBHOOK_SECRET  = os.getenv("WEBHOOK_SECRET", "")  # set to a random string in .env

# TradingView watchlist — replaces SYMBOLS when USE_TV_SCREENER=true.
# Format: {"symbol": "TV_SYMBOL", "exchange": "EXCHANGE", "screener": "SCREENER"}
# Screeners: "crypto" | "america" (US stocks) | "forex" | "cfd" (indices/commodities)
TV_SYMBOLS = [
    # ── Crypto (Binance) ──────────────────────────────────────────────────
    {"symbol": "BTCUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "ETHUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "SOLUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "BNBUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "XRPUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "DOGEUSDT", "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "ADAUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "LINKUSDT", "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "AVAXUSDT", "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "DOTUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "NEARUSDT", "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "SUIUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "APTUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "INJUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "ARBUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "OPUSDT",   "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "AAVEUSDT", "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "FETUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "RNDRUSDT", "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "HBARUSDT", "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "ATOMUSDT", "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "UNIUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "LTCUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "TRXUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "ICPUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "STXUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "RUNEUSDT", "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "SEIUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "TIAUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "GALAUSDT", "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "SANDUSDT", "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "ALGOUSDT", "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "FILUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "MATICUSDT","exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "TONUSDT",  "exchange": "BYBIT",   "screener": "crypto"},

    # ── US Stocks (uncomment to enable) ───────────────────────────────────
    # {"symbol": "AAPL",  "exchange": "NASDAQ", "screener": "america"},
    # {"symbol": "NVDA",  "exchange": "NASDAQ", "screener": "america"},
    # {"symbol": "TSLA",  "exchange": "NASDAQ", "screener": "america"},
    # {"symbol": "MSFT",  "exchange": "NASDAQ", "screener": "america"},
    # {"symbol": "AMZN",  "exchange": "NASDAQ", "screener": "america"},
    # {"symbol": "META",  "exchange": "NASDAQ", "screener": "america"},
    # {"symbol": "GOOGL", "exchange": "NASDAQ", "screener": "america"},

    # ── Forex (uncomment to enable) ───────────────────────────────────────
    # {"symbol": "EURUSD", "exchange": "FX", "screener": "forex"},
    # {"symbol": "GBPUSD", "exchange": "FX", "screener": "forex"},
    # {"symbol": "USDJPY", "exchange": "FX", "screener": "forex"},

    # ── Indices / Commodities (uncomment to enable) ───────────────────────
    # {"symbol": "US30",  "exchange": "FOREXCOM", "screener": "cfd"},
    # {"symbol": "SPX500","exchange": "FOREXCOM", "screener": "cfd"},
    # {"symbol": "XAUUSD","exchange": "FOREXCOM", "screener": "cfd"},
]
