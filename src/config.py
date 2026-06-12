import os

# Watchlist: liquid Binance spot pairs
SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "LINK/USDT", "AVAX/USDT", "TON/USDT",
    "DOT/USDT", "NEAR/USDT", "SUI/USDT", "APT/USDT", "LTC/USDT",
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

# Storage (attach a Railway volume at /data in production)
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "journal.db"))

SKILL_DIR = os.path.join(os.path.dirname(__file__), "..", "skill")
