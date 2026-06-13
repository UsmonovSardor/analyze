"""Parameter sweep: backtest many strategy variants and rank them.

Keeps the live screener untouched. Reimplements the core entry detection in a
parameterized, vectorized-friendly way so dozens of combos run in-memory after
fetching each symbol's data ONCE. Goal: find a variant with a real positive edge
before any live trading.

Usage:
    python -m src.tuning            # default 180d, all SYMBOLS
    python -m src.tuning 270        # 270 days
"""
import itertools
import sys
from dataclasses import dataclass

from . import config
from .data import add_indicators, fetch_ohlcv

LOOKFORWARD = 120


@dataclass(frozen=True)
class Params:
    atr_stop: float          # SL distance in ATR
    setups: tuple            # which setups allowed: ("A",), ("B",), ("A","B")
    vol_mult: float          # breakout volume requirement (Setup B)
    strong_trend: bool       # require ema20>ema50>ema200 (Setup A)
    tp_mode: str             # "fixed" (1.5/2.5/4 partials) or "trail"
    trail_atr: float         # trailing distance for tp_mode="trail"

    def label(self) -> str:
        s = "+".join(self.setups)
        t = f"trail{self.trail_atr}" if self.tp_mode == "trail" else "fixed"
        return f"SL{self.atr_stop}·{s}·vol{self.vol_mult}·{'strong' if self.strong_trend else 'std'}·{t}"


