"""Main loop: screener scan -> Claude analysis -> risk gate -> Telegram (+ optional trade).
Plus: open-signal outcome tracking, weekly stats, and a Telegram button poller."""
import asyncio
import time
import traceback

from . import config, journal, risk, screener, telegram
from .analyzer import analyze
from .data import _exchange as _px
from .data import snapshot


def last_price(symbol: str) -> float:
    return float(_px.fetch_ticker(symbol)["last"])


def _last(df, col):
    return float(df[col].iloc[-1])


def market_context(btc_snap) -> str:
    """One-line human-readable market regime for the report header."""
    ctx = btc_snap["context_tf"]
    price, ema200 = _last(ctx, "close"), _last(ctx, "ema200")
    trend = "ko'tarilish 📈" if price > ema200 else "pasayish 📉"
    rsi = _last(btc_snap["entry_tf"], "rsi")
    return f"BTC {trend} (4h) · BTC RSI {rsi:.0f}"


async def scan_once():
    btc_snap = snapshot("BTC/USDT", config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
    if not screener.btc_context_ok(btc_snap):
        print("[scan] BTC 4h downtrend — skipping cycle")
        return

    perf = journal.setup_performance(30)  # feedback loop: recent per-setup win-rate
    ctx_str = market_context(btc_snap)

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
                symbol, config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
            hint = screener.find_candidate(snap)
            if not hint:
                continue

            if journal.claude_calls_today() >= config.MAX_CLAUDE_CALLS_PER_DAY:
                print("[scan] Claude daily call budget exhausted")
                return

            print(f"[scan] candidate {symbol} setup {hint} -> Claude")
            journal.bump_claude_calls()
            sig = await analyze(snap, hint, btc_snap, perf)

            ok, why = risk.validate(sig, last_price(symbol))
            if not ok:
                print(f"[risk] {symbol} rejected: {why}")
                continue

            sig_id = journal.add_signal(sig)
            kb = telegram.execute_keyboard(sig_id) if config.trading_enabled() else None
            telegram.send(telegram.format_signal(sig, sig_id, ctx_str), reply_markup=kb)
            if config.trading_enabled() and config.TRADING_MODE == "auto":
                _try_execute(sig_id)
            print(f"[signal] #{sig_id} {symbol} posted")
        except Exception:
            print(f"[scan] error on {symbol}:\n{traceback.format_exc()}")


def _try_execute(sig_id: int):
    """Place a real order for a signal (guarded by daily loss stop)."""
    from . import exchange_trade
    sig = journal.get_signal(sig_id)
    if not sig or sig["executed"]:
        return "already executed or missing"
    if journal.realized_r_today() <= config.DAILY_LOSS_STOP_R:
        telegram.send(f"⛔ Kunlik zarar limiti ({config.DAILY_LOSS_STOP_R}R) — bugun savdo to'xtatildi.")
        return "daily loss stop"
    res = exchange_trade.execute_signal(sig)
    if not res.get("ok"):
        telegram.send(f"❌ Savdo bajarilmadi #{sig_id}: {res.get('error')}")
        return res.get("error")
    journal.mark_executed(sig_id, res["qty"], res["fill"], res.get("oco_id"))
    telegram.send(telegram.format_trade_filled(sig_id, sig["symbol"], res["qty"], res["fill"], res["oco"]))
    if res.get("warn"):
        telegram.send(f"⚠️ #{sig_id}: {res['warn']}")
    return "ok"


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
            for c in _px.fetch_ohlcv(row["symbol"], timeframe="5m", limit=3):
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


async def telegram_poller():
    """Long-poll for inline-button presses (Execute / Skip) in semi-auto mode."""
    offset = 0
    while True:
        try:
            updates = await asyncio.to_thread(telegram.get_updates, offset, 25)
            for u in updates:
                offset = u["update_id"] + 1
                cb = u.get("callback_query")
                if not cb:
                    continue
                data = cb.get("data", "")
                action, _, sid = data.partition(":")
                telegram.answer_callback(cb["id"])
                if action == "exec" and config.trading_enabled():
                    result = await asyncio.to_thread(_try_execute, int(sid))
                    print(f"[exec] #{sid}: {result}")
                elif action == "skip":
                    telegram.send(f"❌ Signal #{sid} o'tkazib yuborildi.")
        except Exception:
            print(f"[poller] error:\n{traceback.format_exc()}")
            await asyncio.sleep(5)


async def scan_loop():
    last_scan = last_outcome = 0.0
    last_weekly = time.time()
    while True:
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


async def main():
    mode = config.TRADING_MODE if config.trading_enabled() else "off (signals only)"
    print(f"[boot] trading-signal-bot starting · trading={mode}")
    tasks = [scan_loop()]
    if config.trading_enabled() and config.TRADING_MODE == "semi":
        tasks.append(telegram_poller())  # only needed to receive Execute buttons
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
