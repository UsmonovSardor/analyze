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
from .data import snapshot, snapshot_yf, yf_last_and_range, market_open

# TradingView is only used by the webhook path now — scanning is ccxt + yfinance.
from .screener_tv import tv_symbol_to_ccxt

if config.WEBHOOK_ENABLED:
    from .webhook_server import run_webhook_server, init_queue as _init_webhook_queue

_webhook_queue: asyncio.Queue = asyncio.Queue()

# Rejected symbols aren't re-analyzed for a while — otherwise the same doomed
# candidates burn the daily Gemini budget every 30-minute scan.
_reject_cooldown: dict = {}
REJECT_COOLDOWN_SEC = 2 * 3600


# On-demand analysis timeframes: entry TF -> higher context TF
TF_CONTEXT = {"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w"}


def _recently_rejected(symbol: str) -> bool:
    return time.time() - _reject_cooldown.get(symbol, 0.0) < REJECT_COOLDOWN_SEC


def _mark_rejected(symbol: str):
    _reject_cooldown[symbol] = time.time()


def send_chart(symbol: str, snap: dict, sig: dict | None = None, chat_id=None):
    """Render and post an annotated chart; never let a chart error block a signal."""
    try:
        png = chart.render(symbol, snap, sig)
        tf = snap.get("tf_entry", "1h")
        cap = f"📈 <b>{symbol}</b> · {tf}"
        if sig and sig.get("signal") in ("long", "short"):
            cap = (f"🔻 <b>{symbol}</b> · SHORT · {tf}" if sig.get("signal") == "short"
                   else f"🟢 <b>{symbol}</b> · LONG · {tf}")
        telegram.send_photo(png, caption=cap, chat_id=chat_id)
    except Exception:
        print(f"[chart] error for {symbol}:\n{traceback.format_exc()}")


def post_signal(symbol: str, snap: dict, sig: dict, sig_id: int, ctx_str: str,
                kb: dict | None = None, chat_id=None):
    """Post a full signal as ONE Telegram message: chart photo + caption (plan +
    confluence + reasoning) + trade buttons. Falls back to text if the chart fails."""
    caption = telegram.format_signal(sig, sig_id, ctx_str)
    try:
        png = chart.render(symbol, snap, sig)
        mid = telegram.send_photo(png, caption=caption, reply_markup=kb, chat_id=chat_id)
        if mid is not None:
            return
    except Exception:
        print(f"[post_signal] chart error for {symbol}:\n{traceback.format_exc()}")
    # Chart failed (or caption too long for a photo) — send text so the signal still goes out.
    telegram.send(caption, reply_markup=kb, chat_id=chat_id)


