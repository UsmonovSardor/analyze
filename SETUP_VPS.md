# VPS Deploy — 24/7 Binance bilan

Railway Binance'ni bloklaydi (451). To'liq ishlash (avto savdo + /balance) uchun
botni Binance ochiq VPS'da ishlatamiz.

## 1. VPS talablari

- **Region:** Binance ochiq joy (EU: Germaniya/Niderlandiya/Finlandiya, yoki Osiyo: Singapur/Yaponiya, yoki Uzbekistan). **US datacenter EMAS.**
- **Specs:** 1 vCPU, 1-2 GB RAM, 20 GB disk — yetarli (~$3-6/oy)
- **OS:** Ubuntu 22.04 / 24.04

## 2. Binance ulanishini tekshirish (eng muhim — birinchi qadam)

VPS'ga SSH bilan kiring va:
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://api.binance.com/api/v3/ping
```
- `200` → Binance ochiq ✅ davom eting
- `451` → bu region bloklangan ❌ boshqa region/provider tanlang

## 3. O'rnatish

```bash
# Docker
curl -fsSL https://get.docker.com | sh

# Kod
git clone https://github.com/UsmonovSardor/analyze.git ~/bot && cd ~/bot

# .env yarating (kalitlarni qo'ying)
nano .env
```

`.env` ichiga:
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=-1004297365894
CLAUDE_CODE_OAUTH_TOKEN=...
BINANCE_API_KEY=...        # YANGI key: Spot Trading + IP cheklov (VPS IP)
BINANCE_API_SECRET=...
TRADING_MODE=semi          # semi = tugma bilan tasdiq; off = faqat signal
MAX_TRADE_QUOTE=15         # bitta savdo max USDT
DAILY_LOSS_STOP_R=-3
```

```bash
# Ishga tushirish
docker compose up -d --build

# Loglar
docker compose logs -f
```

## 4. Railway'ni pauza qiling

Ikkita bot bitta token bilan ishlamaydi (Telegram konflikt). VPS ishga tushgach
Railway service'ni pauza qiling (dashboard → Settings → pause).

## 5. Binance API key (savdo uchun)

VPS IP'sini bilgach, Binance'da YANGI key yarating:
- ✅ Enable Reading + ✅ Enable Spot Trading, ❌ Withdrawals
- **Restrict access to trusted IPs** → VPS IP'sini qo'shing (majburiy)

## Yangilash

```bash
cd ~/bot && git pull && docker compose up -d --build
```
