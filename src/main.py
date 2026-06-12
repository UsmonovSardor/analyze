"""Main loop: screener scan -> Claude analysis -> risk gate -> Telegram.
Plus: open-signal outcome tracking and weekly stats."""
import asyncio
import time
import traceback

from . import config, journal, risk, screener, telegram
from .analyzer import analyze
from .data import _exchange as _px
from .data import snapshot


def last_price(symbol: str) -> float:
    return float(_px.fetch_ticker(symbol)["last"])


async def scan_once():
    btc_snap = snapshot("BTC/USDT", config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
    if not screener.btc_context_ok(btc_snap):
        print("[scan] BTC 4h downtrend — skipping cycle")
        return

    for symbol in config.SYMBOLS:
        try:
            if journal.signals_today() >= config.MAX_SIGNALS_PER_DAY:
                print("[scan] daily signal cap reached")
                return
            if len(journal.open_signals()) >= config.MAX_OPEN_SIGNALS:
                print("[scan] max open signals reached")
                return
            if journal.recent_signal_for(symbol, config.COOLDOWN_HOURS_PER_SYMBOL):
                continue

            snap = btc_snap if symbol == "BTC/USDT" else snapshot(
                symbol, config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES
            )
            hint = screener.find_candidate(snap)
            if not hint:
                continue

            if journal.claude_calls_today() >= config.MAX_CLAUDE_CALLS_PER_DAY:
                print("[scan] Claude daily call budget exhausted")
                return

            print(f"[scan] candidate {symbol} setup {hint} -> Claude")
            journal.bump_claude_calls()
            sig = await analyze(snap, hint, btc_snap)

            ok, why = risk.validate(sig, last_price(symbol))
            if not ok:
                print(f"[risk] {symbol} rejected: {why}")
                continue

            sig_id = journal.add_signal(sig)
            telegram.send(telegram.format_signal(sig, sig_id))
            print(f"[signal] #{sig_id} {symbol} posted")
        except Exception:
            print(f"[scan] error on {symbol}:\n{traceback.format_exc()}")


def realized_r(row: dict, exit_price: float) -> float:
    """Weighted result in R given partial exits 40/40/20 and final exit price."""
    e, sl = row["entry"], row["stop_loss"]
    r = e - sl
    parts = 0.0
    if row["status"] in ("tp1", "tp2"):
        parts += 0.4 * (row["tp1"] - e) / r
    if row["status"] == "tp2":
        parts += 0.4 * (row["tp2"] - e) / r
    remaining = {"open": 1.0, "tp1": 0.6, "tp2": 0.2}.get(row["status"], 1.0)
    return parts + remaining * (exit_price - e) / r


def check_outcomes():
    for row in journal.open_signals():
        try:
            price_now = last_price(row["symbol"])
            hi = lo = price_now
            # use candle extremes since the last check for hit detection
            candles = _px.fetch_ohlcv(row["symbol"], timeframe="5m", limit=3)
            for c in candles:
                hi, lo = max(hi, c[2]), min(lo, c[3])

            effective_sl = row["entry"] if row["status"] in ("tp1", "tp2") else row["stop_loss"]

            if lo <= effective_sl:
                event = "breakeven" if row["status"] in ("tp1", "tp2") else "stopped"
                r_val = realized_r(row, effective_sl)
                journal.update_status(row["id"], event, r_val, close=True)
                telegram.send(telegram.format_outcome(row, event, r_val))
            elif hi >= row["tp3"] and row["status"] == "tp2":
                r_val = realized_r(row, row["tp3"])
                journal.update_status(row["id"], "tp3", r_val, close=True)
                telegram.send(telegram.format_outcome(row, "tp3", r_val))
            elif hi >= row["tp2"] and row["status"] == "tp1":
                journal.update_status(row["id"], "tp2")
                telegram.send(telegram.format_outcome(row, "tp2"))
            elif hi >= row["tp1"] and row["status"] == "open":
                journal.update_status(row["id"], "tp1")
                telegram.send(telegram.format_outcome(row, "tp1"))
        except Exception:
            print(f"[outcome] error on #{row['id']}:\n{traceback.format_exc()}")


async def main():
    print("[boot] trading-signal-bot starting")
    last_scan = last_outcome = 0.0
    last_weekly = time.time()
    while True:
        # the loop must survive any error (exchange outage, network, etc.) —
        # a crash here causes a container restart storm
        try:
            now = time.time()
            if now - last_scan >= config.SCAN_INTERVAL_SEC:
                last_scan = now
                await scan_once()
            if now - last_outcome >= config.OUTCOME_CHECK_SEC:
                last_outcome = now
                check_outcomes()
            if now - last_weekly >= 7 * 86400:
                last_weekly = now
                telegram.send(telegram.format_weekly(journal.weekly_stats()))
        except Exception:
            print(f"[loop] error:\n{traceback.format_exc()}")
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
