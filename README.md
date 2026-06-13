# Trading Signal Bot (shaxsiy)

Crypto spot swing-trading signal tizimi: 24/7 screener → Claude tahlil → risk filtri → Telegram.
Faqat signal beradi, avtomatik savdo qilmaydi.

## Arxitektura

1. **Screener** (`src/screener.py`) — har 15 daqiqada 15 ta juftlikni tekshiradi, Claude'siz.
2. **Claude tahlil** (`src/analyzer.py`) — faqat nomzod setup topilganda chaqiriladi.
   Strategiya bilimlari `skill/` papkasida — o'zgartirsangiz bot darhol yangi qoidalar bilan ishlaydi.
3. **Risk engine** (`src/risk.py`) — model taklifini deterministik tekshiradi (R:R, score, narx).
4. **Telegram** — signal, TP/SL urilganda yangilanish, haftalik statistika.
5. **Jurnal** (`journal.db`) — har signal va natijasi saqlanadi.

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

## Railway deploy

1. Repo'ni GitHub'ga push qiling, Railway'da New Project → Deploy from GitHub.
2. Dockerfile avtomatik aniqlanadi.
3. **Volume** qo'shing, mount path: `/data` (jurnal o'chib ketmasligi uchun).
4. Variables: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, va `CLAUDE_CODE_OAUTH_TOKEN`
   (lokal terminalda `claude setup-token` bajaring va chiqqan tokenni qo'ying)
   yoki `ANTHROPIC_API_KEY`.

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

## Jonli savdo (Binance, ixtiyoriy)

`.env`da `BINANCE_API_KEY`/`SECRET` to'ldirilsa, signal ostida **✅ Bajarish /
❌ O'tkazib yuborish** tugmalari chiqadi (semi rejim). Bajarish bosilganda:
market buy + OCO (TP2/SL) order qo'yiladi. OCO Binance serverida turadi, shuning
uchun bot o'chsa ham stop-loss ishlaydi.

- API key: **faqat Spot Trading**, Withdrawal **o'chirilgan**.
- `TRADING_MODE`: `semi` (tugma bilan tasdiq) | `auto` | `off`.
- Himoyalar: `RISK_PER_TRADE` (1%), `MAX_TRADE_QUOTE` (USDT cap), `DAILY_LOSS_STOP_R` (-3R).
- ⚠️ `api.binance.com` Railway US IP'dan bloklangan — savdoni Binance'ga ulanadigan
  joydan (Mac yoki UZ VPS) ishga tushiring. Signal/hisobot Railway'da qoladi.

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
