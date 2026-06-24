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

_TV_REQUEST_DELAY = 0.6  # seconds between TradingView API calls (avoid 429)


def get_tv_analysis(symbol: str, exchange: str, screener: str, timeframe: str = "1h"):
    time.sleep(_TV_REQUEST_DELAY)
    handler = TA_Handler(
        symbol=symbol,
        screener=screener,
        exchange=exchange,
        interval=_TF_MAP.get(timeframe, Interval.INTERVAL_1_HOUR),
    )
    return handler.get_analysis()


def find_candidate_tv(tv_sym: dict) -> str | None:
    """
    tv_sym format:
      {"symbol": "BTCUSDT", "exchange": "BINANCE", "screener": "crypto"}
    For stocks:
      {"symbol": "AAPL", "exchange": "NASDAQ", "screener": "america"}
    For forex:
      {"symbol": "EURUSD", "exchange": "FX", "screener": "forex"}

    Returns 'A', 'B', 'TV', or None.
    """
    try:
        e   = get_tv_analysis(tv_sym["symbol"], tv_sym["exchange"], tv_sym["screener"], "1h")
        ctx = get_tv_analysis(tv_sym["symbol"], tv_sym["exchange"], tv_sym["screener"], "4h")
    except Exception as _exc:
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

    uptrend_4h = close_4h > ema200_4h and ema50_4h > ema200_4h

    # --- Setup A: pullback to EMA50 zone in 4H uptrend ---
    if uptrend_4h and ema50_1h > 0 and atr_1h > 0:
        near_ema50 = abs(close_1h - ema50_1h) <= 1.2 * atr_1h
        rsi_reset  = rsi_1h < 55 and stoch_k < 55
        if near_ema50 and rsi_reset:
            return "A"

    # --- Setup B: TV multi-indicator BUY alignment + uptrend ---
    if uptrend_4h:
        buy_1h = e.summary.get("BUY", 0)
        rec_1h = e.summary.get("RECOMMENDATION", "")
        if buy_1h >= 10 and rec_1h in ("STRONG_BUY", "BUY") and rsi_1h < 70:
            return "B"

    # --- Setup TV: 4H STRONG_BUY (works even without strict uptrend) ---
    buy_4h = ctx.summary.get("BUY", 0)
    rec_4h = ctx.summary.get("RECOMMENDATION", "")
    buy_1h = e.summary.get("BUY", 0)
    if rec_4h == "STRONG_BUY" and buy_4h >= 12 and buy_1h >= 8 and rsi_1h < 65:
        return "TV"

    return None


def btc_context_ok_tv() -> bool:
    """BTC 4H trend check via TradingView (fallback: True if TV is down)."""
    try:
        a = get_tv_analysis("BTCUSDT", "BINANCE", "crypto", "4h")
        close  = a.indicators.get("close",  0)
        ema200 = a.indicators.get("EMA200", 0)
        ema50  = a.indicators.get("EMA50",  0)
        return not (close < ema200 and ema50 < ema200)
    except Exception:
        return True


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
