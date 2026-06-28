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

---

## ICT Smart Money Models (Advanced Setups — Setup C/D)

These models extend Setup A/B with ICT (Inner Circle Trader) Smart Money Concepts. Use them as additional confluence or as standalone setups when classic A/B conditions are absent.

---

### ICT AMD / Power of Three (PO3)

**Timeframe**: 5m (entries), 1h (context). Works on any session.

**Structure**: Market moves in 3 phases:
1. **Accumulation** — tight consolidation range (identify using candle BODIES, not wicks)
2. **Manipulation** — quick spike OUT of the range then BACK inside it (false breakout to grab liquidity)
3. **Distribution** — directional move to the opposite side of the accumulation range

**Entry Trigger #1 — iFVG Retest**: During the manipulation leg, a Fair Value Gap forms. When price inverts that FVG and retests it, enter.
- SL: at manipulation high (short) or low (long)
- TP: 2 standard deviations of the manipulation leg (if provides ≥2R), else 4 STDV

**Entry Trigger #2 — Box Setup**: No iFVG available. After price closes back into the accumulation zone, enter on retest of the manipulation box high (longs) or low (shorts).
- Same SL/TP as above

**Win rate boosters**:
- HTF liquidity swept during manipulation (session H/L, prior day H/L)
- Trade aligns with HTF AMD distribution direction
- Continuation trades only when HTF trend agrees

**AMD/PO3 Checklist**: Accumulation zone identified → Manipulation out-and-back confirmed → Entry on iFVG retest or manipulation box retest → SL at manipulation extreme → TP at 2 STDV (≥2R) or 4 STDV

---

### ICT Judas Swing (Asia Session Variation)

**Timeframe**: 5m. **Pairs**: GBPJPY (primary), GU, EU, AU. **Session**: London open 3:00–5:30am NY time.

**Asia Range**: 9am–4pm Tokyo (00:00–07:00 UTC). Mark the high and low of this range.

**Setup**:
1. Price sweeps the Asia H or Asia L during London session (creates a false break)
2. Wait for 5m market structure shift (MSS) — a candle that closes back inside the Asia range
3. Enter on MSS candle close. SL at the sweep high/low.
4. TP = opposite side of the Asia range. No active trade management.

**Invalidations** (do NOT trade if any apply):
- Sweep extended >50% OUTSIDE the Asia range (use Fib 0/1/-0.5 to measure)
- Longs: price must be in BOTTOM half of Asia range at time of entry
- Shorts: price must be in TOP half of Asia range at time of entry
- No trendline liquidity visible (prior swing highs/lows that form a trendline = required)

**Judas Swing Checklist**: Asia H/L marked → Sweep during London session (<50% deviation) → Trendline liquidity present → MSS on 5m (entry) → Entry at or below/above Asia midpoint → TP opposite side of Asia range

---

### ICT Unicorn Model

**Timeframe**: 5m. **Market**: ES/NQ (indices). **Session**: NY after 9:30am.

**Key concepts**:
- **Breaker** = failed order block. Bullish breaker: last green candle BEFORE a lower low. Bearish breaker: last red candle BEFORE a higher high.
- **FVG** = Fair Value Gap: non-overlapping wicks between 3 consecutive candles.
- **DOL** = Draw on Liquidity: equal highs (buy-side) or equal lows (sell-side).

**Steps**:
1. Identify DOL (equal highs or equal lows as the target)
2. Wait for manipulation AWAY from the DOL
3. Displacement back toward DOL forms an overlapping Breaker + FVG (Unicorn = both overlap)
4. Enter on retest of the Breaker/FVG overlap zone
5. SL: body high/low of the manipulation leg
6. TP: 2 STDV of manipulation leg OR hold to the DOL (whichever provides ≥2R)

**Rules**: No trades during red-folder news. Trade must provide ≥2R. No active management, let it play out.

**Unicorn Checklist**: DOL identified → Manipulation away from DOL → Overlapping Breaker + FVG formed → Retest of BB/FVG (entry) → SL at manipulation body H/L → TP 2 STDV or DOL

---

### ICT Venom Model (2025)

**Timeframe**: 1m. **Market**: NQ (primary), indices, gold. **Session**: 9:30–11:00am NY only.

**Setup**:
1. Mark the 8:00–9:30am NY pre-market range H/L
2. After 9:30am open, price takes out the 8-9:30am high OR low
3. An initial FVG forms on 1m

**Entry #1 — BPR Retest** (preferred): After the sweep, a Balanced Price Range (BPR = two overlapping FVGs) forms. Enter on limit order at BPR retest.
- SL: recent swing H/L
- TP: fixed 2R (or other side of 8-9:30am range with HTF bias)

**Entry #2 — Venom Breakout**: A strong engulfing candle inverts the initial FVG (closes past it). Enter market order.
- SL: open of the engulfing candle
- TP: fixed 2R

**Rules**:
- No trades after 11:00am NY
- No trades if price already hit 2R before BPR forms
- No trades near red-folder news
- 2nd attempt allowed if first entry stopped out and new entry forms

