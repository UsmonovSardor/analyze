#!/usr/bin/env bash
# Run the FULL bot locally on the Mac (Binance reachable → auto-trade works).
# While this runs, PAUSE the Railway deployment to avoid a Telegram getUpdates conflict.
set -euo pipefail
cd "$(dirname "$0")"

[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt

# load .env (must contain TELEGRAM_*, CLAUDE_CODE_OAUTH_TOKEN, BINANCE_API_KEY/SECRET)
set -a; [ -f .env ] && source .env; set +a

export DB_PATH="${DB_PATH:-$PWD/journal.db}"
echo "[run_local] trading=${TRADING_MODE:-off}  db=$DB_PATH"
exec .venv/bin/python -m src.main
