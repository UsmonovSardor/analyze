"""Telegram delivery (plain Bot API via requests — no framework needed)."""
import requests

from . import config

API = "https://api.telegram.org/bot{token}/{method}"


def send(text: str):
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("[telegram] not configured, message:\n" + text)
        return
    r = requests.post(
        API.format(token=config.TELEGRAM_BOT_TOKEN, method="sendMessage"),
        json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
        timeout=15,
    )
    if not r.ok:
        print(f"[telegram] send failed: {r.status_code} {r.text[:200]}")


def fmt_price(p: float) -> str:
    return f"{p:.6f}".rstrip("0").rstrip(".") if p < 10 else f"{p:,.2f}"


def format_signal(sig: dict, sig_id: int) -> str:
    e, sl = sig["entry"], sig["stop_loss"]
    r = e - sl
    return (
        f"🟢 <b>LONG #{sig_id} — {sig['symbol']}</b>  (Setup {sig.get('setup','?')}, {sig.get('score')}/10)\n\n"
        f"📍 Entry: <code>{fmt_price(e)}</code>\n"
        f"🛑 Stop-loss: <code>{fmt_price(sl)}</code>  (-1R)\n"
        f"🎯 TP1: <code>{fmt_price(sig['tp1'])}</code>  (+{(sig['tp1']-e)/r:.1f}R, 40%)\n"
        f"🎯 TP2: <code>{fmt_price(sig['tp2'])}</code>  (+{(sig['tp2']-e)/r:.1f}R, 40%)\n"
        f"🎯 TP3: <code>{fmt_price(sig['tp3'])}</code>  (+{(sig['tp3']-e)/r:.1f}R, 20%)\n\n"
        f"💡 {sig.get('reasoning','')}\n\n"
        f"⚖️ Risk: depozitning 1% | TP1 dan keyin SL → breakeven\n"
        f"⚠️ Moliyaviy maslahat emas"
    )


def format_outcome(row: dict, event: str, r_val: float | None = None) -> str:
    label = {
        "tp1": "🎯 TP1 urildi — SL endi breakeven'da",
        "tp2": "🎯 TP2 urildi",
        "tp3": "✅ TP3 urildi — to'liq yopildi",
        "stopped": "🛑 Stop-loss urildi",
        "breakeven": "⚪ Breakeven'da yopildi",
    }[event]
    txt = f"{label}\n<b>#{row['id']} {row['symbol']}</b>"
    if r_val is not None:
        txt += f"  | Natija: <b>{r_val:+.2f}R</b>"
    return txt


def format_weekly(stats: dict) -> str:
    return (
        f"📊 <b>Haftalik hisobot</b>\n\n"
        f"Yopilgan signallar: {stats['closed']}\n"
        f"Yutuq: {stats['wins']} ({stats['win_rate']}%)\n"
        f"Jami natija: <b>{stats['total_r']:+.2f}R</b>\n"
        f"Ochiq signallar: {stats['open']}"
    )
