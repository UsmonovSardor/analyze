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
    """Inline keyboard with all watchlist symbols — tap to analyze on demand."""
    from . import config
    buttons, row = [], []
    for sym in config.SYMBOLS:
        base = sym.split("/")[0]
        row.append({"text": base, "callback_data": f"coin:{sym}"})
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return {"inline_keyboard": buttons}


def execute_keyboard(sig_id: int) -> dict:
    return {"inline_keyboard": [
        [{"text": "🤖 Avto savdo", "callback_data": f"auto:{sig_id}"},
         {"text": "✍️ Qo'lda savdo", "callback_data": f"manual:{sig_id}"}],
        [{"text": "👁️ Kuzatish (Test)", "callback_data": f"skip:{sig_id}"}],
    ]}


def format_manual_plan(sig: dict, sig_id: int) -> str:
    """Copy-paste plan for the user to place the order themselves on Binance."""
    e, sl = float(sig["entry"]), float(sig["stop_loss"])
    return (
        f"✍️ <b>QO'LDA SAVDO rejasi</b> — #{sig_id} {sig['symbol']}\n\n"
        f"1️⃣ Binance Spot'da <b>{sig['symbol']}</b> oching\n"
        f"2️⃣ <b>Limit Buy</b> qo'ying: <code>{fmt_price(e)}</code>\n"
        f"3️⃣ <b>OCO / TP-SL</b> sozlang:\n"
        f"   🛑 Stop-loss: <code>{fmt_price(sl)}</code>\n"
        f"   🎯 Take-profit (TP2): <code>{fmt_price(sig['tp2'])}</code>\n"
        f"4️⃣ Hajm: depozitning 1% riskiga moslang\n\n"
        f"📌 TP1 (<code>{fmt_price(sig['tp1'])}</code>) urilganda 40% oling va stop'ni "
        f"kirish narxiga (breakeven) ko'chiring.\n"
        f"Bot bu signal natijasini avtomatik kuzatib, sizga xabar beradi."
    )


def format_signal(sig: dict, sig_id: int, market_ctx: str = "") -> str:
    meta = strategy(sig.get("setup", ""))
    e, sl = float(sig["entry"]), float(sig["stop_loss"])
    r = e - sl
    tp1, tp2, tp3 = float(sig["tp1"]), float(sig["tp2"]), float(sig["tp3"])
    risk_pct = (e - sl) / e * 100

    lines = [
        f"{meta['emoji']} <b>LONG SIGNAL #{sig_id}</b> — <b>{sig['symbol']}</b>",
        f"<i>{meta['name']} · ishonch {sig.get('score')}/10</i>",
        "",
        "<b>━━━ Kirish rejasi ━━━</b>",
        f"📍 Entry:  <code>{fmt_price(e)}</code>",
        f"🛑 Stop:   <code>{fmt_price(sl)}</code>  <i>(-1R · {risk_pct:.2f}%)</i>",
        f"🎯 TP1:    <code>{fmt_price(tp1)}</code>  <i>(+{(tp1-e)/r:.1f}R · {_pct(tp1,e)} · 40%)</i>",
        f"🎯 TP2:    <code>{fmt_price(tp2)}</code>  <i>(+{(tp2-e)/r:.1f}R · {_pct(tp2,e)} · 40%)</i>",
        f"🎯 TP3:    <code>{fmt_price(tp3)}</code>  <i>(+{(tp3-e)/r:.1f}R · {_pct(tp3,e)} · 20%)</i>",
        "",
        "<b>━━━ Qaysi strategiya ━━━</b>",
        f"{meta['emoji']} <b>{meta['name']}</b>",
        f"<i>{meta['tagline']}</i>",
        "",
        "<b>━━━ Confluence tahlili ━━━</b>",
        f"<pre>{render_scorecard(sig.get('scorecard', {}))}</pre>",
    ]
    if market_ctx:
        lines += ["", f"🌐 <b>Bozor:</b> {market_ctx}"]
    lines += [
        "",
        "<b>━━━ Asoslash ━━━</b>",
        f"💡 {sig.get('reasoning', '')}",
        "",
        "⚖️ Risk: depozitning 1% · TP1 dan keyin SL→breakeven",
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
        "📊 AI-asosli crypto spot tahlil va signal tizimi\n\n"
        "📌 <b>Imkoniyatlar:</b>\n"
        "• 24/7 avtomatik skanerlash (35+ juftlik)\n"
        "• Claude AI bilan chuqur tahlil + grafik\n"
        "• Entry / TP1-3 / Stop-loss aniq belgilangan\n"
        "• Avto va qo'lda savdo (Binance)\n"
        "• Signal natijasini avtomatik kuzatish\n\n"
        "🔘 <b>Buyruqlar:</b>\n"
        "🪙 <code>/coins</code> — barcha valyutalar ro'yxati (bosing → tahlil)\n"
        "📊 <code>/analyze BTC</code> — juftlikni tahlil qilish\n"
        "💼 <code>/balance</code> — Binance portfel\n"
        "📈 <code>/stats</code> — haftalik statistika\n"
        "📂 <code>/open</code> — ochiq signallar\n"
        "❓ <code>/help</code> — yordam\n\n"
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


def format_trade_filled(sig_id: int, symbol: str, qty: float, entry: float, oco: bool) -> str:
    txt = (f"💰 <b>Savdo bajarildi</b> #{sig_id} {symbol}\n"
           f"Sotib olindi: <code>{qty}</code> @ ~<code>{fmt_price(entry)}</code>")
    txt += "\n🛡 TP/SL OCO order qo'yildi" if oco else "\n⚠️ OCO qo'yilmadi — qo'lda nazorat qiling"
    return txt
