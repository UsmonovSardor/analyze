# BLACK LION AI — Win Rate Improvement Plan

Maqsad: **kamida 10 tadan 8 tasi ishlaydigan (80%+ win rate)** signallar, stop-loss kamdan-kam uriladi.
Asosiy printsip: **Rule Engine (deterministik kod) signal yaratadi, AI (Grok) faqat tasdiqlaydi va izohlaydi.**

> Vizual arxitektura: [`docs/architecture.html`](architecture.html) (brauzerda oching).

---

## AI provayder — Grok (xAI)

Loyha endi **Grok** bilan ishlaydi (`AI_PROVIDER=grok`). Kod: [`src/ai_client.py`](../src/ai_client.py).

- **grok-4** — yakuniy qaror (kuchli reasoning)
- **grok-3-mini** — tez/arzon zaxira (grok-4 xato bersa)
- Gemini kaliti bo'lsa — Grok ishlamaganda avtomatik zaxira

Grok afzalligi: **real-time X (Twitter) + yangiliklar** — bu news-driven false breakout'lardan (stop-loss'ning eng katta sababi) himoya qiladi.

---

## 10 ta yo'nalish (ta'sir bo'yicha tartiblangan)

### 1. Multi-Timeframe Alignment (eng muhim, ~+18% WR)
Uchala TF bir yo'nalishda bo'lmasa — signal YO'Q.
```
HTF (H4/D1) → trend yo'nalishi
MTF (H1)    → struktura + OB/FVG zonasi
LTF (M15)   → aniq entry trigger
```

### 2. Displacement + ATR-based dinamik SL
Stop noto'g'ri joyda bo'lsa uriladi. Yechim:
```
SL  = OB pastida + 0.3×ATR (buffer), yaxlit raqamlar ostida EMAS
TP1 = 1.5R, TP2 = 2.5R, TP3 = 4R
TP1 ga yetganda → SL Breakeven'ga
```

### 3. Session / Kill Zone filtri (~+8% WR)
```
TRADE: London Open (08:00–10:00 GMT), NY Open (13:00–15:00 GMT)
AVOID: Asian range (likvidlik yo'q), yangilik ±30 daqiqa (NFP/CPI/FOMC)
```

### 4. Liquidity Sweep tasdiqlash (~+12% WR)
```
❌ Oddiy:        narx OB ga keldi → BUY
✅ Professional: BSL/SSL sweep → displacement (3+ body) → FVG → OB ichida entry
```
Sweep bo'lmasa signal berilmaydi → "stop hunt" himoyasi.

### 5. Premium/Discount + OTE zonasi
```
Discount (<50%) → faqat BUY | Premium (>50%) → faqat SELL
OTE (62–79% Fib) ichida entry → +25% WR
```

### 6. Grok Sentiment Gate
Rule Engine BUY desa, lekin Grok "bearish sentiment / major news" desa → signal BEKOR.
```json
{"sentiment":"bullish/bearish/neutral","confidence":0-100,
 "major_news":true,"whale_activity":true,"recommendation":"proceed/caution/avoid"}
```

### 7. Partial Close (loss'ni yo'qotadi)
```
TP1 (1.5R) → 40% yopish, SL → Breakeven (bu yerdan keyin loss YO'Q)
TP2 (2.5R) → 40% yopish, trailing stop
TP3 (4R+)  → 20% runner
```

### 8. Correlation & Portfolio Heat
```
max_trades=3, max_correlated=1, max_exposure=6%
XAUUSD+XAGUSD / EURUSD+GBPUSD — bir vaqtda YO'Q
```

### 9. Backtesting standarti
```
Min 3 yil data (2022–2025), Walk-Forward har 6 oy, Monte Carlo 1000×
Min Sharpe 1.5, Max DD 8%. Backtest 75%+ bo'lmasa — live YO'Q.
```

### 10. Market Regime filtri
```
ADX>25 → TRENDING (BOS/CHOCH setup)
ADX<20 → RANGING (OB/FVG reversal)
oralig'i → AVOID (choppy)
```

---

## Kutilayotgan natija

| Bosqich | Win Rate | R:R | EV |
|---|---|---|---|
| Hozirgi (AI only) | ~55% | 1:1.5 | +0.3R |
| + MTF alignment | ~65% | 1:2 | +1.0R |
| + Liquidity sweep | ~72% | 1:2.5 | +1.5R |
| + Kill Zone | ~78% | 1:2.5 | +1.95R |
| + Session + News + Sentiment | **~83%** | 1:3 | **+2.49R** |

---

## Amalga oshirish tartibi (prioritet)

1. ✅ **Grok AI konversiyasi** — bajarildi (`src/ai_client.py`)
2. ⬜ MTF Alignment engine (`src/mtf.py`) — 2–3 kun
3. ⬜ Liquidity Sweep confirmation — 3–4 kun
4. ⬜ Kill Zone filtri (`src/session.py`) — 1 kun
5. ⬜ Partial Close (TP1→Breakeven) `src/exchange_trade.py` — 1–2 kun
6. ⬜ Grok Sentiment Gate — 2 kun
7. ⬜ News filter (economic calendar API) — 2 kun
8. ⬜ PostgreSQL + TimescaleDB migratsiya — 3–5 kun
9. ⬜ ML ensemble (XGBoost/LightGBM) — 1–2 hafta