def send_outcome_chart(row: dict, exit_price: float, r_val: float, event: str):
    """Post the closed-trade chart with the exit marked and WIN/LOSS banner."""
    try:
        info = config.noncrypto_info(row["symbol"])
        snap = (snapshot_yf(row["symbol"], info["yf"]) if info else
                snapshot(row["symbol"], config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES))
        sig = {"signal": row.get("side", "long"), "symbol": row["symbol"], "setup": row.get("setup"),
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


def trend_4h(snap: dict) -> str:
    """Classify the 4h trend from ccxt data — the SAME data Gemini analyzes.
    Returns 'up' | 'down' | 'mixed'."""
    ctx = snap["context_tf"]
    close, e50, e200 = _last(ctx, "close"), _last(ctx, "ema50"), _last(ctx, "ema200")
    if close > e200 and e50 > e200:
        return "up"
    if close < e200 and e50 < e200:
        return "down"
    return "mixed"


def align_hint(hint: dict, snap: dict) -> dict:
    """The TV screener's side can contradict the ccxt 4h trend that Gemini sees,
    and Gemini hard-rejects counter-trend trades — so those candidates always died.
    A long hint in a downtrend is usually a textbook short (pullback into
    resistance), and vice versa; flip the side so the candidate is with-trend."""
    if not isinstance(hint, dict):
        return hint
    trend = trend_4h(snap)
    side = hint.get("side", "long")
    if trend == "down" and side == "long" and config.ALLOW_SHORTS:
        print(f"[align] {snap['symbol']}: 4h trend down — long hint flipped to SHORT")
        return {**hint, "side": "short"}
    if trend == "up" and side == "short":
        print(f"[align] {snap['symbol']}: 4h trend up — short hint flipped to LONG")
        return {**hint, "side": "long"}
    return hint


def market_context(btc_snap) -> str:
    """One-line human-readable market regime for the report header."""
    ctx = btc_snap["context_tf"]
    price, ema200 = _last(ctx, "close"), _last(ctx, "ema200")
    trend = "ko'tarilish 📈" if price > ema200 else "pasayish 📉"
    rsi = _last(btc_snap["entry_tf"], "rsi")
    return f"BTC {trend} (4h) · BTC RSI {rsi:.0f}"


async def _process_candidate(symbol: str, snap: dict, hint: str,
                             btc_snap: dict, perf: dict, ctx_str: str,
                             cur_price: float | None = None):
    """Shared logic: run Claude → risk → Telegram for one candidate.
    cur_price: pass for non-crypto instruments (no Binance ticker for them)."""
    if journal.signals_today() >= config.MAX_SIGNALS_PER_DAY:
        print("[scan] daily signal cap reached")
        return False
    if len(journal.open_signals()) >= config.MAX_OPEN_SIGNALS:
        print("[scan] max open signals reached")
        return False
    if journal.recent_signal_for(symbol, config.COOLDOWN_HOURS_PER_SYMBOL):
        return False
    if _recently_rejected(symbol):
        return False
    if journal.claude_calls_today() >= config.MAX_CLAUDE_CALLS_PER_DAY:
        print("[scan] Claude daily call budget exhausted")
        return False
    # Correlation guard: alts move together — N same-side crypto signals are one
    # correlated bet, not N independent trades.
    if "/" in symbol and isinstance(hint, dict):
        side = hint.get("side", "long")
        same = [r for r in journal.open_signals()
                if "/" in r["symbol"] and r.get("side") == side]
        if len(same) >= config.MAX_SAME_SIDE_CRYPTO:
            print(f"[scan] {symbol}: {len(same)} open crypto {side}s — correlation guard")
            return False

    print(f"[scan] candidate {symbol} setup {hint} -> Claude")
    journal.bump_claude_calls()
    sig = await analyze(snap, hint, btc_snap, perf)

    price = cur_price if cur_price is not None else last_price(symbol)
    ok, why = risk.validate(sig, price)
    if not ok:
        print(f"[risk] {symbol} rejected: {why}")
        _mark_rejected(symbol)
        return False

    sig_id = journal.add_signal(sig)
    is_crypto = "/" in symbol
    can_auto = is_crypto and config.can_autotrade_side(sig.get("signal", "long"))
    kb = (telegram.execute_keyboard(sig_id, allow_auto=can_auto)
          if is_crypto and config.trading_enabled() else None)
    post_signal(symbol, snap, sig, sig_id, ctx_str, kb=kb)   # grafik + reja + tugmalar = BITTA xabar
    if can_auto and config.TRADING_MODE == "auto":
        _try_execute(sig_id)
    print(f"[signal] #{sig_id} {symbol} posted")
    return True


async def _tv_analysis_async(symbol: str, exchange: str, screener: str, tf: str):
    """Non-blocking wrapper for get_tv_analysis (time.sleep inside — runs in thread)."""
    from .screener_tv import get_tv_analysis
    return await asyncio.to_thread(get_tv_analysis, symbol, exchange, screener, tf)


async def scan_once(notify_chat_id=None):
    """Unified scan: crypto via ccxt (fast, no rate limits) + forex/gold/stocks via
    Yahoo Finance. One data source per instrument = the screener sees exactly what
    Gemini sees, so hints are never counter-trend."""
    def _notify(msg: str):
        if notify_chat_id:
            telegram.send(msg, chat_id=notify_chat_id)

    btc_snap = snapshot("BTC/USDT", config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
    perf    = journal.setup_performance(30)
    ctx_str = market_context(btc_snap)
    btc_ok  = screener.btc_context_ok(btc_snap)
    btc_status = "📈 ko'tarilish" if btc_ok else "📉 pasayish (faqat SHORT)"

    open_nc = [i for i in config.NONCRYPTO_SYMBOLS if market_open(i["kind"])]
    _notify(
        f"🔍 <b>Skanerlash boshlandi</b>\n"
        f"BTC: {btc_status}\n"
        f"✅ Crypto: {len(config.SYMBOLS)} ta\n"
        f"✅ Forex/Oltin/Aksiya: {len(open_nc)} ta (bozor ochiq)\n"
        f"<i>~1-2 daqiqa...</i>"
    )

    signals_found = errors = 0

    # ── Crypto (ccxt/Binance) ─────────────────────────────────────────────
    for symbol in config.SYMBOLS:
        try:
            snap = btc_snap if symbol == "BTC/USDT" else snapshot(
                symbol, config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
            hint = screener.find_candidate(snap)
            if not hint:
                continue
            # When BTC 4h is bearish, block crypto LONGS but still allow SHORTS.
            if not btc_ok and hint.get("side") == "long":
                continue
            if await _process_candidate(symbol, snap, hint, btc_snap, perf,
                                        f"{symbol} • CRYPTO • {config.ENTRY_TF}"):
                signals_found += 1
        except Exception:
            errors += 1
            print(f"[scan] error on {symbol}:\n{traceback.format_exc()}")

    # ── Forex / gold / stocks (Yahoo Finance) ─────────────────────────────
    for inst in open_nc:
        sym = inst["symbol"]
        try:
            snap = await asyncio.to_thread(snapshot_yf, sym, inst["yf"])
            hint = screener.find_candidate(snap)
            if not hint:
                continue
            cur = float(snap["entry_tf"]["close"].iloc[-1])
            label = f"{sym} • {inst['kind'].upper()}"
            if await _process_candidate(sym, snap, hint, btc_snap, perf, label, cur_price=cur):
                signals_found += 1
        except Exception:
            errors += 1
            print(f"[scan] error on {sym}:\n{traceback.format_exc()}")

    print(f"[scan] done: {signals_found} signal(s), {errors} error(s)")
    summary = "✅ <b>Skanerlash tugadi</b>\n"
    summary += (f"🎯 <b>{signals_found} ta signal topildi!</b>" if signals_found
                else "📊 Hozir kuchli setup topilmadi")
    _notify(summary)


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
    telegram.send(telegram.format_trade_filled(
        sig_id, sig["symbol"], res["qty"], res["fill"], res["oco"],
        side=res.get("side", sig.get("side", "long")), leverage=res.get("leverage")))
    if res.get("warn"):
        telegram.send(f"⚠️ #{sig_id}: {res['warn']}")
    return "ok"


def realized_r(row: dict, exit_price: float) -> float:
    """Weighted result in R given partial exits 40/40/20 and final exit price.
    Direction-aware: profit moves opposite ways for long vs short."""
    e, sl = row["entry"], row["stop_loss"]
    sign = -1.0 if row.get("side") == "short" else 1.0
    r = abs(e - sl)
    if r == 0:
        return 0.0
    parts = 0.0
    if row["status"] in ("tp1", "tp2"):
        parts += 0.4 * sign * (row["tp1"] - e) / r
    if row["status"] == "tp2":
        parts += 0.4 * sign * (row["tp2"] - e) / r
    remaining = {"open": 1.0, "tp1": 0.6, "tp2": 0.2}.get(row["status"], 1.0)
    return parts + remaining * sign * (exit_price - e) / r


def check_outcomes():
    for row in journal.open_signals():
        try:
            short = row.get("side") == "short"
            info = config.noncrypto_info(row["symbol"])
            if info:
                if not market_open(info["kind"]):
                    continue  # market closed — prices are stale, skip this cycle
                price_now, hi, lo = yf_last_and_range(info["yf"])
            else:
                price_now = last_price(row["symbol"])
                hi = lo = price_now
                for c in _px.fetch_ohlcv(row["symbol"], timeframe="5m", limit=3):
                    hi, lo = max(hi, c[2]), min(lo, c[3])

            # After TP1/TP2 the stop trails to breakeven (entry).
            effective_sl = row["entry"] if row["status"] in ("tp1", "tp2") else row["stop_loss"]

            if short:
                stop_hit = hi >= effective_sl          # price rose into the stop
                tp_reached = lambda lvl: lo <= lvl     # price fell to a target
            else:
                stop_hit = lo <= effective_sl          # price fell into the stop
                tp_reached = lambda lvl: hi >= lvl      # price rose to a target

            if stop_hit:
                event = "breakeven" if row["status"] in ("tp1", "tp2") else "stopped"
                r_val = realized_r(row, effective_sl)
                journal.update_status(row["id"], event, r_val, close=True)
                telegram.send(telegram.format_outcome(row, event, r_val))
                send_outcome_chart(row, effective_sl, r_val, event)
            elif tp_reached(row["tp3"]) and row["status"] == "tp2":
                r_val = realized_r(row, row["tp3"])
                journal.update_status(row["id"], "tp3", r_val, close=True)
                telegram.send(telegram.format_outcome(row, "tp3", r_val))
                send_outcome_chart(row, row["tp3"], r_val, "tp3")
            elif tp_reached(row["tp2"]) and row["status"] == "tp1":
                journal.update_status(row["id"], "tp2")
                telegram.send(telegram.format_outcome(row, "tp2"))
            elif tp_reached(row["tp1"]) and row["status"] == "open":
                journal.update_status(row["id"], "tp1")
                telegram.send(telegram.format_outcome(row, "tp1"))
        except Exception:
            print(f"[outcome] error on #{row['id']}:\n{traceback.format_exc()}")


def _resolve_symbol(raw: str):
    """Map user input to ('nc', info_dict) for forex/gold/stocks or ('crypto', 'BTC/USDT')."""
    s = raw.strip().upper().replace("-", "").replace("/", "")
    info = config.noncrypto_info(s)
    if info:
        return "nc", info
    base = s[:-4] if s.endswith(("USDT", "USDC")) else s
    return "crypto", f"{base}/USDT"


async def analyze_on_demand(symbol_raw: str, chat_id=None, tf: str = "1h") -> str:
    """Full Gemini analysis + chart for any instrument, on the chosen timeframe."""
    if journal.claude_calls_today() >= config.MAX_CLAUDE_CALLS_PER_DAY:
        return "⏳ Bugungi tahlil limiti tugadi, ertaga urinib ko'ring."

    tf = tf if tf in TF_CONTEXT else "1h"
    ctx_tf = TF_CONTEXT[tf]
    kind, target = _resolve_symbol(symbol_raw)
    symbol = target["symbol"] if kind == "nc" else target

    try:
        btc_snap = snapshot("BTC/USDT", config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
        if kind == "nc":
            if not market_open(target["kind"]):
                return (f"🕐 <b>{symbol}</b> — bozor hozir yopiq "
                        f"({'aksiya sessiyasi 18:30-01:00 Tashkent' if target['kind'] == 'stock' else 'forex dam olish kunlari yopiq'}).")
            snap = await asyncio.to_thread(snapshot_yf, symbol, target["yf"],
                                           config.CANDLES, tf, ctx_tf)
            ctx_str = f"{symbol} • {target['kind'].upper()} • {tf}"
            cur = float(snap["entry_tf"]["close"].iloc[-1])
        else:
            snap = (btc_snap if symbol == "BTC/USDT" and tf == config.ENTRY_TF
                    else snapshot(symbol, tf, ctx_tf, config.CANDLES))
            ctx_str = f"{symbol} • CRYPTO • {tf}"
            cur = last_price(symbol)
    except Exception as exc:
        return f"❌ <b>{symbol}</b> ma'lumot olishda xato: {str(exc)[:120]}"

    hint = screener.find_candidate(snap)
    if not hint:
        default_side = "short" if (trend_4h(snap) == "down" and config.ALLOW_SHORTS) else "long"
        hint = {"setup": "A", "side": default_side}
    journal.bump_claude_calls()
    sig = await analyze(snap, hint, btc_snap, journal.setup_performance(30))

    if sig.get("signal") in ("long", "short"):
        ok, why = risk.validate(sig, cur)
        if ok:
            sig_id = journal.add_signal(sig)
            is_crypto = kind == "crypto"
            can_auto = is_crypto and config.can_autotrade_side(sig.get("signal", "long"))
            kb = (telegram.execute_keyboard(sig_id, allow_auto=can_auto)
                  if is_crypto and config.trading_enabled() else None)
            post_signal(symbol, snap, sig, sig_id, ctx_str, kb=kb, chat_id=chat_id)
            return ""  # already sent as a full signal + chart
        send_chart(symbol, snap, None, chat_id=chat_id)
        return (f"📊 <b>{symbol}</b> ({tf}) — tahlil qilindi, lekin signal BERILMADI\n"
                f"Sabab: {why}")
    send_chart(symbol, snap, None, chat_id=chat_id)
    return (f"📊 <b>{symbol}</b> ({tf}) — hozir kuchli setup yo'q\n"
            f"💡 {sig.get('reason', 'kriteriylarga mos kelmadi')}\n"
            f"Ishonch: {sig.get('score', 0)}/10")


def _skills_menu_text() -> str:
    from . import skills_store
    n_st, n_cu = len(skills_store.strategies()), len(skills_store.list_custom())
    return (f"📚 <b>Bilimlar bazasi</b>\n"
            f"🎯 {n_st} ta strategiya · ✍️ {n_cu} ta sizniki\n"
            f"Bo'limni tanlang:")


def _send_skills_menu(chat_id=None):
    from . import skills_store
    telegram.send(_skills_menu_text(),
                  reply_markup=telegram.skills_menu_keyboard(
                      len(skills_store.strategies()), len(skills_store.list_custom())),
                  chat_id=chat_id)


ADDSKILL_HELP = (
    "➕ <b>Yangi strategiya qo'shish</b>\n\n"
    "Bitta xabarda quyidagicha yuboring:\n\n"
    "<code>/addskill Strategiya nomi\n"
    "Qoidalar: qachon kirish, qachon kirmaslik,\n"
    "stop-loss qayerda, take-profit qayerda,\n"
    "qaysi timeframe va bozorlar uchun.</code>\n\n"
    "Birinchi qator — nom, qolgani — qoidalar (kamida 30 belgi).\n"
    "Strategiya darhol AI tahliliga qo'shiladi va signallarda "
    "<b>strategy_name</b> sifatida chiqishi mumkin.\n"
    "O'chirish: 📚 Skillar → ✍️ Mening strategiyalarim → 🗑"
)


async def _handle_addskill(text: str, chat_id=None):
    from . import skills_store
    from .analyzer import reload_skill
    # strip everything up to and including the /addskill token
    idx = text.lower().find("/addskill")
    payload = text[idx + len("/addskill"):].strip()
    lines = [l for l in payload.splitlines()]
    name = (lines[0].strip() if lines else "")[:60]
    body = "\n".join(lines[1:]).strip()
    if not name or len(body) < 30:
        telegram.send(ADDSKILL_HELP, chat_id=chat_id)
        return
    replaced = skills_store.add_custom(name, body)
    reload_skill()
    verb = "yangilandi ♻️" if replaced else "qo'shildi ✅"
    telegram.send(
        f"✅ <b>{telegram._esc(name)}</b> strategiyasi {verb}\n"
        f"AI endi tahlillarda undan foydalanadi.\n"
        f"Jami sizning strategiyalaringiz: {len(skills_store.list_custom())} ta",
        chat_id=chat_id)


async def handle_command(text: str, chat_id=None):
    # tolerate emoji/text before the command (reply-keyboard buttons send "📊 /analyze BTC")
    tokens = text.strip().split()
    idx = next((i for i, t in enumerate(tokens) if t.startswith("/")), None)
    if idx is None:
        return
    cmd = tokens[idx].lower().lstrip("/").split("@")[0]
    arg = tokens[idx + 1] if len(tokens) > idx + 1 else None

    if cmd == "addskill":
        await _handle_addskill(text, chat_id=chat_id)
        return
    if cmd in ("skills", "skillar", "strategiyalar", "s"):
        _send_skills_menu(chat_id=chat_id)
        return
    if cmd in ("refresh", "yangilash", "r"):
        asyncio.create_task(scan_once(notify_chat_id=chat_id))
    elif cmd in ("coins", "valyutalar", "c"):
        telegram.send("🪙 <b>Valyutani tanlang</b> — tahlil uchun bosing:",
                      reply_markup=telegram.coins_keyboard(), chat_id=chat_id)
    elif cmd in ("analyze", "analiz", "a"):
        if not arg:
            telegram.send("Foydalanish: <code>/analyze BTC</code> yoki <code>/analyze EURUSD 15m</code>",
                          reply_markup=telegram.main_keyboard(), chat_id=chat_id)
            return
        tf_arg = tokens[idx + 2].lower() if len(tokens) > idx + 2 else None
        if tf_arg in TF_CONTEXT:
            telegram.send(f"🔍 <b>{arg.upper()}</b> ({tf_arg}) tahlil qilinmoqda...", chat_id=chat_id)
            msg = await analyze_on_demand(arg, chat_id=chat_id, tf=tf_arg)
            if msg:
                telegram.send(msg, chat_id=chat_id)
        else:
            telegram.send(f"⏱ <b>{arg.upper()}</b> — qaysi vaqt oralig'ida tahlil qilay?",
                          reply_markup=telegram.tf_keyboard(arg.upper()), chat_id=chat_id)
    elif cmd in ("balance", "balans", "portfel"):
        if not config.trading_enabled():
            telegram.send(
                "💼 <b>Binance portfel</b>\n\n"
                "⚠️ Binance API key sozlanmagan (signal-only rejim).\n"
                "Avto/qo'lda savdo uchun <code>BINANCE_API_KEY</code> va "
                "<code>BINANCE_API_SECRET</code> qo'shing (Futures ruxsati bilan).",
                chat_id=chat_id)
            return
        from . import exchange_trade
        data = await asyncio.to_thread(exchange_trade.portfolio)
        telegram.send(telegram.format_portfolio(data), chat_id=chat_id)
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
            e1h = await _tv_analysis_async(tv_info["symbol"], tv_info["exchange"], tv_info["screener"], "1h")
            e4h = await _tv_analysis_async(tv_info["symbol"], tv_info["exchange"], tv_info["screener"], "4h")
        except Exception as exc:
            telegram.send(f"❌ TradingView xato: {exc}", chat_id=chat_id)
            return
        sig = await analyze_tv_direct(sym, e1h, e4h, "TV")
        sig["symbol"] = sym
        cur_price = float(e1h.indicators.get("close", 0))
        signal_type = sig.get("signal", "none")
        score = sig.get("score", 0)
        reason = sig.get("reason", "")
        if signal_type in ("long", "short"):
            from . import risk
            ok, why = risk.validate(sig, cur_price)
            if ok:
                sig_id = journal.add_signal(sig)
                telegram.send(telegram.format_signal(sig, sig_id, f"TEST • {sym}"), chat_id=chat_id)
                telegram.send(f"✅ Signal yaratildi #{sig_id}", chat_id=chat_id)
            else:
                telegram.send(
                    f"📊 <b>TEST {sym}</b> — Gemini {signal_type.upper()} dedi lekin risk gate o'tmadi\n"
                    f"Sabab: {why}\nScore: {score}/10\n💡 {reason}", chat_id=chat_id)
        else:
            telegram.send(
                f"📊 <b>TEST {sym}</b> — Gemini signal bermadi\n"
                f"Signal: {signal_type} | Score: {score}/10\n💡 {reason}", chat_id=chat_id)
    elif cmd in ("help", "start", "yordam", "menu"):
        telegram.send(telegram.format_help(), reply_markup=telegram.main_keyboard(), chat_id=chat_id)


def _handle_skills_callback(sid: str, chat_id):
    """sk:* inline-button router: menu, docs (paged), strategy list, custom CRUD."""
    from . import skills_store
    from .analyzer import reload_skill
    part = sid.split("|")
    what = part[0]

    if what == "menu":
        _send_skills_menu(chat_id=chat_id)

    elif what == "list":
        page = int(part[1]) if len(part) > 1 else 0
        names = [n for n, _ in skills_store.strategies()]
        telegram.send(f"🎯 <b>Strategiyalar</b> ({len(names)} ta) — o'qish uchun bosing:",
                      reply_markup=telegram.strategies_list_keyboard(names, page),
                      chat_id=chat_id)

    elif what == "st":
        idx = int(part[1])
        items = skills_store.strategies()
        if 0 <= idx < len(items):
            name, body = items[idx]
            if len(body) > skills_store.PAGE_CHARS:
                body = body[:skills_store.PAGE_CHARS] + "\n… (qisqartirildi)"
            telegram.send(f"🎯 <b>{telegram._esc(name)}</b>\n\n<pre>{telegram._esc(body)}</pre>",
                          reply_markup={"inline_keyboard": [[
                              {"text": "🔙 Strategiyalar", "callback_data": f"sk:list|{idx // 10}"}]]},
                          chat_id=chat_id)

    elif what == "doc":
        di, page = int(part[1]), int(part[2]) if len(part) > 2 else 0
        label, pages = skills_store.doc_pages(di)
        page = max(0, min(page, len(pages) - 1))
        telegram.send(f"{label}\n\n<pre>{telegram._esc(pages[page])}</pre>",
                      reply_markup=telegram.doc_nav_keyboard(di, page, len(pages)),
                      chat_id=chat_id)

    elif what == "cust":
        items = skills_store.list_custom()
        if not items:
            telegram.send("✍️ Hozircha o'z strategiyangiz yo'q.\n" + ADDSKILL_HELP,
                          chat_id=chat_id)
        else:
            lines = [f"{i+1}. <b>{telegram._esc(n)}</b> — {telegram._esc(b[:80])}…"
                     for i, (n, b) in enumerate(items)]
            telegram.send("✍️ <b>Mening strategiyalarim</b>\n\n" + "\n".join(lines) +
                          "\n\nO'chirish uchun 🗑 tugmasini bosing:",
                          reply_markup=telegram.custom_list_keyboard([n for n, _ in items]),
                          chat_id=chat_id)

    elif what == "cdel":
        name = skills_store.remove_custom(int(part[1]))
        reload_skill()
        if name:
            telegram.send(f"🗑 <b>{telegram._esc(name)}</b> o'chirildi.", chat_id=chat_id)
        _send_skills_menu(chat_id=chat_id)

    elif what == "add":
        telegram.send(ADDSKILL_HELP, chat_id=chat_id)


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
                    elif action == "sk":
                        cb_chat = cb.get("message", {}).get("chat", {}).get("id")
                        try:
                            _handle_skills_callback(sid, cb_chat)
                        except Exception:
                            print(f"[skills-cb] error {sid}:\n{traceback.format_exc()}")
                    elif action in ("coin", "tv"):
                        symbol = sid
                        cb_chat = cb.get("message", {}).get("chat", {}).get("id")
                        telegram.send(f"⏱ <b>{symbol}</b> — qaysi vaqt oralig'ida tahlil qilay?",
                                      reply_markup=telegram.tf_keyboard(symbol), chat_id=cb_chat)
                    elif action == "tf":
                        symbol, _, tf = sid.partition("|")
                        cb_chat = cb.get("message", {}).get("chat", {}).get("id")
                        telegram.send(f"🔍 <b>{symbol}</b> ({tf}) tahlil qilinmoqda...", chat_id=cb_chat)
                        try:
                            msg = await analyze_on_demand(symbol, chat_id=cb_chat, tf=tf)
                            if msg:
                                telegram.send(msg, chat_id=cb_chat)
                        except Exception:
                            telegram.send(f"❌ <b>{symbol}</b> tahlilida xato — qayta urinib ko'ring.", chat_id=cb_chat)
                            print(f"[tf-cb] error {symbol}:\n{traceback.format_exc()}")
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
            hint          = {"setup": item.get("setup", "TV"), "side": item.get("side", "long")}

            tv_sym = {"symbol": symbol, "exchange": exchange, "screener": screener_name}
            ccxt_symbol = tv_symbol_to_ccxt(tv_sym)

            if ccxt_symbol:
                # Crypto path
                print(f"[webhook] processing {ccxt_symbol} setup={hint}")
                btc_snap = snapshot("BTC/USDT", config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
                snap = btc_snap if ccxt_symbol == "BTC/USDT" else snapshot(
                    ccxt_symbol, config.ENTRY_TF, config.CONTEXT_TF, config.CANDLES)
                hint    = align_hint(hint, snap)
                perf    = journal.setup_performance(30)
                ctx_str = market_context(btc_snap)
                await _process_candidate(ccxt_symbol, snap, hint, btc_snap, perf, ctx_str)
            else:
                # Forex/stocks/indices path
                print(f"[webhook] non-crypto signal: {exchange}:{symbol} setup={hint}")
                from .screener_tv import get_tv_analysis
                from .analyzer import analyze_tv_direct
                try:
                    e1h = await _tv_analysis_async(symbol, exchange, screener_name, "1h")
                    e4h = await _tv_analysis_async(symbol, exchange, screener_name, "4h")
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


def _daily_digest() -> str:
    n_sig  = journal.signals_today()
    n_ai   = journal.claude_calls_today()
    n_open = len(journal.open_signals())
    header = "📬 <b>Kunlik hisobot</b>\n"
    body = (f"🎯 Bugun: <b>{n_sig} ta signal</b>\n"
            f"🧠 AI tahlillar: {n_ai}/{config.MAX_CLAUDE_CALLS_PER_DAY}\n"
            f"📂 Ochiq signallar: {n_open}\n")
    if n_sig == 0:
        body += "<i>Bugun kuchli setup bo'lmadi — bot ishlayapti, sifat filtri qattiq turibdi.</i>"
    return header + body


async def scan_loop():
    from datetime import datetime, timezone
    last_scan = last_outcome = 0.0
    last_weekly = time.time()
    last_digest_day = None
    last_err_alert = 0.0
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
            utc = datetime.now(timezone.utc)
            if utc.hour >= config.DIGEST_HOUR_UTC and last_digest_day != utc.date():
                last_digest_day = utc.date()
                telegram.send(_daily_digest())
        except Exception:
            print(f"[loop] error:\n{traceback.format_exc()}")
            # Alert the chat about repeated failures, at most once per 2 hours.
            if time.time() - last_err_alert > 2 * 3600:
                last_err_alert = time.time()
                try:
                    telegram.send("⚠️ <b>Bot xatosi</b> — skanerlash siklida muammo, "
                                  "loglarni tekshiring. Bot avtomatik davom etadi.")
                except Exception:
                    pass
        await asyncio.sleep(30)


async def main():
    mode = config.TRADING_MODE if config.trading_enabled() else "off (signals only)"
    screener_mode = "ccxt+yfinance (unified)"
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
