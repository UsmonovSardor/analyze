"""Authenticated Binance trading. Optional — only active when API keys are set.

Two modes (config.BINANCE_MARKET):
  - "future"  USDT-M perpetuals. Supports LONG and SHORT. Uses leverage.
              TP/SL placed as reduceOnly STOP_MARKET / TAKE_PROFIT_MARKET orders that
              live on Binance's servers, so they stay active even if the bot goes offline.
  - "spot"    Spot market, LONG only (BUY + OCO SELL). Shorts are rejected.

SAFETY:
- Position size targets ~RISK_PER_TRADE of the quote balance at the stop, hard-capped
  by MAX_TRADE_QUOTE (margin) × leverage in notional terms.
- Withdrawals are never called. Create the API key WITHOUT withdrawal permission.
- Futures key needs "Enable Futures" permission.

NOTE: Binance is geo-blocked from some datacenters (HTTP 451). Run the executor from a
Binance-reachable location (e.g. a Hetzner EU server). Data fetching uses the public
vision endpoint and is not affected.
"""
import ccxt

from . import config

_client = None


def client():
    global _client
    if _client is None:
        opts = {
            "apiKey": config.BINANCE_API_KEY,
            "secret": config.BINANCE_API_SECRET,
            "enableRateLimit": True,
            "options": {
                "defaultType": config.BINANCE_MARKET,  # "future" or "spot"
                "adjustForTimeDifference": True,
            },
        }
        if config.BINANCE_HOSTNAME:
            opts["hostname"] = config.BINANCE_HOSTNAME
        _client = ccxt.binance(opts)
    return _client


def _fetch_balance_safe() -> dict:
    """Fetch balance without triggering margin/currency endpoints."""
    return client().fetch_balance({"type": config.BINANCE_MARKET})


def quote_balance(quote: str = "USDT") -> float:
    bal = _fetch_balance_safe()
    return float(bal.get("free", {}).get(quote, 0) or 0)


def portfolio() -> dict:
    """Read-only snapshot of balances valued in USDT. Returns a 451 note where blocked."""
    from .data import _exchange as price_src
    try:
        bal = _fetch_balance_safe()
    except ccxt.BaseError as exc:
        msg = str(exc)
        if "451" in msg or "restricted location" in msg:
            return {"ok": False, "error": "Binance bu serverdan bloklangan (451). "
                    "Balansni ko'rish uchun botni Binance'ga ulanadigan serverda ishga tushiring."}
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


def _sizing(free: float, entry: float, sl: float) -> float:
    """Notional (in quote) so a stop-out loses ~RISK_PER_TRADE of balance, bounded by caps."""
    stop_frac = abs(entry - sl) / entry
    if stop_frac <= 0:
        return 0.0
    risk_quote = min(free * config.RISK_PER_TRADE, config.MAX_TRADE_QUOTE)
    lev = max(1, config.LEVERAGE) if config.BINANCE_MARKET == "future" else 1
    max_notional = config.MAX_TRADE_QUOTE * lev
    notional = risk_quote / stop_frac
    return min(notional, free * lev, max_notional)


def _execute_spot_long(sig: dict) -> dict:
    """Spot market BUY + OCO (TP2/SL) sell. LONG only."""
    ex = client()
    symbol = sig["symbol"]
    quote = symbol.split("/")[1]
    entry, sl, tp2 = float(sig["entry"]), float(sig["stop_loss"]), float(sig["tp2"])

    free = quote_balance(quote)
    notional = _sizing(free, entry, sl)
    if notional < 10:
        return {"ok": False, "error": f"notional {notional:.2f} {quote} < 10 minimum"}
    amount = float(ex.amount_to_precision(symbol, notional / entry))

    buy = ex.create_order(symbol, "market", "buy", amount)
    filled = float(buy.get("average") or buy.get("price") or entry)
    got = float(buy.get("filled") or amount)

    try:
        oco = ex.private_post_order_oco({
            "symbol": ex.market_id(symbol),
            "side": "SELL",
            "quantity": ex.amount_to_precision(symbol, got),
            "price": ex.price_to_precision(symbol, tp2),
            "stopPrice": ex.price_to_precision(symbol, sl),
            "stopLimitPrice": ex.price_to_precision(symbol, sl * 0.999),
            "stopLimitTimeInForce": "GTC",
        })
        oco_id = str(oco.get("orderListId", "")) or None
    except Exception as exc:
        return {"ok": True, "oco": False, "qty": got, "fill": filled,
                "warn": f"OCO qo'yilmadi: {exc}"}
    return {"ok": True, "oco": True, "qty": got, "fill": filled, "oco_id": oco_id}


def _execute_futures(sig: dict) -> dict:
    """Futures market open (BUY=long / SELL=short) + reduceOnly TP & SL. Both directions."""
    ex = client()
    raw = sig["symbol"]                         # e.g. "BTC/USDT"
    symbol = raw if ":" in raw else f"{raw}:{raw.split('/')[1]}"  # ccxt perp id "BTC/USDT:USDT"
    quote = raw.split("/")[1]
    short = sig.get("signal") == "short" or sig.get("side") == "short"
    entry, sl, tp2 = float(sig["entry"]), float(sig["stop_loss"]), float(sig["tp2"])

    try:
        ex.set_leverage(config.LEVERAGE, symbol)
    except Exception as exc:
        print(f"[trade] set_leverage warning {symbol}: {exc}")

    free = quote_balance(quote)
    notional = _sizing(free, entry, sl)
    if notional < 5:
        return {"ok": False, "error": f"notional {notional:.2f} {quote} < 5 minimum (futures)"}
    amount = float(ex.amount_to_precision(symbol, notional / entry))

    open_side = "sell" if short else "buy"
    close_side = "buy" if short else "sell"

    order = ex.create_order(symbol, "market", open_side, amount)
    filled = float(order.get("average") or order.get("price") or entry)
    got = float(order.get("filled") or amount)

    warn = None
    try:
        # Stop-loss (reduceOnly)
        ex.create_order(symbol, "STOP_MARKET", close_side, got, None,
                        {"stopPrice": ex.price_to_precision(symbol, sl), "reduceOnly": True})
        # Take-profit at TP2 (reduceOnly)
        ex.create_order(symbol, "TAKE_PROFIT_MARKET", close_side, got, None,
                        {"stopPrice": ex.price_to_precision(symbol, tp2), "reduceOnly": True})
    except Exception as exc:
        warn = f"TP/SL qo'yilmadi: {exc}"

    res = {"ok": True, "oco": warn is None, "qty": got, "fill": filled,
           "oco_id": None, "side": "short" if short else "long", "leverage": config.LEVERAGE}
    if warn:
        res["warn"] = warn
    return res


def execute_signal(sig: dict) -> dict:
    """Place a real order for a signal. Futures (long/short) or spot (long only)."""
    short = sig.get("signal") == "short" or sig.get("side") == "short"
    try:
        if config.BINANCE_MARKET == "future":
            return _execute_futures(sig)
        if short:
            return {"ok": False, "error": "SHORT spot'da imkonsiz. BINANCE_MARKET=future qiling."}
        return _execute_spot_long(sig)
    except ccxt.BaseError as exc:
        msg = str(exc)
        if "451" in msg or "restricted location" in msg:
            return {"ok": False, "error": "Binance ushbu serverdan bloklangan (451). "
                    "Savdoni Binance'ga ulanadigan serverdan (Hetzner EU) ishga tushiring."}
        return {"ok": False, "error": msg[:300]}
