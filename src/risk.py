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
        return False, "shorts disabled"

    try:
        entry = float(sig["entry"])
        sl = float(sig["stop_loss"])
        tp1, tp2, tp3 = float(sig["tp1"]), float(sig["tp2"]), float(sig["tp3"])
        score = float(sig["score"])
    except (KeyError, TypeError, ValueError):
        return False, "malformed signal fields"

    if score < config.MIN_SCORE:
        return False, f"score {score} < {config.MIN_SCORE}"

    if side == "long":
        if not (sl < entry < tp1 < tp2 < tp3):
            return False, "price levels not ordered (sl < entry < tp1 < tp2 < tp3)"
        r = entry - sl
        reward2 = tp2 - entry
    else:  # short
        if not (sl > entry > tp1 > tp2 > tp3):
            return False, "price levels not ordered (sl > entry > tp1 > tp2 > tp3)"
        r = sl - entry
        reward2 = entry - tp2

    if r <= 0:
        return False, "non-positive risk distance"
    if reward2 / r < config.MIN_RR_TP2:
        return False, f"R:R to TP2 below {config.MIN_RR_TP2}"

    # Entry must be near current market price (max 1.5% away) — stale analysis guard
    if abs(entry - last_price) / last_price > 0.015:
        return False, "entry too far from current price"

    return True, "ok"