def _prep(symbol: str, days: int):
    bars = min(days * 24 + 300, 1000)
    e = add_indicators(fetch_ohlcv(symbol, config.ENTRY_TF, bars)).reset_index(drop=True)
    ctx = add_indicators(fetch_ohlcv(symbol, config.CONTEXT_TF, bars // 4 + 200)).reset_index(drop=True)
    # map each 1h bar to the latest closed 4h bar (causal)
    ctx_ts = ctx["ts"].values
    ctx_idx = ctx_ts.searchsorted(e["ts"].values, side="right") - 1
    return e, ctx, ctx_idx


def _entry_signal(e, ctx, ctx_idx, i, p: Params):
    ci = ctx_idx[i]
    if ci < 200 or i < 60:
        return None
    c = float(e["close"].iloc[i])
    atr = float(e["atr"].iloc[i])
    if atr <= 0:
        return None

    up4 = ctx["close"].iloc[ci] > ctx["ema200"].iloc[ci] and ctx["ema50"].iloc[ci] > ctx["ema200"].iloc[ci]

    # Setup A — pullback to EMA50 in uptrend
    if "A" in p.setups and up4:
        cond_trend = True
        if p.strong_trend:
            cond_trend = e["ema20"].iloc[i] > e["ema50"].iloc[i] > e["ema200"].iloc[i]
        near = abs(c - float(e["ema50"].iloc[i])) <= 1.0 * atr
        rsi_now, rsi_prev = float(e["rsi"].iloc[i]), float(e["rsi"].iloc[i - 1])
        reset = rsi_now < 55 and rsi_now > rsi_prev and float(e["rsi"].iloc[i - 6:i].min()) < 45
        if cond_trend and near and reset:
            return "A"

    # Setup B — range-high breakout on volume
    if "B" in p.setups and up4:
        range_high = float(e["high"].iloc[i - 40:i - 1].max())
        vol_ok = float(e["volume"].iloc[i]) >= p.vol_mult * float(e["vol_avg20"].iloc[i])
        if c > range_high and (c - range_high) <= 1.5 * atr and vol_ok:
            return "B"
    return None


def _simulate(e, i, entry, sl, p: Params):
    r = entry - sl
    if p.tp_mode == "fixed":
        tp1, tp2, tp3 = entry + 1.5 * r, entry + 2.5 * r, entry + 4 * r
        status = "open"
        for j in range(i + 1, min(i + 1 + LOOKFORWARD, len(e))):
            hi, lo = float(e["high"].iloc[j]), float(e["low"].iloc[j])
            eff_sl = entry if status in ("tp1", "tp2") else sl
            if lo <= eff_sl:
                if status == "open":
                    return -1.0
                parts = 0.4 * (tp1 - entry) / r + (0.4 * (tp2 - entry) / r if status == "tp2" else 0)
                rem = {"tp1": 0.6, "tp2": 0.2}[status]
                return parts + rem * (eff_sl - entry) / r
            if hi >= tp3 and status == "tp2":
                return (0.4 * (tp1 - entry) + 0.4 * (tp2 - entry) + 0.2 * (tp3 - entry)) / r
            if hi >= tp2 and status == "tp1":
                status = "tp2"
            elif hi >= tp1 and status == "open":
                status = "tp1"
        return (float(e["close"].iloc[min(i + LOOKFORWARD, len(e) - 1)]) - entry) / r
    else:  # trailing stop after first 1R, lets winners run
        atr0 = (entry - sl) / p.atr_stop
        trail = sl
        armed = False
        for j in range(i + 1, min(i + 1 + LOOKFORWARD, len(e))):
            hi, lo = float(e["high"].iloc[j]), float(e["low"].iloc[j])
            if hi >= entry + 1.0 * r:
                armed = True
            if armed:
                trail = max(trail, hi - p.trail_atr * atr0)
            if lo <= trail:
                return (trail - entry) / r
        return (float(e["close"].iloc[min(i + LOOKFORWARD, len(e) - 1)]) - entry) / r


def run_combo(data, p: Params):
    trades = []
    for e, ctx, ctx_idx in data:
        cd = 0
        for i in range(250, len(e) - 2):
            if cd > 0:
                cd -= 1
                continue
            hint = _entry_signal(e, ctx, ctx_idx, i, p)
            if not hint:
                continue
            entry = float(e["close"].iloc[i])
            sl = entry - p.atr_stop * float(e["atr"].iloc[i])
            trades.append((hint, _simulate(e, i, entry, sl, p)))
            cd = 12
    return trades


def score(trades):
    if not trades:
        return {"n": 0, "win": 0, "total_r": 0, "avg_r": 0, "expectancy": -99}
    rs = [r for _, r in trades]
    wins = [r for r in rs if r > 0]
    return {
        "n": len(rs),
        "win": round(100 * len(wins) / len(rs), 1),
        "total_r": round(sum(rs), 2),
        "avg_r": round(sum(rs) / len(rs), 3),
        "expectancy": round(sum(rs) / len(rs), 3),
    }


def grid():
    combos = []
    for atr_stop, setups, tp in itertools.product(
        [1.3, 2.0, 2.8],
        [("A",), ("B",), ("A", "B")],
        [("fixed", 0.0), ("trail", 2.0), ("trail", 3.0)],
    ):
        strong = setups != ("B",)  # strong-trend filter only relevant when A present
        combos.append(Params(atr_stop=atr_stop, setups=setups, vol_mult=1.5,
                             strong_trend=strong, tp_mode=tp[0], trail_atr=tp[1]))
    return combos


def main():
    days = int(next((a for a in sys.argv[1:] if a.isdigit()), 180))
    print(f"Ma'lumot yuklanmoqda ({len(config.SYMBOLS)} juftlik, ~{days} kun)...")
    data = []
    for s in config.SYMBOLS:
        try:
            data.append(_prep(s, days))
        except Exception as exc:
            print(f"  {s}: skip — {exc}")
    combos = grid()
    print(f"{len(combos)} ta variant sinalmoqda...\n")
    results = []
    for p in combos:
        st = score(run_combo(data, p))
        results.append((p, st))
        print(f"  {p.label():<46} n={st['n']:<4} win={st['win']:<5} totalR={st['total_r']:+.1f}")

    print("\n══════════ TOP 5 (jami R bo'yicha, n≥20) ══════════")
    ranked = sorted([r for r in results if r[1]["n"] >= 20],
                    key=lambda x: x[1]["total_r"], reverse=True)[:5]
    for p, st in ranked:
        print(f"  {st['total_r']:+6.1f}R  win {st['win']}%  n={st['n']}  avg {st['avg_r']:+.3f}R  | {p.label()}")
    if ranked:
        best = ranked[0][0]
        print(f"\n🏆 ENG YAXSHI: {best.label()}")
        print(f"   atr_stop={best.atr_stop} setups={best.setups} tp_mode={best.tp_mode} "
              f"trail_atr={best.trail_atr} strong_trend={best.strong_trend}")
    else:
        print("  Yetarli savdoli musbat variant topilmadi.")


if __name__ == "__main__":
    main()
