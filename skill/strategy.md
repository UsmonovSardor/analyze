# Strategy Rules — Spot Swing (1h entry / 4h context)

Only TWO setups are tradeable. Anything else is `none`.

---

## Setup A — Trend Pullback (High 2 / EMA50 Retest)

**Source**: Nison candlestick reversal + Brooks High-2 pullback + Livermore trend following

Context (4h), ALL required:
- Price above EMA200 AND EMA50 above EMA200 (confirmed uptrend)
- Structure of higher highs and higher lows
- BTC 4h is not in a strong downtrend

Entry conditions (1h), ALL required:
1. **Pullback depth**: Price pulled back to the EMA50 zone (±1.0×ATR) OR to a prior breakout level / swing support — must be within 25%–75% retracement of the prior bull swing. If > 75%: reject.
2. **RSI reset**: RSI(14) dipped below 45 at some point in the last 6 bars, AND current RSI > prior bar's RSI (turning up). RSI reset below 40 = stronger signal.
3. **Candle confirmation** (from Nison): At least ONE of these on the signal bar (bar closing at/after the pullback):
   - Hammer (lower shadow ≥ 2× body)
   - Bullish engulfing (bull bar engulfs prior bear bar)
   - Morning star (3-bar pattern)
   - Piercing pattern (closes above 50% of prior bear bar)
   - "ii" inside-inside pattern with bull breakout bar
   - Strong bull trend bar (body ≥ 60% of range, closes top 25%)
4. **Pullback volume**: Pullback bars (bear bars in the dip) should have LOWER volume than the prior impulse leg average. Healthy retracement = low-volume dip. High-volume selling into support = red flag.
5. **No large upper wick on signal bar**: If the entry bar has an upper wick > 60% of its total range, the bears are absorbing buyers. Reject.

**High-quality bonus** (add to reasoning):
- Two-legged pullback (leg 1 then leg 2 = "Higher 2" / "High 2" per Brooks): signal is much stronger than a single-leg dip
- Sell climax before the pullback (15+ red bars, RSI < 25, then hammer): extremely high quality
- The midpoint of a prior long white candle (Nison) coincides with the EMA50 — double support

---

## Setup B — Range Breakout with Retest

**Source**: Brooks breakout analysis + Nison long white candle breakout confirmation

Context (4h), ALL required:
- Price was compressed in a range for ≥ 30 bars (1h) with a clearly defined upper boundary
- BTC 4h is not in a strong downtrend

Entry conditions (1h), ALL required:
1. **Close above range high** with volume ≥ 1.5× the 20-bar average ON THE BREAKOUT BAR.
2. **Entry method** (choose the BETTER one):
   - **Preferred (retest)**: After the breakout, price pulls back to the broken level. Enter on the close of a small bear bar or doji at that level — it must NOT close back below the range high. This is the highest-quality Setup B entry.
   - **Immediate breakout**: Enter within 0.5×ATR(14) of the breakout bar's close — only if the breakout bar is a strong bull trend bar (body ≥ 60% of range, no large upper wick).
3. **No higher-timeframe resistance within 1R of entry**: Check 4h resistance levels.
4. **Candle quality at entry** (Nison): The entry bar should be a strong bull trend bar or a small doji/inside bar at the retest level. A large upper wick at the retest = trap, reject.

**Failed breakout warning** (Brooks "bull trap"):
- Breakout bar is large but next bar REVERSES most of it (closes below the range high).
- This is a bull trap. Do NOT enter. Institutional sellers absorbed the breakout buyers.
- If you already entered, this is an early exit signal.

---

## Market Regime (MUST determine BEFORE scoring)

**Regime 1 — Strong Bull Trend**: 4h EMA50/200 aligned, price well above both, clean higher high/higher low structure. → Setup A is the primary setup. Setup B allowed.

**Regime 2 — Bull Trend with Pullbacks**: Bull trend but price has corrected significantly. EMA50 being tested on 4h. → Setup A only. Extra candle confirmation required.

**Regime 3 — Range / Consolidation**: Flat or narrowing EMAs, price oscillating between defined levels. → Setup B ONLY on confirmed breakout. Buying mid-range is FORBIDDEN (Reminiscences: "don't guess the breakout direction, wait for the market to tell you").

**Regime 4 — High-Volatility Chop**: Huge wicks, ATR spiking > 2× normal, no structure, EMAs tangled. → **NOTHING IS ALLOWED. Reject everything.** (Livermore: "There are times when I won't do anything. Not even consider a trade.")

