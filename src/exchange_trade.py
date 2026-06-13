"""Authenticated Binance spot trading. Optional — only active when API keys are set.

SAFETY:
- Spot only, BUY to open, OCO SELL (take-profit + stop-loss) to protect.
- Position size = RISK_PER_TRADE of quote balance, hard-capped by MAX_TRADE_QUOTE.
- Withdrawals are never called. Create the API key WITHOUT withdrawal permission.

NOTE: api.binance.com is geo-blocked from some datacenters (HTTP 451). If the host
cannot reach Binance, execution returns an error string and posts it to Telegram —
run the executor from a Binance-reachable location. The OCO order, once placed, lives
on Binance's servers, so the stop-loss stays active even if this bot goes offline.
"""
import ccxt

from . import config

_client = None


def client():
    global _client
    if _client is None:
        _client = ccxt.binance({
            "apiKey": config.BINANCE_API_KEY,
            "secret": config.BINANCE_API_SECRET,
            "enableRateLimit": True,
            "options": {"defaultType": "spot", "adjustForTimeDifference": True},
        })
    return _client


def quote_balance(quote: str = "USDT") -> float:
    bal = client().fetch_balance()
    return float(bal.get("free", {}).get(quote, 0) or 0)


def portfolio() -> dict:
    """Read-only snapshot of spot balances valued in USDT. Works only where Binance
    is reachable (the Mac); returns a 451 note otherwise."""
    from .data import _exchange as price_src
    try:
        bal = client().fetch_balance()
    except ccxt.BaseError as exc:
        msg = str(exc)
        if "451" in msg or "restricted location" in msg:
            return {"ok": False, "error": "Binance bu serverdan bloklangan (451). "
                    "Balansni ko'rish uchun botni Mac'da ishga tushiring."}
        return {"ok": False, "error": msg[:200]}

    holdings, total = [], 0.0
    for asset, amount in bal.get("total", {}).items():
        if not amount or amount <= 0:
            continue
        if asset in ("USDT", "USDC", "FDUSD", "BUSD"):
            usd = float(amount)
        else:
            try:
                usd = float(amount) * float(price_src.fetch_ticker(f"{asset}/USDT")["last"])
            except Exception:
                usd = 0.0
        total += usd
        holdings.append({"asset": asset, "amount": float(amount), "usd": usd})
    holdings.sort(key=lambda h: h["usd"], reverse=True)
    return {"ok": True, "holdings": holdings, "total_usd": total}


def _round_amount(symbol: str, amount: float) -> float:
    return float(client().amount_to_precision(symbol, amount))


def _round_price(symbol: str, price: float) -> float:
    return float(client().price_to_precision(symbol, price))


def execute_signal(sig: dict) -> dict:
    """Market-buy then place an OCO (TP2 / SL) sell. Returns a result dict."""
    ex = client()
    symbol = sig["symbol"]
    quote = symbol.split("/")[1]
    entry, sl, tp2 = float(sig["entry"]), float(sig["stop_loss"]), float(sig["tp2"])

    try:
        free = quote_balance(quote)
        risk_quote = min(free * config.RISK_PER_TRADE, config.MAX_TRADE_QUOTE)
        # size so that a stop-out loses ~risk_quote; bounded by available balance
        stop_frac = (entry - sl) / entry
        notional = min(risk_quote / stop_frac, free, config.MAX_TRADE_QUOTE)
        if notional < 10:  # Binance min notional
            return {"ok": False, "error": f"notional {notional:.2f} {quote} < 10 minimum"}
        amount = _round_amount(symbol, notional / entry)

        buy = ex.create_order(symbol, "market", "buy", amount)
        filled = float(buy.get("average") or buy.get("price") or entry)
        got = float(buy.get("filled") or amount)

        oco_id = None
        try:
            oco = ex.private_post_order_oco({
                "symbol": ex.market_id(symbol),
                "side": "SELL",
                "quantity": ex.amount_to_precision(symbol, got),
                "price": ex.price_to_precision(symbol, tp2),            # take-profit limit
                "stopPrice": ex.price_to_precision(symbol, sl),          # stop trigger
                "stopLimitPrice": ex.price_to_precision(symbol, sl * 0.999),
                "stopLimitTimeInForce": "GTC",
            })
            oco_id = str(oco.get("orderListId", "")) or None
        except Exception as exc:  # entry filled but OCO failed — must warn loudly
            return {"ok": True, "oco": False, "qty": got, "fill": filled,
                    "warn": f"OCO qo'yilmadi: {exc}"}

        return {"ok": True, "oco": True, "qty": got, "fill": filled, "oco_id": oco_id}
    except ccxt.BaseError as exc:
        msg = str(exc)
        if "451" in msg or "restricted location" in msg:
            return {"ok": False, "error": "Binance ushbu serverdan bloklangan (451). "
                    "Savdoni Binance'ga ulanadigan joydan ishga tushiring."}
        return {"ok": False, "error": msg[:300]}
