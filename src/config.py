import os

# Watchlist: liquid Binance spot pairs (broad coverage — the screener filters cheaply)
SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "LINK/USDT", "AVAX/USDT", "TON/USDT",
    "DOT/USDT", "NEAR/USDT", "SUI/USDT", "APT/USDT", "LTC/USDT",
    "TRX/USDT", "POL/USDT", "ATOM/USDT", "UNI/USDT", "FIL/USDT",
    "INJ/USDT", "ARB/USDT", "OP/USDT", "AAVE/USDT", "RENDER/USDT",
    "SEI/USDT", "TIA/USDT", "FET/USDT", "RUNE/USDT", "ICP/USDT",
    "HBAR/USDT", "ALGO/USDT", "STX/USDT", "GALA/USDT", "SAND/USDT",
]

ENTRY_TF = "1h"
CONTEXT_TF = "4h"
CANDLES = 300  # bars fetched per timeframe

SCAN_INTERVAL_SEC = 30 * 60       # screener cadence — 30 daqiqada bir scan
OUTCOME_CHECK_SEC = 5 * 60        # open-signal TP/SL checker cadence

# Risk engine gates (deterministic, independent of the model)
# Tuned for ~5-8 signals/day across crypto + forex + stocks, both directions.
MIN_SCORE = int(os.getenv("MIN_SCORE", "6"))
MIN_RR_TP2 = float(os.getenv("MIN_RR_TP2", "1.6"))   # entry->TP2 must be >= this R
MAX_SIGNALS_PER_DAY = int(os.getenv("MAX_SIGNALS_PER_DAY", "12"))
TARGET_SIGNALS_PER_DAY = int(os.getenv("TARGET_SIGNALS_PER_DAY", "5"))
MAX_OPEN_SIGNALS = int(os.getenv("MAX_OPEN_SIGNALS", "8"))
COOLDOWN_HOURS_PER_SYMBOL = int(os.getenv("COOLDOWN_HOURS_PER_SYMBOL", "3"))

# Direction: allow short signals (forex both ways; crypto short on Futures).
ALLOW_SHORTS = os.getenv("ALLOW_SHORTS", "true").lower() == "true"
# When BTC 4h is bearish, block crypto LONGS but still allow crypto SHORTS.
BTC_GATE_BLOCKS_LONGS_ONLY = True

# Gemini
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
MAX_CLAUDE_CALLS_PER_DAY = int(os.getenv("MAX_CLAUDE_CALLS_PER_DAY", "150"))

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
MAX_TRADE_QUOTE = float(os.getenv("MAX_TRADE_QUOTE", "100"))  # hard cap per position (USDT margin)
DAILY_LOSS_STOP_R = float(os.getenv("DAILY_LOSS_STOP_R", "-3"))  # halt trading for the day at -3R

# Market type for execution: "future" (USDT-M perpetuals — supports SHORT) or "spot" (LONG only).
# Futures is required to trade short signals. Set BINANCE_MARKET=spot to force spot/long-only.
BINANCE_MARKET = os.getenv("BINANCE_MARKET", "future")
LEVERAGE = int(os.getenv("LEVERAGE", "3"))  # futures leverage per position (keep low)
# Futures host: fapi.binance.com. Spot host: api.binance.com.
# On a Binance-reachable server (Hetzner EU) the defaults work; on a blocked host you'll get 451.
BINANCE_HOSTNAME = os.getenv("BINANCE_HOSTNAME", "")  # empty => ccxt default for the chosen market

def trading_enabled() -> bool:
    return bool(BINANCE_API_KEY and BINANCE_API_SECRET) and TRADING_MODE in ("semi", "auto")

def futures_enabled() -> bool:
    return trading_enabled() and BINANCE_MARKET == "future"

def can_autotrade_side(side: str) -> bool:
    """Auto-trade is possible for longs always; shorts only on futures (spot can't short)."""
    if not trading_enabled():
        return False
    if side == "short":
        return BINANCE_MARKET == "future"
    return True

# Storage (attach a Railway volume at /data in production)
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "journal.db"))

SKILL_DIR = os.path.join(os.path.dirname(__file__), "..", "skill")

# ── TradingView integration ─────────────────────────────────────────────────

# Use tradingview-ta as the screener instead of ccxt-based indicators.
# Set to "true" in .env to enable.
USE_TV_SCREENER = os.getenv("USE_TV_SCREENER", "true").lower() == "true"

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
    {"symbol": "FETUSDT",    "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "RENDERUSDT", "exchange": "BINANCE", "screener": "crypto"},
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
    {"symbol": "POLUSDT",  "exchange": "BINANCE", "screener": "crypto"},
    {"symbol": "TONUSDT",  "exchange": "BYBIT",   "screener": "crypto"},

    # ── US Stocks ─────────────────────────────────────────────────────────
    {"symbol": "AAPL",  "exchange": "NASDAQ", "screener": "america"},
    {"symbol": "NVDA",  "exchange": "NASDAQ", "screener": "america"},
    {"symbol": "TSLA",  "exchange": "NASDAQ", "screener": "america"},
    {"symbol": "MSFT",  "exchange": "NASDAQ", "screener": "america"},
    {"symbol": "AMZN",  "exchange": "NASDAQ", "screener": "america"},
    {"symbol": "META",  "exchange": "NASDAQ", "screener": "america"},

    # ── Forex ─────────────────────────────────────────────────────────────
    {"symbol": "EURUSD", "exchange": "FX", "screener": "forex"},
    {"symbol": "GBPUSD", "exchange": "FX", "screener": "forex"},
    {"symbol": "USDJPY", "exchange": "FX", "screener": "forex"},
    {"symbol": "AUDUSD", "exchange": "FX", "screener": "forex"},

    # ── Commodities ───────────────────────────────────────────────────────
    {"symbol": "XAUUSD", "exchange": "TVC", "screener": "cfd"},
]

# ── Forex/Stocks for /coins keyboard ───────────────────────────────────────
FOREX_SYMBOLS = [
    {"symbol": "EURUSD", "exchange": "FX",    "screener": "forex"},
    {"symbol": "GBPUSD", "exchange": "FX",    "screener": "forex"},
    {"symbol": "USDJPY", "exchange": "FX",    "screener": "forex"},
    {"symbol": "XAUUSD", "exchange": "TVC", "screener": "cfd"},
]

STOCK_SYMBOLS = [
    {"symbol": "AAPL",  "exchange": "NASDAQ", "screener": "america"},
    {"symbol": "NVDA",  "exchange": "NASDAQ", "screener": "america"},
    {"symbol": "TSLA",  "exchange": "NASDAQ", "screener": "america"},
    {"symbol": "MSFT",  "exchange": "NASDAQ", "screener": "america"},
    {"symbol": "AMZN",  "exchange": "NASDAQ", "screener": "america"},
]
