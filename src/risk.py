"""Deterministic risk gate. The model proposes; this code disposes.

Supports both directions:
  long:  stop_loss < entry < tp1 < tp2 < tp3   (R = entry - stop_loss)
  short: stop_loss > entry > tp1 > tp2 > tp3   (R = stop_loss - entry)
"""
from . import config


def validate(sig: dict, last_price: float) -> tuple[bool, str]:
    side = sig.get("signal")
    if side not in ("long", "short"):
        return False, sig.get("reason", "no setup")
    if side == "short" and not config.ALLOW_SHORTS:
        return False, "short signallar o'chirilgan"

    try:
        entry = float(sig["entry"])
        sl = float(sig["stop_loss"])
        tp1, tp2, tp3 = float(sig["tp1"]), float(sig["tp2"]), float(sig["tp3"])
        score = float(sig["score"])
    except (KeyError, TypeError, ValueError):
        return False, "signal maydonlari xato (narxlar yetishmayapti)"

    if score < config.MIN_SCORE:
        return False, f"ishonch {score:.0f}/10 — minimal {config.MIN_SCORE} dan past"

    if side == "long":
        if not (sl < entry < tp1 < tp2 < tp3):
            return False, "narx darajalari tartibsiz (SL < Kirish < TP1 < TP2 < TP3 bo'lishi kerak)"
        r = entry - sl
        reward2 = tp2 - entry
    else:  # short
        if not (sl > entry > tp1 > tp2 > tp3):
            return False, "narx darajalari tartibsiz (SL > Kirish > TP1 > TP2 > TP3 bo'lishi kerak)"
        r = sl - entry
        reward2 = entry - tp2

    if r <= 0:
        return False, "risk masofasi nolga teng"
    if reward2 / r < config.MIN_RR_TP2:
        return False, f"TP2 gacha foyda/risk nisbati {config.MIN_RR_TP2} dan past"

    # Entry must be near current market price (max 1.5% away) — stale analysis guard
    if abs(entry - last_price) / last_price > 0.015:
        return False, "kirish narxi joriy narxdan juda uzoq (>1.5%)"

    return True, "ok"
