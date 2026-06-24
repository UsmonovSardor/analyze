"""Main loop: screener scan -> Claude analysis -> risk gate -> Telegram (+ optional trade).
Plus: open-signal outcome tracking, weekly stats, and a Telegram button poller.
Optional: TradingView screener (USE_TV_SCREENER=true) and webhook server (WEBHOOK_ENABLED=true).
"""
import asyncio
import time
import traceback

from . import chart, config, journal, risk, screener, telegram
from .analyzer import analyze
from .data import _exchange as _px
from .data import snapshot

# ── TradingView optional imports ─────────────────────────────────────────────
if config.USE_TV_SCREENER:
    from .screener_tv import find_candidate_tv, btc_context_ok_tv, tv_symbol_to_ccxt

if config.WEBHOOK_ENABLED:
    from .webhook_server import run_webhook_server, init_queue as _init_webhook_queue

_webhook_queue: asyncio.Queue = asyncio.Queue()


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


async def _process_candidate(symbol: str, snap: dict, hint: str,
                             btc_snap: dict, perf: dict, ctx_str: str):
    """Shared logic: run Claude → risk → Telegram for one candidate."""
    if journal.signals_today() >= config.MAX_SIGNALS_PER_DAY:
        print("[scan] daily signal cap reached")
        return False
    if len(journal.open_signals()) >= config.MAX_OPEN_SIGNALS:
        print("[scan] max open signals reached")
        return False
    if journal.recent_signal_for(symbol, config.COOLDOWN_HOURS_PER_SYMBOL):
        return False
    if journal.claude_calls_today() >= config.MAX_CLAUDE_CALLS_PER_DAY:
        print("[scan] Claude daily call budget exhausted")
        return False

    print(f"[scan] candidate {symbol} setup {hint} -> Claude")
    journal.bump_claude_calls()
    sig = await analyze(snap, hint, btc_snap, perf)

    ok, why = risk.validate(sig, last_price(symbol))
    if not ok:
        print(f"[risk] {symbol} rejected: {why}")
        return False

    sig_id = journal.add_signal(sig)
    kb = telegram.execute_keyboard(sig_id) if config.trading_enabled() else None
    telegram.send(telegram.format_signal(sig, sig_id, ctx_str), reply_markup=kb)
    send_chart(symbol, snap, sig)
    if config.trading_enabled() and config.TRADING_MODE == "auto":
        _try_execute(sig_id)
    print(f"[signal] #{sig_id} {symbol} posted")
    return True


def _find_tv_info(symbol: str) -> dict | None:
    """Find TV config dict for forex/stocks by symbol name."""
    for s in config.FOREX_SYMBOLS + config.STOCK_SYMBOLS:
        if s["symbol"].upper() == symbol.upper():
            return s
    return None


async def _process_tv_noncrpyto(tv_sym: dict, perf: dict, ctx_label: str) -> bool:
    """Run Claude analysis for forex/stocks/indices using tradingview-ta data."""
    from .screener_tv import get_tv_analysis
    from .analyzer import analyze_tv_direct

    symbol = tv_sym["symbol"]
    if journal.signals_today() >= config.MAX_SIGNALS_PER_DAY:
        return False
    if journal.claude_calls_today() >= config.MAX_CLAUDE_CALLS_PER_DAY:
        return False
    if journal.recent_signal_for(symbol, config.COOLDOWN_HOURS_PER_SYMBOL):
        return False

    e1h = get_tv_analysis(symbol, tv_sym["exchange"], tv_sym["screener"], "1h")
    e4h = get_tv_analysis(symbol, tv_sym["exchange"], tv_sym["screener"], "4h")
    current_price = float(e1h.indicators.get("close", 0))
    if not current_price:
        return False

    print(f"[scan-tv] {symbol} -> Claude (non-crypto)")
    journal.bump_claude_calls()
    sig = await analyze_tv_direct(symbol, e1h, e4h, "TV", perf)
    sig["symbol"] = symbol

    ok, why = risk.validate(sig, current_price)
    if not ok:
        print(f"[risk] {symbol} rejected: {why}")
        return False

    sig_id = journal.add_signal(sig)
    telegram.send(telegram.format_signal(sig, sig_id, ctx_label))
    print(f"[signal] #{sig_id} {symbol} posted")
    return True