**Regime 5 — Bear Trend / Downtrend**: Price below EMA200, EMA50 < EMA200. → **Hard reject all longs. Look for SHORT setups (A or B short) instead**, trading WITH the down-trend. (Nison: "place a new position based on a reversal signal ONLY if that signal is in the direction of the major trend.")

---

## Short Setups (mirror image — only in a 4h DOWNTREND)

Both setups apply symmetrically to the short side. Everything flips:

- **Setup A short (bounce to EMA50 in a downtrend)**: 4h price below EMA200 and EMA50 < EMA200.
  Price bounces UP into the EMA50 zone (±1.0×ATR) or a prior breakdown level. RSI rallies toward
  55–65 then turns DOWN. Entry on a bearish confirmation candle (shooting star, bearish engulfing,
  evening star, strong bear trend bar). SL ABOVE the bounce swing high. Targets below.
- **Setup B short (range breakdown + retest)**: price breaks BELOW a ≥30-bar range low on volume
  ≥ 1.5× average, then retests the broken level from below. Enter on a small bull bar / doji that
  fails to reclaim the level. SL above the broken level. A failed breakdown (price reclaims the range
  low) is a bull trap against you — do NOT enter.

For shorts, "BTC context" means BTC 4h should be neutral-to-bearish (don't short alts into a strong
BTC bull). All other rejection rules apply with direction reversed.

---

## Confluence Scorecard (need ≥ 6 to pass)

| # | Factor | Points | How to judge |
|---|--------|--------|--------------|
| 1 | **4h trend aligned** (EMA50 > EMA200, price above both) | 2 | Both required for 2 pts; price only above EMA200 but EMA50 below = 1 pt |
| 2 | **Entry at a real level** (EMA50, prior breakout, swing support, midpoint of a long white candle) | 2 | Structure-based level = 2 pts; vague zone = 1 pt |
| 3 | **Volume confirms** (low volume pullback + volume expansion at entry, OR breakout volume ≥ 1.5×) | 2 | Clear confirmation = 2 pts; borderline = 1 pt; volume against = 0 pts |
| 4 | **RSI agrees** (reset below 45, now turning up; no bearish divergence) | 1 | RSI divergence present = automatic 0 pts here |
| 5 | **BTC context supportive or neutral** (BTC 4h not in downtrend) | 1 | BTC actively falling on 4h = 0 pts |
| 6 | **Clean room above** (nearest resistance ≥ 2R away from entry) | 1 | Major resistance < 1R = reject entire trade |
| 7 | **Candle quality** (hammer/engulfing/morning star/strong bull bar at the exact entry level) | 1 | Per candlestick-patterns.md |

Score every factor explicitly. State the exact points for each. A score < 6 = reject without exception.
For shorts, score each factor as its mirror (trend DOWN aligned, breakdown volume, RSI rolling over, etc.).

**From Market Wizards**: "Risk control is the #1 common denominator among ALL top traders." A setup with 6/10 that looks amazing is still a 6/10. Do not negotiate with the minimum.

---

## Hard Rejection Rules

- BTC 4h trend is strongly down (EMA50 < EMA200 AND price below both) AND candidate is an altcoin → **reject** (alts follow BTC).
- Price is mid-range with no nearby support → **reject** (buying mid-range is forbidden per Brooks and Livermore).
- The move already extended > 2×ATR(14) from the trigger level → too late, momentum gone → **reject**.
- Volume does NOT confirm (breakout on below-average volume, or pullback on HIGHER volume than the impulse) → **reject** (bears are selling aggressively).
- Bearish candle pattern present at entry zone (shooting star, dark cloud cover, evening star, bearish engulfing) → **reject** (Nison: "bearish signals require defensive action").
- Pullback > 75% of prior bull swing → likely trend failure → **reject** (Brooks 75% rule).
- Large upper wick on signal bar (> 60% of total range is wick) → supply zone, distribution → **reject**.
- 4 or more tests of the same resistance level without a break → level is about to break but short-term risk too high → **reject**.
- Major 4h resistance sitting within 1R above entry → insufficient room → **reject**.

---

## Reasoning Quality Standards (Reminiscences + Market Wizards)

When writing the `reasoning` field in the signal JSON:
1. State which SPECIFIC level (exact price) is the structural support/entry zone.
2. State which candle pattern formed (e.g., "hammer with lower shadow 2.3× the body").
3. State the regime clearly (e.g., "4h uptrend, EMA50 rising, BTC neutral").
4. State the invalidation (exactly where the stop is and WHY that price is the invalidation).

Livermore: "I don't buy because a stock has gone up. I buy because the right thing has happened at the right time at the right place." — Your reasoning must reflect this specificity.
