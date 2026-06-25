"""Telegram delivery (plain Bot API via requests — no framework needed)."""
import json

import requests

from . import config
from .strategy_meta import render_scorecard, strategy

API = "https://api.telegram.org/bot{token}/{method}"


def _call(method: str, payload: dict, timeout: int = 15):
    if not config.TELEGRAM_BOT_TOKEN:
        print(f"[telegram] not configured ({method}):\n" + payload.get("text", ""))
        return None
    try:
        r = requests.post(
            API.format(token=config.TELEGRAM_BOT_TOKEN, method=method),
            json=payload, timeout=timeout,
        )
        if not r.ok:
            print(f"[telegram] {method} failed: {r.status_code} {r.text[:200]}")
        return r.json() if r.ok else None
    except requests.RequestException as exc:
        print(f"[telegram] {method} network error: {exc}")
        return None


def send(text: str, reply_markup: dict | None = None, chat_id=None) -> int | None:
    payload = {"chat_id": chat_id or config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    res = _call("sendMessage", payload)
    return res["result"]["message_id"] if res and res.get("ok") else None


def send_photo(png: bytes, caption: str = "", reply_markup: dict | None = None, chat_id=None) -> int | None:
    if not config.TELEGRAM_BOT_TOKEN:
        print(f"[telegram] not configured (photo):\n{caption[:200]}")
        return None
    data = {"chat_id": chat_id or config.TELEGRAM_CHAT_ID, "caption": caption[:1024], "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(API.format(token=config.TELEGRAM_BOT_TOKEN, method="sendPhoto"),
                          data=data, files={"photo": ("chart.png", png, "image/png")}, timeout=30)
        if not r.ok:
            print(f"[telegram] sendPhoto failed: {r.status_code} {r.text[:200]}")
            return None
        return r.json()["result"]["message_id"]
    except requests.RequestException as exc:
        print(f"[telegram] sendPhoto network error: {exc}")
        return None


def edit(message_id: int, text: str, reply_markup: dict | None = None):
    payload = {"chat_id": config.TELEGRAM_CHAT_ID, "message_id": message_id,
               "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    payload["reply_markup"] = reply_markup or {"inline_keyboard": []}
    _call("editMessageText", payload)


def answer_callback(callback_id: str, text: str = ""):
    _call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})


def get_updates(offset: int, timeout: int = 20) -> list[dict]:
    # HTTP read timeout must exceed the server-side long-poll timeout
    res = _call("getUpdates", {"offset": offset, "timeout": timeout,
                               "allowed_updates": ["callback_query", "message"]},
                timeout=timeout + 10)
    return res["result"] if res and res.get("ok") else []


def fmt_price(p: float) -> str:
    p = float(p)
    if p >= 100:
        return f"{p:,.2f}"
    if p >= 1:
        return f"{p:.4f}".rstrip("0").rstrip(".")
    return f"{p:.6f}".rstrip("0").rstrip(".")


def _pct(a: float, b: float) -> str:
    return f"{(a / b - 1) * 100:+.2f}%"