async def scan_once(notify_chat_id=None):
    def _notify(msg: str):
        if notify_chat_id:
            telegram.send(msg, chat_id=notify_chat_id)

    btc_snap = snapshot("BTC/USDT", config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
    perf    = journal.setup_performance(30)
    ctx_str = market_context(btc_snap)

    btc_ok = btc_context_ok_tv() if config.USE_TV_SCREENER else screener.btc_context_ok(btc_snap)
    btc_status = "📈 ko'tarilish" if btc_ok else "📉 pasayish (crypto o'tkaziladi)"

    # ── TradingView screener path ─────────────────────────────────────────
    if config.USE_TV_SCREENER:
        crypto_syms  = [s for s in config.TV_SYMBOLS if tv_symbol_to_ccxt(s)]
        noncrypto    = [s for s in config.TV_SYMBOLS if not tv_symbol_to_ccxt(s)]
        forex_syms   = [s for s in noncrypto if s["screener"] == "forex"]
        stock_syms   = [s for s in noncrypto if s["screener"] == "america"]

        _notify(
            f"🔍 <b>Skanerlash boshlandi</b>\n"
            f"BTC: {btc_status}\n"
            f"{'✅ Crypto: ' + str(len(crypto_syms)) + ' ta' if btc_ok else '⏭ Crypto: o'tkazildi (BTC pastda)'}\n"
            f"✅ Forex/Oltin: {len(forex_syms)} ta\n"
            f"✅ US Aksiyalar: {len(stock_syms)} ta\n"
            f"<i>Iltimos kuting (~3-5 daqiqa)...</i>"
        )

        signals_found = 0
        skipped_429   = 0

        for tv_sym in config.TV_SYMBOLS:
            ccxt_symbol = tv_symbol_to_ccxt(tv_sym)
            if ccxt_symbol:
                if not btc_ok:
                    continue
                try:
                    hint = find_candidate_tv(tv_sym)
                    if not hint:
                        continue
                    snap = btc_snap if ccxt_symbol == "BTC/USDT" else snapshot(
                        ccxt_symbol, config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
                    sent = await _process_candidate(ccxt_symbol, snap, hint, btc_snap, perf, ctx_str)
                    if sent:
                        signals_found += 1
                except Exception as exc:
                    if "429" in str(exc):
                        skipped_429 += 1
                    else:
                        print(f"[scan-tv] error on {tv_sym['symbol']}:\n{traceback.format_exc()}")
            else:
                try:
                    hint = find_candidate_tv(tv_sym)
                    if not hint:
                        continue
                    sent = await _process_tv_noncrpyto(tv_sym, perf, f"{tv_sym['symbol']} • {tv_sym['screener'].upper()}")
                    if sent:
                        signals_found += 1
                except Exception as exc:
                    if "429" in str(exc):
                        skipped_429 += 1
                    else:
                        print(f"[scan-tv] error on {tv_sym['symbol']}:\n{traceback.format_exc()}")

        summary = f"✅ <b>Skanerlash tugadi</b>\n"
        if signals_found:
            summary += f"🎯 <b>{signals_found} ta signal topildi!</b>\n"
        else:
            summary += f"📊 Hozir kuchli setup topilmadi\n"
        if skipped_429:
            summary += f"⚠️ {skipped_429} ta symbol TradingView cheklovida o'tkazildi (20-30 daqiqada o'z-o'zidan ochiladi)"
        _notify(summary)
        return

    # ── Original ccxt screener path ───────────────────────────────────────
    if not btc_ok:
        _notify("📉 <b>BTC pasayish trendida</b> — hozir kuchli signal sharoiti yo'q.")
        return
    signals_found = 0
    for symbol in config.SYMBOLS:
        try:
            snap = btc_snap if symbol == "BTC/USDT" else snapshot(
                symbol, config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
            hint = screener.find_candidate(snap)
            if not hint:
                continue
            sent = await _process_candidate(symbol, snap, hint, btc_snap, perf, ctx_str)
            if sent:
                signals_found += 1
        except Exception:
            print(f"[scan] error on {symbol}:\n{traceback.format_exc()}")
    if not signals_found:
        _notify("📊 <b>Skanerlash tugadi</b> — hozir kuchli setup topilmadi.")


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
        await scan_once(notify_chat_id=chat_id)
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
    elif cmd in ("testsignal", "test"):
        sym = (arg or "EURUSD").upper()
        from .screener_tv import get_tv_analysis
        from .analyzer import analyze_tv_direct
        tv_map = {s["symbol"]: s for s in config.TV_SYMBOLS}
        tv_info = tv_map.get(sym)
        if not tv_info:
            telegram.send(f"❌ {sym} TV_SYMBOLS da topilmadi. Misol: /testsignal EURUSD", chat_id=chat_id)
            return
        telegram.send(f"🧪 <b>TEST MODE</b> — {sym} majburan tahlil qilinmoqda (screener o'tkazib yuborildi)...", chat_id=chat_id)
        try:
            e1h = get_tv_analysis(tv_info["symbol"], tv_info["exchange"], tv_info["screener"], "1h")
            e4h = get_tv_analysis(tv_info["symbol"], tv_info["exchange"], tv_info["screener"], "4h")
        except Exception as exc:
            telegram.send(f"❌ TradingView xato: {exc}", chat_id=chat_id)
            return
        sig = await analyze_tv_direct(sym, e1h, e4h, "TV")
        sig["symbol"] = sym
        cur_price = float(e1h.indicators.get("close", 0))
        signal_type = sig.get("signal", "none")
        score = sig.get("score", 0)
        reason = sig.get("reason", "")
        if signal_type == "long":
            from . import risk
            ok, why = risk.validate(sig, cur_price)
            if ok:
                sig_id = journal.add_signal(sig)
                telegram.send(telegram.format_signal(sig, sig_id, f"TEST • {sym}"), chat_id=chat_id)
                telegram.send(f"✅ Signal yaratildi #{sig_id}", chat_id=chat_id)
            else:
                telegram.send(
                    f"📊 <b>TEST {sym}</b> — Gemini LONG dedi lekin risk gate o'tmadi\n"
                    f"Sabab: {why}\nScore: {score}/10\n💡 {reason}", chat_id=chat_id)
        else:
            telegram.send(
                f"📊 <b>TEST {sym}</b> — Gemini signal bermadi\n"
                f"Signal: {signal_type} | Score: {score}/10\n💡 {reason}", chat_id=chat_id)
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
                    if action == "noop":
                        continue
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
                    elif action in ("coin", "tv"):
                        symbol = sid
                        cb_chat = cb.get("message", {}).get("chat", {}).get("id")
                        telegram.send(f"🔍 <b>{symbol}</b> tahlil qilinmoqda...", chat_id=cb_chat)
                        try:
                            if action == "coin" and "/" in symbol:
                                # Crypto via ccxt
                                btc_snap = snapshot("BTC/USDT", config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
                                snap = btc_snap if symbol == "BTC/USDT" else snapshot(symbol, config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
                                hint = screener.find_candidate(snap) or "A"
                                journal.bump_claude_calls()
                                sig = await analyze(snap, hint, btc_snap, journal.setup_performance(30))
                                ctx_str = market_context(btc_snap)
                                cur_price = last_price(symbol)
                                if sig.get("signal") == "long":
                                    ok, why = risk.validate(sig, cur_price)
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
                            else:
                                # Forex/Stocks via tradingview-ta
                                tv_info = _find_tv_info(symbol)
                                if not tv_info:
                                    telegram.send(f"❌ {symbol} — ma'lumot topilmadi", chat_id=cb_chat)
                                    continue
                                from .screener_tv import get_tv_analysis
                                from .analyzer import analyze_tv_direct
                                try:
                                    e1h = get_tv_analysis(tv_info["symbol"], tv_info["exchange"], tv_info["screener"], "1h")
                                    e4h = get_tv_analysis(tv_info["symbol"], tv_info["exchange"], tv_info["screener"], "4h")
                                except Exception as _tv_exc:
                                    if "429" in str(_tv_exc):
                                        telegram.send(f"⏳ <b>{symbol}</b> — TradingView so'rovlar cheklandi, 1-2 daqiqadan keyin qayta bosing.", chat_id=cb_chat)
                                    else:
                                        telegram.send(f"❌ <b>{symbol}</b> ma'lumot olishda xato: {str(_tv_exc)[:100]}", chat_id=cb_chat)
                                    continue
                                cur_price = float(e1h.indicators.get("close", 0))
                                journal.bump_claude_calls()
                                sig = await analyze_tv_direct(symbol, e1h, e4h, "TV", journal.setup_performance(30))
                                sig["symbol"] = symbol
                                if sig.get("signal") == "long":
                                    ok, why = risk.validate(sig, cur_price)
                                    if ok:
                                        sig_id = journal.add_signal(sig)
                                        telegram.send(telegram.format_signal(sig, sig_id, f"{symbol} • {tv_info['screener'].upper()}"), chat_id=cb_chat)
                                    else:
                                        telegram.send(f"📊 <b>{symbol}</b> — signal berilmadi\nSabab: {why}", chat_id=cb_chat)
                                else:
                                    telegram.send(f"📊 <b>{symbol}</b> — hozir kuchli setup yo'q\n💡 {sig.get('reason', '')}\nIshonch: {sig.get('score', 0)}/10", chat_id=cb_chat)
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


async def webhook_processor():
    """Process signals arriving from TradingView webhooks."""
    print("[webhook] processor started")
    while True:
        try:
            item = await _webhook_queue.get()
            symbol        = item["symbol"]
            exchange      = item["exchange"]
            screener_name = item["screener"]
            hint          = item.get("setup", "TV")

            tv_sym = {"symbol": symbol, "exchange": exchange, "screener": screener_name}
            ccxt_symbol = tv_symbol_to_ccxt(tv_sym)

            if ccxt_symbol:
                # Crypto path
                print(f"[webhook] processing {ccxt_symbol} setup={hint}")
                btc_snap = snapshot("BTC/USDT", config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
                snap = btc_snap if ccxt_symbol == "BTC/USDT" else snapshot(
                    ccxt_symbol, config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
                perf    = journal.setup_performance(30)
                ctx_str = market_context(btc_snap)
                await _process_candidate(ccxt_symbol, snap, hint, btc_snap, perf, ctx_str)
            else:
                # Forex/stocks/indices path
                print(f"[webhook] non-crypto signal: {exchange}:{symbol} setup={hint}")
                from .screener_tv import get_tv_analysis
                from .analyzer import analyze_tv_direct
                try:
                    e1h = get_tv_analysis(symbol, exchange, screener_name, "1h")
                    e4h = get_tv_analysis(symbol, exchange, screener_name, "4h")
                    current_price = float(e1h.indicators.get("close", 0))
                    if not current_price:
                        print(f"[webhook] {symbol} — no price data")
                        continue
                    perf = journal.setup_performance(30)
                    if journal.signals_today() >= config.MAX_SIGNALS_PER_DAY:
                        continue
                    if journal.claude_calls_today() >= config.MAX_CLAUDE_CALLS_PER_DAY:
                        continue
                    if journal.recent_signal_for(symbol, config.COOLDOWN_HOURS_PER_SYMBOL):
                        continue
                    journal.bump_claude_calls()
                    sig = await analyze_tv_direct(symbol, e1h, e4h, hint, perf)
                    sig["symbol"] = symbol
                    ok, why = risk.validate(sig, current_price)
                    if not ok:
                        print(f"[webhook] {symbol} rejected: {why}")
                        continue
                    sig_id = journal.add_signal(sig)
                    ctx_label = f"{symbol} • {screener_name.upper()} • TradingView"
                    telegram.send(telegram.format_signal(sig, sig_id, ctx_label))
                    print(f"[webhook] #{sig_id} {symbol} signal posted")
                except Exception:
                    print(f"[webhook] {symbol} error:\n{traceback.format_exc()}")
        except Exception:
            print(f"[webhook] processor error:\n{traceback.format_exc()}")
        finally:
            try:
                _webhook_queue.task_done()
            except Exception:
                pass


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
    screener_mode = "TradingView" if config.USE_TV_SCREENER else "ccxt"
    print(f"[boot] trading-signal-bot starting · trading={mode} · screener={screener_mode}")

    tasks = [scan_loop()]

    if config.TELEGRAM_BOT_TOKEN:
        tasks.append(telegram_poller())

    if config.WEBHOOK_ENABLED:
        _init_webhook_queue(_webhook_queue)
        tasks.append(run_webhook_server(port=config.WEBHOOK_PORT))
        tasks.append(webhook_processor())
        print(f"[boot] webhook server enabled on port {config.WEBHOOK_PORT}")

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
