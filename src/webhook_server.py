"""FastAPI webhook server — receives TradingView Pine Script alerts.

Flow:
  TradingView alert (Pine Script) → POST /webhook/tv → signal queue
  → main.py webhook_processor() → Claude analysis → risk gate → Telegram

Requirements:
  - Add WEBHOOK_SECRET to .env  (any random string, e.g. openssl rand -hex 16)
  - Expose port 8080 in docker-compose.yml (already done)
  - TradingView Pro+ plan for webhook alerts

TradingView alert message (JSON body):
  {
    "secret":   "your-webhook-secret",
    "symbol":   "BTCUSDT",
    "exchange": "BINANCE",
    "screener": "crypto",
    "setup":    "TV",
    "action":   "long"
  }

For stocks use:  "exchange": "NASDAQ", "screener": "america"
For forex use:   "exchange": "FX",     "screener": "forex"
"""

import asyncio
import os
import traceback
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="TradingView Webhook", docs_url=None, redoc_url=None)

_signal_queue: asyncio.Queue | None = None
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


def init_queue(q: asyncio.Queue):
    global _signal_queue
    _signal_queue = q


@app.post("/webhook/tv")
async def tradingview_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Token check — skip if WEBHOOK_SECRET not set (dev mode)
    if WEBHOOK_SECRET and body.get("secret") != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    symbol   = body.get("symbol",   "").strip().upper()
    exchange = body.get("exchange", "BINANCE").strip().upper()
    screener = body.get("screener", "crypto").strip().lower()
    setup    = body.get("setup",    "TV")
    action   = body.get("action",   "long").lower()

    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")

    if action not in ("long", "short"):
        return JSONResponse({"status": "ignored", "reason": "action must be long or short"})

    print(f"[webhook] {datetime.now():%H:%M:%S} TV alert: {exchange}:{symbol} setup={setup} {action}")

    if _signal_queue is not None:
        await _signal_queue.put({
            "symbol":   symbol,
            "exchange": exchange,
            "screener": screener,
            "setup":    setup,
            "side":     action,
            "source":   "tradingview_webhook",
        })
        return JSONResponse({"status": "queued", "symbol": symbol})

    return JSONResponse({"status": "dropped", "reason": "queue not ready"}, status_code=503)


@app.get("/health")
async def health():
    return {
        "status":     "ok",
        "queue_size": _signal_queue.qsize() if _signal_queue else 0,
        "time":       datetime.now().isoformat(),
    }


async def run_webhook_server(host: str = "0.0.0.0", port: int = 8080):
    """Start uvicorn as an asyncio task (called from main.py)."""
    cfg    = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(cfg)
    print(f"[webhook] server listening on {host}:{port}")
    await server.serve()
