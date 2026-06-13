"""Historical backtest of the deterministic entry rules.

Honesty note: this backtests the SCREENER rules + risk model (the deterministic layer),
NOT Claude's judgment — running the LLM over thousands of bars is impractical/expensive.
Claude in production only makes the system MORE selective, so these numbers are a
conservative-to-optimistic proxy: treat them as "is the underlying edge real?", not as
the exact live result. Same partial-exit (40/40/20) and breakeven logic as live.

Usage:
    python -m src.backtest                 # all SYMBOLS, 120 days
    python -m src.backtest BTC/USDT 180    # one symbol, 180 days
"""
import sys

from . import config, screener
from .data import add_indicators, fetch_ohlcv, swing_levels

LOOKFORWARD = 120          # max 1h bars to resolve a trade
ATR_STOP_MULT = 1.3        # SL distance in ATR (mid of risk-rules 0.8–2.0 band)
COOLDOWN_BARS = 12         # mirror COOLDOWN_HOURS_PER_SYMBOL on 1h


def _snap_at(e, ctx, i, ts):
    """Build a screener-compatible snapshot using only data up to bar i."""
    e_slice = e.iloc[: i + 1]
    ctx_slice = ctx[ctx["ts"] <= ts]
    if len(ctx_slice) < 200 or len(e_slice) < 60:
        return None
    res, sup = swing_levels(e_slice)
    res4, sup4 = swing_levels(ctx_slice, lookback=80)
    return {"symbol": "BT", "entry_tf": e_slice, "context_tf": ctx_slice,
            "resistance_1h": res, "support_1h": sup,
            "resistance_4h": res4, "support_4h": sup4}


def _simulate(e, i, entry, sl, tp1, tp2, tp3):
    """Walk forward; return realized R using partial exits + breakeven-after-TP1."""
    r = entry - sl
    status = "open"
    for j in range(i + 1, min(i + 1 + LOOKFORWARD, len(e))):
        hi, lo = float(e["high"].iloc[j]), float(e["low"].iloc[j])
        eff_sl = entry if status in ("tp1", "tp2") else sl
        if lo <= eff_sl:
            if status == "open":
                return -1.0, "stopped", j - i
            parts = 0.4 * (tp1 - entry) / r
            if status == "tp2":
                parts += 0.4 * (tp2 - entry) / r
            rem = {"tp1": 0.6, "tp2": 0.2}[status]
            return parts + rem * (eff_sl - entry) / r, "breakeven", j - i
        if hi >= tp3 and status == "tp2":
            return (0.4 * (tp1 - entry) + 0.4 * (tp2 - entry) + 0.2 * (tp3 - entry)) / r, "tp3", j - i
        if hi >= tp2 and status == "tp1":
            status = "tp2"
        elif hi >= tp1 and status == "open":
            status = "tp1"
    # timed out — mark to last close
    last = float(e["close"].iloc[min(i + LOOKFORWARD, len(e) - 1)])
    return (last - entry) / r, "timeout", LOOKFORWARD


def backtest_symbol(symbol: str, days: int) -> list[dict]:
    bars = min(days * 24 + 300, 1000)
    e = add_indicators(fetch_ohlcv(symbol, config.ENTRY_TF, bars))
    ctx = add_indicators(fetch_ohlcv(symbol, config.CONTEXT_TF, bars // 4 + 200))
    trades, cooldown = [], 0
    for i in range(250, len(e) - 2):
        if cooldown > 0:
            cooldown -= 1
            continue
        snap = _snap_at(e, ctx, i, e["ts"].iloc[i])
        if not snap:
            continue
        hint = screener.find_candidate(snap)
        if not hint:
            continue
        entry = float(e["close"].iloc[i])
        atr = float(e["atr"].iloc[i])
        sl = entry - ATR_STOP_MULT * atr
        r = entry - sl
        rr, outcome, held = _simulate(e, i, entry, sl, entry + 1.5 * r, entry + 2.5 * r, entry + 4 * r)
        trades.append({"symbol": symbol, "setup": hint, "r": rr, "outcome": outcome, "bars_held": held})
        cooldown = COOLDOWN_BARS
    return trades


def summarize(trades: list[dict]) -> str:
    if not trades:
        return "Hech qanday savdo topilmadi (juda kam tarix yoki signal yo'q)."
    wins = [t for t in trades if t["r"] > 0]
    total_r = sum(t["r"] for t in trades)
    avg = total_r / len(trades)
    lines = [
        "═══════════ BACKTEST NATIJASI ═══════════",
        f"Jami savdo:   {len(trades)}",
        f"Yutuq:        {len(wins)} ({100*len(wins)/len(trades):.1f}%)",
        f"Jami R:       {total_r:+.2f}R",
        f"O'rtacha R:   {avg:+.3f}R / savdo",
        f"Eng yaxshi:   {max(t['r'] for t in trades):+.2f}R   Eng yomon: {min(t['r'] for t in trades):+.2f}R",
        "",
        "Strategiya bo'yicha:",
    ]
    for setup in sorted({t["setup"] for t in trades}):
        ts = [t for t in trades if t["setup"] == setup]
        w = [t for t in ts if t["r"] > 0]
        lines.append(f"  Setup {setup}: {len(ts)} savdo · {100*len(w)/len(ts):.0f}% win · "
                     f"{sum(t['r'] for t in ts):+.2f}R")
    lines += ["", "Natija bo'yicha:"]
    for oc in ("tp3", "tp2", "tp1", "breakeven", "stopped", "timeout"):
        n = sum(1 for t in trades if t["outcome"] == oc)
        if n:
            lines.append(f"  {oc:<10} {n}")
    lines.append("══════════════════════════════════════════")
    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    symbols = [args[0]] if args and "/" in args[0] else config.SYMBOLS
    days = int(next((a for a in args if a.isdigit()), 120))
    print(f"Backtesting {len(symbols)} ta juftlik, ~{days} kun...\n")
    all_trades = []
    for s in symbols:
        try:
            t = backtest_symbol(s, days)
            all_trades += t
            print(f"  {s}: {len(t)} savdo, {sum(x['r'] for x in t):+.2f}R")
        except Exception as exc:
            print(f"  {s}: xato — {exc}")
    print("\n" + summarize(all_trades))


if __name__ == "__main__":
    main()
