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
        if config.BINANCE_TESTNET:
            # Route all trading calls to testnet.binancefuture.com (fake money, real path).
            _client.set_sandbox_mode(True)
    return _client


def _perp_symbol(raw: str) -> str:
    """ccxt USDT-M perpetual id, e.g. 'BTC/USDT' -> 'BTC/USDT:USDT'."""
    return raw if ":" in raw else f"{raw}:{raw.split('/')[1]}"


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


def _split_qty(ex, symbol: str, total: float) -> list[float]:
    """Split total qty across TP_SPLITS, exchange-rounded. Last leg gets the remainder so
    the parts always sum to `total`. Returns [] if any leg rounds to zero (too small to split)."""
    qtys, allocated = [], 0.0
    for i, frac in enumerate(config.TP_SPLITS):
        if i == len(config.TP_SPLITS) - 1:
            q = float(ex.amount_to_precision(symbol, total - allocated))
        else:
            q = float(ex.amount_to_precision(symbol, total * frac))
        qtys.append(q)
        allocated += q
    return qtys if all(q > 0 for q in qtys) else []


def _execute_futures(sig: dict) -> dict:
    """Futures market open (BUY=long / SELL=short) + reduceOnly SL and partial TP1/TP2/TP3.
    Both directions. If the stop-loss cannot be placed, the position is closed immediately
    (never hold an unprotected/naked position)."""
    ex = client()
    raw = sig["symbol"]                         # e.g. "BTC/USDT"
    symbol = _perp_symbol(raw)                  # ccxt perp id "BTC/USDT:USDT"
    quote = raw.split("/")[1]
    short = sig.get("signal") == "short" or sig.get("side") == "short"
    entry, sl = float(sig["entry"]), float(sig["stop_loss"])
    tps = [float(sig["tp1"]), float(sig["tp2"]), float(sig["tp3"])]

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

    # ── CRITICAL: stop-loss first. If it fails, close the position — never go naked. ──
    try:
        sl_order = ex.create_order(symbol, "STOP_MARKET", close_side, got, None,
                                   {"stopPrice": ex.price_to_precision(symbol, sl), "reduceOnly": True})
        sl_order_id = str(sl_order.get("id") or "") or None
    except Exception as exc:
        try:
            ex.create_order(symbol, "market", close_side, got, None, {"reduceOnly": True})
            return {"ok": False, "error": f"SL qo'yilmadi — pozitsiya darhol yopildi (himoyasiz qoldirilmadi): {exc}"}
        except Exception as exc2:
            return {"ok": False, "error": f"⚠️ SL qo'yilmadi VA yopib bo'lmadi — QO'LDA yoping! {symbol}: {exc2}",
                    "naked": True, "qty": got, "side": "short" if short else "long"}

    # ── Best-effort: partial take-profits (position is already protected by the SL). ──
    warn = None
    legs = _split_qty(ex, symbol, got)
    try:
        if legs:
            for lvl, q in zip(tps, legs):
                if q <= 0:
                    continue
                ex.create_order(symbol, "TAKE_PROFIT_MARKET", close_side, q, None,
                                {"stopPrice": ex.price_to_precision(symbol, lvl), "reduceOnly": True})
        else:
            # Too small to split — single TP at TP2 for the full size.
            ex.create_order(symbol, "TAKE_PROFIT_MARKET", close_side, got, None,
                            {"stopPrice": ex.price_to_precision(symbol, tps[1]), "reduceOnly": True})
    except Exception as exc:
        warn = f"TP qo'yilmadi (SL bor, pozitsiya himoyalangan): {exc}"

    res = {"ok": True, "oco": warn is None, "qty": got, "fill": filled, "oco_id": None,
           "sl_order_id": sl_order_id, "side": "short" if short else "long", "leverage": config.LEVERAGE}
    if warn:
        res["warn"] = warn
    return res


def move_stop_to_breakeven(row: dict) -> dict:
    """Cancel the existing stop and place a new reduceOnly stop at entry (breakeven).
    Called after TP1 fills so a runner can no longer turn into a loss. Futures only."""
    if config.BINANCE_MARKET != "future":
        return {"ok": False, "error": "breakeven move only supported on futures"}
    ex = client()
    raw = row["symbol"]
    symbol = _perp_symbol(raw)
    short = row.get("side") == "short"
    close_side = "buy" if short else "sell"
    entry, qty = float(row["entry"]), float(row["qty"] or 0)
    if qty <= 0:
        return {"ok": False, "error": "no qty on record"}
    # TP1 (the first split) has already filled, so only the runner remains — size the new
    # stop to the remaining qty so the reduceOnly order is never larger than the position.
    remaining = float(ex.amount_to_precision(symbol, qty * (1 - config.TP_SPLITS[0])))
    if remaining <= 0:
        remaining = qty
    # Cancel old stop (best effort — it may already be gone).
    old = row.get("sl_order_id")
    if old:
        try:
            ex.cancel_order(old, symbol)
        except Exception as exc:
            print(f"[trade] cancel old SL #{row['id']} warning: {exc}")
    try:
        new_sl = ex.create_order(symbol, "STOP_MARKET", close_side, remaining, None,
                                 {"stopPrice": ex.price_to_precision(symbol, entry), "reduceOnly": True})
        return {"ok": True, "sl_order_id": str(new_sl.get("id") or "") or None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def list_open_positions() -> dict:
    """Map of ccxt symbol -> {'side','qty','entry'} for all non-zero futures positions.
    Used to reconcile the journal with reality after a restart."""
    if config.BINANCE_MARKET != "future":
        return {}
    ex = client()
    out = {}
    for p in ex.fetch_positions():
        contracts = float(p.get("contracts") or 0)
        if contracts == 0:
            continue
        out[p["symbol"]] = {
            "side": p.get("side") or ("short" if contracts < 0 else "long"),
            "qty": abs(contracts),
            "entry": float(p.get("entryPrice") or 0),
        }
    return out


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