**Venom Checklist**: 8-9:30am range marked → 9:30am sweep of range H/L → Initial FVG noted → BPR retest (Entry #1) OR engulfing inverts FVG (Entry #2) → SL at swing H/L or candle open → TP 2R fixed

---

### ICT Turtle Soup (TBL Sweep + Reversal)

**Timeframe**: 5m. **Market**: NQ/ES. **Session**: NY after 9:30am.

**Core concept**: Time-Based Liquidity (TBL) — session H/L, previous day H/L (PDH/PDL), Asia H/L, London H/L. After TBL sweep, smart money reverses.

**Bias identification**: Use TBL levels, NWOGs (New Week Opening Gaps = gap between Friday close and Sunday open), and premium/discount array.

**Entry #1 — CISD Retest (Reversal)**: After TBL sweep, wait for CISD (Change in State of Delivery — candle that closes past the body of the recent price leg). Enter on CISD retest with SL at recent H/L. TP: internal H/L, FVG fill, or premium/discount rebalance. Target 1.5–2R.

**Entry #2 — FVG Retest (Continuation)**: Clear DOL identified. Look for FVG to retest on the way to DOL. SL at H/L of candle that formed the FVG. Fixed 2R TP.

**Rules**:
- Ignore doji/small-bodied candles for CISD signals
- Cancel limit orders if TP hit before entry
- Don't take continuation trades near opposing TBL (don't long when too close to buy-side TBL)
- Max 2 attempts per day (for beginners: done after 1 win)

**Turtle Soup Checklist (CISD)**: TBL sweep → Reversal bias → CISD candle formed → Limit entry on CISD retest → SL at recent H/L → TP 1.5–2R

**Turtle Soup Checklist (FVG)**: DOL identified → Reversal started → FVG retest (entry) → SL at FVG candle H/L → Fixed 2R TP

---

### ICT MMXM (Market Maker Buy/Sell Model)

**Timeframe**: 1h for HTF POI identification, 5m for entries. **Market**: MES/MNQ (indices). **Session**: 9:30am–3:00pm ET.

**The full MMXM cycle**:
- **Market Maker Buy**: Original Consolidation → 1st Stage Distribution (down) → 2nd Stage Distribution (lower) → 1st Stage Accumulation → 2nd Stage Accumulation → Smart Money Reversal → Buy side of curve (up)
- **Market Maker Sell**: Mirror image upward then down

**Daily Bias**: Use 1h 200 EMA. Price above = bullish bias, below = bearish.

**HTF POI** (Points of Interest): 1h FVGs, Balanced Price Ranges (BPR), or Order Blocks (supply/demand zones).

**Smart Money Reversal (SMR)**: Occurs near HTF POI. Requires TWO forms of liquidity taken (HTF + LTF) + SMT Divergence (two correlated assets making divergent H/L, e.g., ES vs NQ).

**Three entry tiers**:

1. **Low-risk buy/sell** (highest R, lower win rate): LTF Breaker + FVG at HTF POI (= Unicorn Model entry). SL at local low/high. TP first opposing liquidity ≥2R.

2. **1st stage accumulation/distribution** (moderate R and win rate): Enter on Order Block retrace (Doyle Exchange model). After wick into OB, enter above (below) candle that wicked into OB. SL at wick low (high). TP first FVG fill or opposing liquidity ≥3R.

3. **2nd stage re-accumulation/re-distribution** (lower R, higher win rate): Same as 1st stage entry but TP = original consolidation liquidity (external liquidity).

**MMXM Rules**: No entry near red-folder news. No active trade management.

**MMXM Low-Risk Checklist**: MMXM model near HTF POI → LTF SMT Divergence during manipulation → Market Structure Shift + overlapping Breaker + FVG → Retest of FVG/Breaker (Unicorn entry) → TP first opposing liquidity ≥2R

---

## ICT Concept Glossary (for AI signal reasoning)

| Term | Definition |
|------|-----------|
| FVG | Fair Value Gap: 3-candle pattern where candle 1 wick and candle 3 wick do NOT overlap |
| iFVG | Inverse FVG: an FVG that price has traded through and now acts as support/resistance |
| BPR | Balanced Price Range: two overlapping FVGs |
| Breaker | Failed order block: last green before LL (bullish) or last red before HH (bearish) |
| CISD | Change in State of Delivery: candle closing past the body of the prior price leg |
| DOL | Draw on Liquidity: target (equal highs = BSL, equal lows = SSL) |
| TBL | Time-Based Liquidity: session/day/week H/L levels |
| NWOG | New Week Opening Gap: gap between Friday close and Sunday open |
| SMT | Smart Money Tool/Divergence: two correlated assets making divergent extremes |
| MSS | Market Structure Shift: first candle that breaks prior swing high/low |
| HTF POI | Higher Timeframe Point of Interest: FVG/OB/BPR on 1h or higher |
| BSL/SSL | Buy-Side Liquidity / Sell-Side Liquidity (stop clusters above highs / below lows) |
| PDH/PDL | Prior Day High / Prior Day Low (key TBL levels) |

---

## Reasoning Quality Standards (Reminiscences + Market Wizards)

When writing the `reasoning` field in the signal JSON:
1. State which SPECIFIC level (exact price) is the structural support/entry zone.
2. State which candle pattern formed (e.g., "hammer with lower shadow 2.3× the body").
3. State the regime clearly (e.g., "4h uptrend, EMA50 rising, BTC neutral").
4. State the invalidation (exactly where the stop is and WHY that price is the invalidation).

Livermore: "I don't buy because a stock has gone up. I buy because the right thing has happened at the right time at the right place." — Your reasoning must reflect this specificity.