def main_keyboard() -> dict:
    """Persistent tap-to-send command buttons shown above the input field."""
    return {
        "keyboard": [
            ["🪙 /coins", "🔄 /refresh"],
            ["📈 /stats", "📂 /open"],
            ["💼 /balance"],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def coins_keyboard() -> dict:
    """Inline keyboard with crypto, forex, stocks — tap to analyze on demand."""
    from . import config
    buttons, row = [], []

    buttons.append([{"text": "🪙 ── CRYPTO ── 🪙", "callback_data": "noop"}])
    for sym in config.SYMBOLS:
        base = sym.split("/")[0]
        row.append({"text": base, "callback_data": f"coin:{sym}"})
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([{"text": "💱 ── FOREX / GOLD / OIL ── 💱", "callback_data": "noop"}])
    row = []
    for sym in config.FOREX_SYMBOLS:
        row.append({"text": sym["symbol"], "callback_data": f"tv:{sym['symbol']}"})
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([{"text": "📈 ── US STOCKS ── 📈", "callback_data": "noop"}])
    row = []
    for sym in config.STOCK_SYMBOLS:
        row.append({"text": sym["symbol"], "callback_data": f"tv:{sym['symbol']}"})
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    return {"inline_keyboard": buttons}


def execute_keyboard(sig_id: int, allow_auto: bool = True) -> dict:
    """Trade buttons. When allow_auto is False (e.g. a SHORT on a spot-only account)
    the auto button is hidden — only manual + watch are offered."""
    rows = []
    if allow_auto:
        rows.append([{"text": "🤖 Avto savdo", "callback_data": f"auto:{sig_id}"},
                     {"text": "✍️ Qo'lda savdo", "callback_data": f"manual:{sig_id}"}])
    else:
        rows.append([{"text": "✍️ Qo'lda savdo", "callback_data": f"manual:{sig_id}"}])
    rows.append([{"text": "👁️ Kuzatish (Test)", "callback_data": f"skip:{sig_id}"}])
    return {"inline_keyboard": rows}


def format_manual_plan(sig: dict, sig_id: int) -> str:
    """Copy-paste plan for the user to place the order themselves on Binance."""
    short = sig.get("signal") == "short" or sig.get("side") == "short"
    e, sl = float(sig["entry"]), float(sig["stop_loss"])
    if short:
        venue = "Binance Futures"
        step2 = f"2️⃣ <b>Limit SELL / Short</b> oching: <code>{fmt_price(e)}</code>"
    else:
        venue = "Binance Spot yoki Futures"
        step2 = f"2️⃣ <b>Limit BUY / Long</b> qo'ying: <code>{fmt_price(e)}</code>"
    return (
        f"✍️ <b>QO'LDA SAVDO rejasi</b> — #{sig_id} {sig['symbol']} "
        f"({'🔻 SHORT' if short else '🟢 LONG'})\n\n"
        f"1️⃣ {venue}'da <b>{sig['symbol']}</b> oching\n"
        f"{step2}\n"
        f"3️⃣ <b>TP / SL</b> sozlang:\n"
        f"   🛑 Stop-loss: <code>{fmt_price(sl)}</code>\n"
        f"   🎯 Take-profit (TP2): <code>{fmt_price(sig['tp2'])}</code>\n"
        f"4️⃣ Hajm: depozitning 1% riskiga moslang\n\n"
        f"📌 TP1 (<code>{fmt_price(sig['tp1'])}</code>) urilganda 40% oling va stop'ni "
        f"kirish narxiga (breakeven) ko'chiring.\n"
        f"Bot bu signal natijasini avtomatik kuzatib, sizga xabar beradi."
    )


def _conf_bar(score: int) -> str:
    """A thin 10-segment confidence bar, e.g. ▰▰▰▰▰▰▰▰▱▱."""
    score = max(0, min(10, int(round(score))))
    return "▰" * score + "▱" * (10 - score)


def format_signal(sig: dict, sig_id: int, market_ctx: str = "") -> str:
    meta = strategy(sig.get("setup", ""))
    short = sig.get("signal") == "short" or sig.get("side") == "short"
    e, sl = float(sig["entry"]), float(sig["stop_loss"])
    r = abs(e - sl)
    tp1, tp2, tp3 = float(sig["tp1"]), float(sig["tp2"]), float(sig["tp3"])
    score = int(round(float(sig.get("score", 0) or 0)))

    def rr(tp):
        return abs(tp - e) / r if r else 0.0

    def gain(tp):            # profit-side % move (always positive, direction-aware)
        return abs(tp - e) / e * 100

    loss_pct = abs(sl - e) / e * 100
    arrow = "🔻" if short else "🟢"
    direction = "SHORT" if short else "LONG"

    # Monospace, perfectly aligned trade plan (no emojis inside <pre> to keep columns straight)
    P = fmt_price
    plan = (
        f"{'Kirish':<7}{P(e):>13}\n"
        f"{'Stop':<7}{P(sl):>13}{'-'+format(loss_pct,'.2f')+'%':>10}{'-1.0R':>7}\n"
        f"{'─'*37}\n"
        f"{'TP1':<7}{P(tp1):>13}{'+'+format(gain(tp1),'.2f')+'%':>10}{'+'+format(rr(tp1),'.1f')+'R':>7}{'40%':>6}\n"
        f"{'TP2':<7}{P(tp2):>13}{'+'+format(gain(tp2),'.2f')+'%':>10}{'+'+format(rr(tp2),'.1f')+'R':>7}{'40%':>6}\n"
        f"{'TP3':<7}{P(tp3):>13}{'+'+format(gain(tp3),'.2f')+'%':>10}{'+'+format(rr(tp3),'.1f')+'R':>7}{'20%':>6}"
    )

    lines = [
        f"{arrow} <b>{direction}</b>  ·  <b>{sig['symbol']}</b>   <code>#{sig_id}</code>",
        f"<i>{meta['name']}</i>",
        f"Ishonch  <b>{score}/10</b>   {_conf_bar(score)}",
        "",
        "<b>📋 Savdo rejasi</b>",
        f"<pre>{plan}</pre>",
        "<b>📊 Confluence</b>",
        f"<pre>{render_scorecard(sig.get('scorecard', {}))}</pre>",
        "<b>💡 Asoslash</b>",
        f"<i>{sig.get('reasoning', '')}</i>",
    ]
    if market_ctx:
        lines += ["", f"🌐 {market_ctx}"]
    lines += [
        "",
        "⚖️ Risk: depozitning <b>1%</b>  ·  TP1 dan keyin SL → breakeven",
        "⚠️ <i>Bu moliyaviy maslahat emas</i>",
    ]
    return "\n".join(lines)


def format_outcome(row: dict, event: str, r_val: float | None = None) -> str:
    meta = strategy(row.get("setup", ""))
    label = {
        "tp1": "🎯 <b>TP1 urildi</b> — 40% olindi, SL endi breakeven'da",
        "tp2": "🎯 <b>TP2 urildi</b> — yana 40% olindi",
        "tp3": "✅ <b>TP3 urildi</b> — pozitsiya to'liq yopildi",
        "stopped": "🛑 <b>Stop-loss urildi</b>",
        "breakeven": "⚪ <b>Breakeven'da yopildi</b> — zarar yo'q",
    }[event]
    txt = f"{label}\n{meta['emoji']} #{row['id']} <b>{row['symbol']}</b> · {meta['name']}"
    if r_val is not None:
        emo = "🟢" if r_val > 0 else ("⚪" if abs(r_val) < 0.05 else "🔴")
        txt += f"\n{emo} Natija: <b>{r_val:+.2f}R</b>"
    return txt


def format_weekly(stats: dict) -> str:
    lines = [
        "📊 <b>HAFTALIK HISOBOT</b>",
        "",
        f"Yopilgan: <b>{stats['closed']}</b>  ·  Yutuq: <b>{stats['wins']}</b> ({stats['win_rate']}%)",
        f"Jami natija: <b>{stats['total_r']:+.2f}R</b>  ·  Ochiq: {stats['open']}",
    ]
    by = stats.get("by_setup", {})
    if by:
        lines += ["", "<b>Strategiya bo'yicha:</b>"]
        for setup, s in by.items():
            meta = strategy(setup)
            lines.append(f"{meta['emoji']} {meta['name']}: {s['wins']}/{s['closed']} "
                         f"({s['win_rate']}%) · {s['total_r']:+.2f}R")
    return "\n".join(lines)


def format_help() -> str:
    return (
        "👋 <b>Trading Analyst Bot</b>\n"
        "📊 AI-asosli ko'p bozorli signal tizimi (crypto · forex · oltin · aksiya)\n\n"
        "📌 <b>Imkoniyatlar:</b>\n"
        "• 24/7 avtomatik skanerlash (40+ instrument)\n"
        "• Gemini AI bilan chuqur tahlil + grafik\n"
        "• 🟢 LONG va 🔻 SHORT — har ikki yo'nalish\n"
        "• Entry / TP1-3 / Stop-loss aniq belgilangan\n"
        "• Avto va qo'lda savdo (Binance Futures)\n"
        "• Signal natijasini grafik bilan avtomatik kuzatish\n\n"
        "🔘 <b>Buyruqlar:</b>\n"
        "🪙 <code>/coins</code> — instrument tanlang → AI tahlil + grafik\n"
        "🔍 <code>/analyze BTC</code> yoki <code>/analyze EURUSD</code> — istalganini tahlil\n"
        "🔄 <code>/refresh</code> — bozorni hozir skanerlash\n"
        "📈 <code>/stats</code> — haftalik statistika\n"
        "📂 <code>/open</code> — ochiq signallar\n"
        "💼 <code>/balance</code> — Binance portfel holati\n\n"
        "Pastdagi tugmalardan foydalaning 👇\n"
        "⚠️ <i>Bu moliyaviy maslahat emas</i>"
    )


def format_portfolio(data: dict) -> str:
    if not data.get("ok"):
        return f"❌ {data.get('error', 'balansni olishda xato')}"
    holdings = data["holdings"]
    if not holdings:
        return "💼 <b>Binance Spot portfel</b>\n\nPortfel bo'sh (0 USDT).\nSavdo uchun avval depozit qiling."
    lines = [f"💼 <b>Binance Spot portfel</b>", f"Jami: <b>${data['total_usd']:,.2f}</b>", ""]
    for h in holdings:
        amt = f"{h['amount']:.6f}".rstrip("0").rstrip(".")
        lines.append(f"• <b>{h['asset']}</b>: {amt}  (≈ ${h['usd']:,.2f})")
    return "\n".join(lines)


def format_open(rows: list) -> str:
    if not rows:
        return "📭 Hozir ochiq signal yo'q."
    lines = ["📂 <b>Ochiq signallar:</b>", ""]
    for r in rows:
        meta = strategy(r.get("setup", ""))
        lines.append(f"#{r['id']} {meta['emoji']} <b>{r['symbol']}</b> · {meta['name']} · "
                     f"holat: {r['status']} · entry {fmt_price(r['entry'])}")
    return "\n".join(lines)


def format_trade_filled(sig_id: int, symbol: str, qty: float, entry: float, oco: bool,
                        side: str = "long", leverage: int | None = None) -> str:
    verb = "Short ochildi" if side == "short" else "Long ochildi"
    lev = f" · {leverage}x" if leverage else ""
    txt = (f"💰 <b>Savdo bajarildi</b> #{sig_id} {symbol} "
           f"({'🔻 SHORT' if side == 'short' else '🟢 LONG'}{lev})\n"
           f"{verb}: <code>{qty}</code> @ ~<code>{fmt_price(entry)}</code>")
    txt += "\n🛡 TP/SL order qo'yildi (Binance serverida)" if oco else "\n⚠️ TP/SL qo'yilmadi — qo'lda nazorat qiling"
    return txt
