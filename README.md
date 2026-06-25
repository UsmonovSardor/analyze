# Trading Signal Bot (shaxsiy)

Ko'p bozorli (crypto · forex · oltin · aksiya) swing-trading signal tizimi:
24/7 screener → **Gemini AI** tahlil → risk filtri → Telegram. Har ikki yo'nalish
(🟢 LONG va 🔻 SHORT). Ixtiyoriy: Binance Futures'da avto/qo'lda savdo.

## Arxitektura

1. **Screener** (`src/screener_tv.py` + `src/screener.py`) — har 15 daqiqada 40+ instrumentni
   tekshiradi (TradingView ma'lumotlari), AI'siz. Long va short nomzodlarni topadi.
2. **Gemini tahlil** (`src/analyzer.py`) — faqat nomzod setup topilganda chaqiriladi.
   Strategiya bilimlari `skill/` papkasida — o'zgartirsangiz bot darhol yangi qoidalar bilan ishlaydi.
3. **Risk engine** (`src/risk.py`) — model taklifini deterministik tekshiradi (R:R, score, narx, long/short tartibi).
4. **Telegram** — signal + grafik, TP/SL urilganda yangilanish + natija grafigi, haftalik statistika.
5. **Savdo** (`src/exchange_trade.py`) — ixtiyoriy. Binance Futures (long+short) yoki spot (faqat long).
6. **Jurnal** (`journal.db`) — har signal, yo'nalishi va natijasi saqlanadi.

## Lokal test

```bash
cd trading-signal-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # to'ldiring
set -a; source .env; set +a
python -m src.main
```

Telegram sozlanmagan bo'lsa xabarlar konsolga chiqadi — xavfsiz test rejimi.

## Deploy

Avto savdo Binance'ga ulanishni talab qiladi. `api.binance.com` / `fapi.binance.com`
ba'zi datsentrlardan (jumladan Railway US IP) **451 bilan bloklangan**. Shuning uchun
avto savdo uchun **Hetzner EU server** tavsiya etiladi (Binance'ga ulanadi).

### Hetzner (yoki boshqa Binance'ga ulanadigan server) — avto savdo bilan
```bash
git clone <repo> && cd trading-signal-bot
cp .env.example .env   # to'ldiring (pastdagi o'zgaruvchilar)
docker compose up -d --build
```

### Railway — faqat signal (avto savdo 451 blok)
1. GitHub'ga push → Railway'da New Project → Deploy from GitHub. Dockerfile aniqlanadi.
2. **Volume** qo'shing, mount path: `/data` (jurnal o'chib ketmasligi uchun).

### Muhim env o'zgaruvchilar
| O'zgaruvchi | Tavsif |
|---|---|
| `GEMINI_API_KEY` | **Majburiy** — AI tahlil (Google AI Studio, bepul tier) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Telegram yetkazib berish |
| `BINANCE_API_KEY`, `BINANCE_API_SECRET` | Ixtiyoriy — savdo (Futures ruxsati, **Withdrawal o'chirilgan**) |
| `BINANCE_MARKET` | `future` (long+short, standart) yoki `spot` (faqat long) |
| `LEVERAGE` | Futures plecho (standart `3`, past tuting) |
| `TRADING_MODE` | `semi` (tugma bilan tasdiq) · `auto` · `off` |
| `MIN_SCORE` | Minimal ishonch (standart `6`) |
| `ALLOW_SHORTS` | `true`/`false` (standart `true`) |

## Telegram sozlash

1. [@BotFather](https://t.me/BotFather) → `/newbot` → token oling.
2. Gruppa oching, botni qo'shib admin qiling.
3. Gruppada bitta xabar yozing, so'ng chat ID ni oling:
   `curl https://api.telegram.org/bot<TOKEN>/getUpdates` → `"chat":{"id":-100...}`.

## Sozlamalar

Hammasi `src/config.py` da: juftliklar ro'yxati, skan oraliq, kunlik signal limiti,
minimal score (7/10), minimal R:R (TP2 gacha 1:2), Claude kunlik chaqiruv byudjeti.

## Backtest (strategiyani tarixda sinash)

```bash
python -m src.backtest                 # barcha juftliklar, 120 kun
python -m src.backtest BTC/USDT 180    # bitta juftlik, 180 kun
```

Bu deterministik qatlam (screener + risk qoidalari) bo'yicha sinaydi — Claude'siz,
shuning uchun jonli natijaga nisbatan konservativ baho. "Asosiy edge bormi?" degan
savolga javob beradi.

## Jonli savdo (Binance Futures, ixtiyoriy)

`.env`da `BINANCE_API_KEY`/`SECRET` to'ldirilsa, har signal ostida tugmalar chiqadi:
**🤖 Avto savdo · ✍️ Qo'lda savdo · 👁️ Kuzatish**.

- **🤖 Avto** — AI o'zi order ochadi: Futures market open (long=BUY / short=SELL) +
  reduceOnly TP (TP2) va SL orderlari. Bu orderlar Binance serverida turadi, bot o'chsa ham ishlaydi.
- **✍️ Qo'lda** — botning aniq rejasi (entry/SL/TP) yuboriladi, siz orderni o'zingiz kiritasiz.
- **👁️ Kuzatish** — order ochilmaydi, lekin TP/SL natijalari kuzatiladi.

Sozlamalar:
- API key: **Enable Futures** ruxsati, Withdrawal **o'chirilgan**.
- `BINANCE_MARKET=future` (long+short) yoki `spot` (faqat long, OCO bilan).
- `TRADING_MODE`: `semi` (tugma bilan tasdiq) | `auto` (avtomatik) | `off`.
- Himoyalar: `RISK_PER_TRADE` (1%), `MAX_TRADE_QUOTE` (margin cap), `LEVERAGE`, `DAILY_LOSS_STOP_R` (-3R).
- ⚠️ Binance ba'zi serverlardan 451 bloklangan — savdoni Binance'ga ulanadigan
  serverdan (Hetzner EU) ishga tushiring. Ma'lumot olish (`data-api.binance.vision`) hamma joyda ishlaydi.

## Hisobotlar

Har signal: qaysi strategiya (Trend Pullback / Range Breakout), entry/SL/TP1-3 (R va %),
confluence scorecard (har omil bo'yicha ball), asoslash, bozor konteksti. Yopilganda
natija R bilan, har hafta strategiya bo'yicha win-rate.

## Feedback loop

Har skanda oxirgi 30 kunlik strategiya statistikasi Claude'ga uzatiladi — kam ishlayotgan
setup uchun bot avtomatik talabchanroq bo'ladi.

## Muhim

- Avval kamida 2-4 hafta kuzating (paper-trading) — haftalik hisobotdagi win-rate va
  jami R musbat barqaror bo'lmaguncha real pul ishlatmang.
- Hech bir AI bozorni bashorat qilmaydi; bu tizim ehtimollik + qattiq risk boshqaruvi.
