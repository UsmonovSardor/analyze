"""TradingView-based screener using tradingview-ta.

Covers crypto, stocks, forex, indices — any instrument on TradingView.
Runs 24/7 without Claude as a cheap pre-filter, same role as screener.py
but with TradingView data instead of raw ccxt OHLCV.

Setup types returned:
  'A'  — pullback to EMA50 in 4H uptrend (same as original)
  'B'  — strong buy confluence across multiple TV indicators
  'TV' — 4H STRONG_BUY alignment (trend continuation)
"""

from tradingview_ta import TA_Handler, Interval
import time
import traceback

_TF_MAP = {
    "1h":  Interval.INTERVAL_1_HOUR,
    "4h":  Interval.INTERVAL_4_HOURS,
    "1d":  Interval.INTERVAL_1_DAY,
    "15m": Interval.INTERVAL_15_MINUTES,
}

_TV_REQUEST_DELAY = 3.0   # seconds between TradingView API calls (avoid 429)


def get_tv_analysis(symbol: str, exchange: str, screener: str, timeframe: str = "1h"):
    """Fetch TradingView analysis. Returns None on 429 (caller should skip symbol)."""
    time.sleep(_TV_REQUEST_DELAY)
    handler = TA_Handler(
        symbol=symbol,
        screener=screener,
        exchange=exchange,
        interval=_TF_MAP.get(timeframe, Interval.INTERVAL_1_HOUR),
    )
    return handler.get_analysis()


