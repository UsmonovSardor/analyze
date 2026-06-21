"""Main loop: screener scan -> Claude analysis -> risk gate -> Telegram (+ optional trade).
Plus: open-signal outcome tracking, weekly stats, and a Telegram button poller."""
import asyncio
import time
import traceback

from . import chart, config, journal, risk, screener, telegram
from .analyzer import analyze
from .data import _exchange as _px
from .data import snapshot


def send_chart(symbol: str, snap: dict, sig: dict | None = None, chat_id=None):
    """Render and post an annotated chart; never let a chart error block a signal."""
    try:
        png = chart.render(symbol, snap, sig)
        telegram.send_photo(png, caption=f"📈 <b>{symbol}</b> · 1h grafik"
                            + (" · kirish nuqtasi belgilandi" if sig and sig.get("signal") == "long" else ""),
                            chat_id=chat_id)
    except Exception:
        print(f"[chart] error for {symbol}:\n{traceback.format_exc()}")


def send_outcome_chart(row: dict, exit_price: float, r_val: float, event: str):
    """Post the closed-trade chart with the exit marked and WIN/LOSS banner."""
    try:
        snap = snapshot(row["symbol"], config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
        sig = {"signal": "long", "symbol": row["symbol"], "setup": row.get("setup"),
               "score": row.get("score"), "entry": row["entry"], "stop_loss": row["stop_loss"],
               "tp1": row["tp1"], "tp2": row["tp2"], "tp3": row["tp3"]}
        png = chart.render(row["symbol"], snap, sig, {"exit": exit_price, "r_val": r_val, "event": event})
        verdict = "✅ ISHLADI" if r_val > 0.05 else ("⚪ breakeven" if abs(r_val) <= 0.05 else "🛑 ishlamadi")
        telegram.send_photo(png, caption=f"📊 <b>#{row['id']} {row['symbol']}</b> natijasi: "
                                         f"{verdict} · <b>{r_val:+.2f}R</b>")
    except Exception:
        print(f"[outcome-chart] error #{row['id']}:\n{traceback.format_exc()}")


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
            send_chart(symbol, snap, sig)
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
                send_outcome_chart(row, effective_sl, r_val, event)
            elif hi >= row["tp3"] and row["status"] == "tp2":
                r_val = realized_r(row, row["tp3"])
                journal.update_status(row["id"], "tp3", r_val, close=True)
                telegram.send(telegram.format_outcome(row, "tp3", r_val))
                send_outcome_chart(row, row["tp3"], r_val, "tp3")
            elif hi >= row["tp2"] and row["status"] == "tp1":
                journal.update_status(row["id"], "tp2")
                telegram.send(telegram.format_outcome(row, "tp2"))
            elif hi >= row["tp1"] and row["status"] == "open":
                journal.update_status(row["id"], "tp1")
                telegram.send(telegram.format_outcome(row, "tp1"))
        except Exception:
            print(f"[outcome] error on #{row['id']}:\n{traceback.format_exc()}")


def _norm_symbol(raw: str) -> str:
    s = raw.strip().upper().replace("-", "/")
    if "/" not in s:
        s = s.removesuffix("USDT") + "/USDT" if s.endswith("USDT") else f"{s}/USDT"
    return s


async def analyze_on_demand(symbol: str, chat_id=None) -> str:
    """Run a full Claude analysis on any pair, on request, and format the report."""
    if journal.claude_calls_today() >= config.MAX_CLAUDE_CALLS_PER_DAY:
        return "⏳ Bugungi Claude tahlil limiti tugadi, ertaga urinib ko'ring."
    try:
        btc_snap = snapshot("BTC/USDT", config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
        snap = btc_snap if symbol == "BTC/USDT" else snapshot(
            symbol, config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
    except Exception as exc:
        return f"❌ <b>{symbol}</b> ma'lumotini olishda xato: {str(exc)[:120]}"

    hint = screener.find_candidate(snap) or "A"  # force analysis even without a screener trigger
    journal.bump_claude_calls()
    sig = await analyze(snap, hint, btc_snap, journal.setup_performance(30))
    ctx_str = market_context(btc_snap)

    if sig.get("signal") == "long":
        ok, why = risk.validate(sig, last_price(symbol))
        if ok:
            sig_id = journal.add_signal(sig)
            kb = telegram.execute_keyboard(sig_id) if config.trading_enabled() else None
            telegram.send(telegram.format_signal(sig, sig_id, ctx_str), reply_markup=kb, chat_id=chat_id)
            send_chart(symbol, snap, sig, chat_id=chat_id)
            return ""  # already sent as a full signal + chart
        send_chart(symbol, snap, None, chat_id=chat_id)
        return (f"📊 <b>{symbol}</b> — tahlil qilindi, lekin signal BERILMADI\n"
                f"Sabab: risk filtri ({why})\n🌐 {ctx_str}")
    send_chart(symbol, snap, None, chat_id=chat_id)
    return (f"📊 <b>{symbol}</b> — hozir kuchli setup yo'q\n"
            f"💡 {sig.get('reason', 'kriteriylarga mos kelmadi')}\n"
            f"Ishonch: {sig.get('score', 0)}/10\n🌐 {ctx_str}")


async def handle_command(text: str, chat_id=None):
    # tolerate emoji/text before the command (reply-keyboard buttons send "📊 /analyze BTC")
    tokens = text.strip().split()
    idx = next((i for i, t in enumerate(tokens) if t.startswith("/")), None)
    if idx is None:
        return
    cmd = tokens[idx].lower().lstrip("/").split("@")[0]
    arg = tokens[idx + 1] if len(tokens) > idx + 1 else None

    if cmd in ("refresh", "yangilash", "r"):
        btc_snap = snapshot("BTC/USDT", config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
        if not screener.btc_context_ok(btc_snap):
            telegram.send(
                "📉 <b>BTC hozir pasayish trendida</b> (4h EMA200 pastida)\n"
                "Signal uchun qulay sharoit yo'q — keyinroq urinib ko'ring.",
                chat_id=chat_id
            )
            return
        # Find candidates quickly (no Claude yet)
        candidates = []
        for sym in config.SYMBOLS:
            try:
                snap = btc_snap if sym == "BTC/USDT" else snapshot(sym, config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
                hint = screener.find_candidate(snap)
                if hint:
                    candidates.append((sym, snap, hint))
            except Exception:
                pass
        if not candidates:
            telegram.send("🔍 Skanerlandi — hozir kuchli setup yo'q.\nKeyinroq avtomatik skaner signal beradi.", chat_id=chat_id)
            return
        telegram.send(f"✅ <b>{len(candidates)} ta kandidat topildi</b> — Claude tahlil qilmoqda...", chat_id=chat_id)
        await scan_once()
    elif cmd in ("coins", "valyutalar", "c"):
        telegram.send("🪙 <b>Valyutani tanlang</b> — tahlil uchun bosing:",
                      reply_markup=telegram.coins_keyboard(), chat_id=chat_id)
    elif cmd in ("analyze", "analiz", "a"):
        if not arg:
            telegram.send("Foydalanish: <code>/analyze BTC</code>",
                          reply_markup=telegram.main_keyboard(), chat_id=chat_id)
            return
        symbol = _norm_symbol(arg)
        telegram.send(f"🔍 <b>{symbol}</b> tahlil qilinmoqda...", chat_id=chat_id)
        msg = await analyze_on_demand(symbol, chat_id=chat_id)
        if msg:
            telegram.send(msg, chat_id=chat_id)
    elif cmd in ("balance", "balans", "portfel"):
        telegram.send(
            "💼 <b>Binance portfel</b>\n\n"
            "⚠️ Server Binance.bh ga kira olmaydi (WAF bloki).\n"
            "Balansni ko'rish uchun quyidagi tugmani bosing 👇",
            reply_markup={"inline_keyboard": [[
                {"text": "🔗 Binance.bh ni ochish", "url": "https://www.binance.bh/en/my/dashboard"}
            ]]},
            chat_id=chat_id
        )
    elif cmd in ("stats", "stat"):
        telegram.send(telegram.format_weekly(journal.weekly_stats()), chat_id=chat_id)
    elif cmd in ("open", "ochiq"):
        telegram.send(telegram.format_open(journal.open_signals()), chat_id=chat_id)
    elif cmd in ("help", "start", "yordam", "menu"):
        telegram.send(telegram.format_help(), reply_markup=telegram.main_keyboard(), chat_id=chat_id)


async def telegram_poller():
    """Long-poll for button presses and text commands."""
    offset = 0
    while True:
        try:
            updates = await asyncio.to_thread(telegram.get_updates, offset, 25)
            for u in updates:
                offset = u["update_id"] + 1
                cb = u.get("callback_query")
                if cb:
                    action, _, sid = cb.get("data", "").partition(":")
                    telegram.answer_callback(cb["id"])
                    if action == "auto":
                        if config.trading_enabled():
                            telegram.send(f"🤖 Avto savdo bajarilmoqda #{sid}...")
                            print(f"[auto] #{sid}: {await asyncio.to_thread(_try_execute, int(sid))}")
                        else:
                            telegram.send("⚠️ Binance ulanmagan. Avto savdo uchun avval API "
                                          "key qo'shing (Spot Trading ruxsati bilan).")
                    elif action == "manual":
                        sg = journal.get_signal(int(sid))
                        if sg:
                            telegram.send(telegram.format_manual_plan(sg, int(sid)))
                    elif action == "skip":
                        telegram.send(
                            f"👁️ Signal #{sid} kuzatish rejimiga olindi.\n"
                            f"Order ochilmadi — lekin TP1/TP2/TP3/SL natijalari yuborilaveradi."
                        )
                    elif action == "coin":
                        symbol = sid  # sid holds the symbol string here (e.g. BTC/USDT)
                        cb_chat = cb.get("message", {}).get("chat", {}).get("id")
                        telegram.send(f"📡 <b>{symbol}</b> ma'lumotlar yuklanmoqda...", chat_id=cb_chat)
                        try:
                            btc_snap = snapshot("BTC/USDT", config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
                            snap = btc_snap if symbol == "BTC/USDT" else snapshot(symbol, config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
                            telegram.send(f"🤖 <b>{symbol}</b> Claude tahlil qilmoqda...", chat_id=cb_chat)
                            hint = screener.find_candidate(snap) or "A"
                            journal.bump_claude_calls()
                            sig = None
                            for _attempt in range(3):
                                try:
                                    sig = await analyze(snap, hint, btc_snap, journal.setup_performance(30))
                                    break
                                except Exception as _e:
                                    if _attempt == 2:
                                        raise
                                    await asyncio.sleep(2)
                            ctx_str = market_context(btc_snap)
                            if sig.get("signal") == "long":
                                ok, why = risk.validate(sig, last_price(symbol))
                                if ok:
                                    sig_id = journal.add_signal(sig)
                                    kb = telegram.execute_keyboard(sig_id) if config.trading_enabled() else None
                                    telegram.send(telegram.format_signal(sig, sig_id, ctx_str), reply_markup=kb, chat_id=cb_chat)
                                    send_chart(symbol, snap, sig, chat_id=cb_chat)
                                else:
                                    send_chart(symbol, snap, None, chat_id=cb_chat)
                                    telegram.send(f"📊 <b>{symbol}</b> — signal berilmadi\nSabab: {why}\n🌐 {ctx_str}", chat_id=cb_chat)
                            else:
                                send_chart(symbol, snap, None, chat_id=cb_chat)
                                telegram.send(f"📊 <b>{symbol}</b> — hozir kuchli setup yo'q\n💡 {sig.get('reason', '')}\nIshonch: {sig.get('score', 0)}/10\n🌐 {ctx_str}", chat_id=cb_chat)
                        except Exception:
                            telegram.send(f"❌ <b>{symbol}</b> tahlilida xato — qayta urinib ko'ring.", chat_id=cb_chat)
                            print(f"[coin-cb] error {symbol}:\n{traceback.format_exc()}")
                    continue
                msg = u.get("message", {})
                text = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id")
                if text and ("/" in text):
                    await handle_command(text, chat_id=chat_id)
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
    if config.TELEGRAM_BOT_TOKEN:
        tasks.append(telegram_poller())  # commands (/analyze, /stats) + execute buttons
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
