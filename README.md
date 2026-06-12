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

## Muhim

- Avval kamida 2-4 hafta kuzating (paper-trading) — haftalik hisobotdagi win-rate va
  jami R musbat barqaror bo'lmaguncha real pul ishlatmang.
- Hech bir AI bozorni bashorat qilmaydi; bu tizim ehtimollik + qattiq risk boshqaruvi.
