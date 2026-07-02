"""Render an annotated candlestick chart (PNG bytes) for a symbol / signal.

Shows the last N 1h candles, EMA20/50/200, recent support/resistance, and — when a
signal is present — marks the ENTRY point with an arrow plus Entry/SL/TP1-3 levels so
it's visually obvious where to enter and where the trade is invalidated.
"""
import io

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

BARS = 120


def render(symbol: str, snap: dict, sig: dict | None = None, result: dict | None = None) -> bytes:
    """result (optional): {"exit": price, "r_val": float, "event": str} draws the
    closed-trade outcome — exit line + WIN/LOSS banner."""
    e = snap["entry_tf"].tail(BARS).reset_index(drop=True)
    x = list(range(len(e)))

    fig, (ax, axv) = plt.subplots(
        2, 1, figsize=(12, 7.8), dpi=110, sharex=True,
        gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04})
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#0e1117")
    axv.set_facecolor("#0e1117")

    # volume panel — expansion/contraction is half the story of every setup
    vol_colors = ["#26a69a" if e["close"][i] >= e["open"][i] else "#ef5350" for i in x]
    axv.bar(x, e["volume"], color=vol_colors, alpha=0.55, width=0.6, zorder=2)
    if "vol_avg20" in e:
        axv.plot(x, e["vol_avg20"], color="#ffa726", linewidth=1.0, alpha=0.8, zorder=3)
    axv.set_ylabel("Vol", color="#9aa0aa", fontsize=8)
    axv.grid(True, color="#2a2e39", linewidth=0.4, alpha=0.5)
    axv.tick_params(colors="#9aa0aa", labelsize=8)
    axv.yaxis.tick_right()
    for sp in axv.spines.values():
        sp.set_color("#2a2e39")

    # candlesticks
    for i in x:
        o, h, l, c = e["open"][i], e["high"][i], e["low"][i], e["close"][i]
        up = c >= o
        color = "#26a69a" if up else "#ef5350"
        ax.plot([i, i], [l, h], color=color, linewidth=0.8, zorder=2)
        ax.add_patch(Rectangle((i - 0.3, min(o, c)), 0.6, max(abs(c - o), h * 1e-5),
                               facecolor=color, edgecolor=color, zorder=3))

    # EMAs
    for col, color, lbl in [("ema20", "#42a5f5", "EMA20"),
                            ("ema50", "#ffa726", "EMA50"),
                            ("ema200", "#ab47bc", "EMA200")]:
        ax.plot(x, e[col], color=color, linewidth=1.3, label=lbl, zorder=4, alpha=0.9)

    # support / resistance from snapshot
    lo, hi = e["low"].min(), e["high"].max()
    for lvl in snap.get("resistance_1h", []):
        if lo <= lvl <= hi:
            ax.axhline(lvl, color="#ef5350", linestyle=":", linewidth=0.8, alpha=0.45, zorder=1)
    for lvl in snap.get("support_1h", []):
        if lo <= lvl <= hi:
            ax.axhline(lvl, color="#26a69a", linestyle=":", linewidth=0.8, alpha=0.45, zorder=1)

    title = f"{symbol}  ·  1h"

    # signal annotations
    if sig and sig.get("signal") in ("long", "short"):
        is_short = sig.get("signal") == "short"
        entry, sl = float(sig["entry"]), float(sig["stop_loss"])
        tp1, tp2, tp3 = float(sig["tp1"]), float(sig["tp2"]), float(sig["tp3"])
        xr = len(e) - 1

        def lvl(y, color, label, lw=1.6, ls="-"):
            ax.axhline(y, color=color, linestyle=ls, linewidth=lw, alpha=0.9, zorder=5)
            ax.text(0.4, y, f" {label}: {y:.4f}".rstrip("0").rstrip("."), color=color,
                    fontsize=9, va="center", ha="left", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", fc="#0e1117", ec=color, alpha=0.85))

        # shaded profit (toward TP3) & risk (toward SL) zones — works for both directions
        ax.axhspan(min(entry, tp3), max(entry, tp3), color="#26a69a", alpha=0.07, zorder=0)
        ax.axhspan(min(entry, sl), max(entry, sl), color="#ef5350", alpha=0.10, zorder=0)
        lvl(entry, "#ffffff", "KIRISH (Entry)", lw=2)
        lvl(sl, "#ef5350", "STOP", ls="--")
        lvl(tp1, "#26a69a", "TP1", lw=1.2, ls="--")
        lvl(tp2, "#26a69a", "TP2", lw=1.2, ls="--")
        lvl(tp3, "#26a69a", "TP3", lw=1.4)
        # entry arrow at the latest bar — points the trade direction
        arrow_label = "SOTISH" if is_short else "KIRISH"
        y_off = (sl - entry) * 2.2 if is_short else -(entry - sl) * 2.2
        ax.annotate(arrow_label, xy=(xr, entry), xytext=(xr - 14, entry + y_off),
                    color="#ffffff", fontsize=11, fontweight="bold", ha="center",
                    arrowprops=dict(arrowstyle="->", color="#ffffff", lw=2))
        meta_setup = sig.get("setup", "")
        direction = "SHORT" if is_short else "LONG"
        title = f"{symbol}  ·  1h  ·  {direction} (Setup {meta_setup}, {sig.get('score')}/10)"

        # closed-trade outcome overlay
        if result:
            exit_p, r_val = float(result["exit"]), float(result["r_val"])
            win = r_val > 0.05
            be = abs(r_val) <= 0.05
            ex_color = "#26a69a" if win else ("#9aa0aa" if be else "#ef5350")
            ax.axhline(exit_p, color=ex_color, linewidth=2, alpha=0.95, zorder=6)
            ax.text(0.4, exit_p, f" CHIQISH: {exit_p:.4f}".rstrip("0").rstrip("."), color=ex_color,
                    fontsize=9, va="center", ha="left", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", fc="#0e1117", ec=ex_color, alpha=0.9))
            verdict = "ISHLADI ✓" if win else ("BREAKEVEN" if be else "ISHLAMADI ✕")
            ax.text(0.5, 0.96, f"{verdict}   ·   {r_val:+.2f}R", transform=ax.transAxes,
                    fontsize=15, fontweight="bold", ha="center", va="top", color=ex_color,
                    bbox=dict(boxstyle="round,pad=0.4", fc="#1a1d26", ec=ex_color, alpha=0.95))

    ax.set_title(title, color="#ffffff", fontsize=14, fontweight="bold", pad=12)
    ax.legend(loc="lower left", facecolor="#1a1d26", edgecolor="none", labelcolor="#cfcfcf", fontsize=9)
    ax.grid(True, color="#2a2e39", linewidth=0.4, alpha=0.5)
    ax.tick_params(colors="#9aa0aa", labelsize=8)
    for s in ax.spines.values():
        s.set_color("#2a2e39")

    # x labels = time
    ticks = list(range(0, len(e), max(1, len(e) // 8)))
    axv.set_xticks(ticks)
    axv.set_xticklabels([e["ts"][i].strftime("%m-%d %H:%M") for i in ticks], rotation=0)
    ax.set_xlim(-1, len(e))
    ax.yaxis.tick_right()

    fig.text(0.99, 0.01, "⚠️ moliyaviy maslahat emas", color="#5a5f6a", fontsize=7, ha="right")
    fig.subplots_adjust(left=0.05, right=0.92, top=0.93, bottom=0.08)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()