def find_candidate_tv(tv_sym: dict):
    """
    tv_sym format:
      {"symbol": "BTCUSDT", "exchange": "BINANCE", "screener": "crypto"}
    For stocks:
      {"symbol": "AAPL", "exchange": "NASDAQ", "screener": "america"}
    For forex:
      {"symbol": "EURUSD", "exchange": "FX", "screener": "forex"}

    Returns a dict {"setup": "A"|"B"|"TV", "side": "long"|"short"} or None.
    Detects both LONG (uptrend) and SHORT (downtrend) candidates.
    """
    from . import config

    try:
        e   = get_tv_analysis(tv_sym["symbol"], tv_sym["exchange"], tv_sym["screener"], "1h")
        ctx = get_tv_analysis(tv_sym["symbol"], tv_sym["exchange"], tv_sym["screener"], "4h")
    except Exception as _exc:
        msg = str(_exc)
        if "429" in msg:
            # Rate limited — re-raise so the caller can back off / fall back to ccxt.
            raise
        print(f"[screener_tv] {tv_sym['symbol']} fetch error: {type(_exc).__name__}: {_exc}")
        return None

    ei = e.indicators
    ci = ctx.indicators

    close_1h  = ei.get("close",   0)
    ema50_1h  = ei.get("EMA50",   0)
    ema200_1h = ei.get("EMA200",  0)
    rsi_1h    = ei.get("RSI",    50)
    atr_1h    = ei.get("ATR",    abs(close_1h - ema50_1h) * 0.5 + 0.001)
    stoch_k   = ei.get("Stoch.K", 50)

    close_4h  = ci.get("close",  0)
    ema50_4h  = ci.get("EMA50",  0)
    ema200_4h = ci.get("EMA200", 0)

    uptrend_4h   = close_4h > ema200_4h and ema50_4h > ema200_4h
    downtrend_4h = close_4h < ema200_4h and ema50_4h < ema200_4h

    buy_1h  = e.summary.get("BUY", 0)
    sell_1h = e.summary.get("SELL", 0)
    rec_1h  = e.summary.get("RECOMMENDATION", "")
    buy_4h  = ctx.summary.get("BUY", 0)
    sell_4h = ctx.summary.get("SELL", 0)
    rec_4h  = ctx.summary.get("RECOMMENDATION", "")

    # ── Non-crypto (forex/gold/stocks): moderate 1h+4h agreement ──────────
    # These instruments trend slower and rarely hit the strict crypto counts,
    # so require both timeframes to agree instead. Gemini still gates quality.
    if tv_sym.get("screener") != "crypto":
        # Side must not fight the 4h EMA trend — Gemini hard-rejects counter-trend.
        if not downtrend_4h and (rec_1h in ("BUY", "STRONG_BUY")
                and rec_4h in ("BUY", "STRONG_BUY") and buy_1h >= 6 and rsi_1h < 70):
            return {"setup": "TV", "side": "long"}
        if config.ALLOW_SHORTS and not uptrend_4h and (rec_1h in ("SELL", "STRONG_SELL")
                and rec_4h in ("SELL", "STRONG_SELL") and sell_1h >= 6 and rsi_1h > 30):
            return {"setup": "TV", "side": "short"}
        # Pullback rally inside a 4h downtrend (oscillators turn buy-ish while the
        # EMA trend stays down) — classic short entry, mirror for longs.
        if config.ALLOW_SHORTS and downtrend_4h and rsi_1h > 45 and buy_1h >= 5:
            return {"setup": "A", "side": "short"}
        if uptrend_4h and rsi_1h < 55 and sell_1h >= 5:
            return {"setup": "A", "side": "long"}

    # ── LONG candidates (uptrend) ──────────────────────────────────────────
    # Setup A: pullback to EMA50 in uptrend
    if uptrend_4h and ema50_1h > 0 and atr_1h > 0:
        near_ema50 = abs(close_1h - ema50_1h) <= 1.5 * atr_1h  # wider zone
        rsi_reset  = rsi_1h < 60 and stoch_k < 60
        if near_ema50 and rsi_reset:
            return {"setup": "A", "side": "long"}

    # Setup B: strong buy momentum
    if uptrend_4h and buy_1h >= 8 and rec_1h in ("STRONG_BUY", "BUY") and rsi_1h < 72:
        return {"setup": "B", "side": "long"}

    # TV: strong 4h + 1h alignment
    if rec_4h in ("STRONG_BUY", "BUY") and buy_4h >= 10 and buy_1h >= 7 and rsi_1h < 68:
        return {"setup": "TV", "side": "long"}

    # Near EMA200 support bounce in any context
    if ema200_1h > 0 and abs(close_1h - ema200_1h) <= 1.0 * atr_1h and buy_1h >= 6:
        return {"setup": "B", "side": "long"}

    # ── SHORT candidates (downtrend) — mirror logic ────────────────────────
    if config.ALLOW_SHORTS:
        # Setup A: bounce to EMA50 resistance in downtrend
        if downtrend_4h and ema50_1h > 0 and atr_1h > 0:
            near_ema50 = abs(close_1h - ema50_1h) <= 1.5 * atr_1h
            rsi_reset  = rsi_1h > 40 and stoch_k > 40
            if near_ema50 and rsi_reset:
                return {"setup": "A", "side": "short"}

        # Setup B: strong sell momentum
        if downtrend_4h and sell_1h >= 8 and rec_1h in ("STRONG_SELL", "SELL") and rsi_1h > 28:
            return {"setup": "B", "side": "short"}

        # TV: strong 4h + 1h sell alignment
        if rec_4h in ("STRONG_SELL", "SELL") and sell_4h >= 10 and sell_1h >= 7 and rsi_1h > 32:
            return {"setup": "TV", "side": "short"}

        # Near EMA200 resistance rejection in any context
        if ema200_1h > 0 and abs(close_1h - ema200_1h) <= 1.0 * atr_1h and sell_1h >= 6:
            return {"setup": "B", "side": "short"}

    return None


def btc_context_ok_tv() -> bool:
    """BTC 4H trend check via TradingView (fallback: True if TV is down)."""
    try:
        a = get_tv_analysis("BTCUSDT", "BINANCE", "crypto", "4h")
        close  = a.indicators.get("close",  0)
        ema200 = a.indicators.get("EMA200", 0)
        ema50  = a.indicators.get("EMA50",  0)
        return not (close < ema200 and ema50 < ema200)
    except Exception as exc:
        if "429" not in str(exc):
            print(f"[screener_tv] BTC context error: {exc}")
        return True  # fallback: allow scanning


def tv_symbol_to_ccxt(tv_sym: dict) -> str | None:
    """Convert TV symbol dict to ccxt format (crypto only).
    Returns None for non-crypto instruments.
    """
    if tv_sym.get("screener") != "crypto":
        return None
    raw = tv_sym["symbol"].upper()
    if raw.endswith("USDT"):
        base = raw[:-4]
        return f"{base}/USDT"
    if raw.endswith("USDC"):
        base = raw[:-4]
        return f"{base}/USDC"
    if raw.endswith("BTC"):
        base = raw[:-3]
        return f"{base}/BTC"
    return None
