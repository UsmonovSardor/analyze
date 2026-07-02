"""Market data + indicators from Binance public endpoints (no API key needed)."""
import os

import ccxt
import pandas as pd

# Binance blocks US IPs (HTTP 451) — set EXCHANGE=okx/bybit/kraken if the host region is restricted
_exchange = getattr(ccxt, os.getenv("EXCHANGE", "binance"))({"enableRateLimit": True, "timeout": 30000})
if _exchange.id == "binance":
    # data-api.binance.vision serves public market data without geo-restrictions;
    # load spot markets only so ccxt never touches the geo-blocked fapi/dapi endpoints
    _exchange.urls["api"]["public"] = "https://data-api.binance.vision/api/v3"
    _exchange.options["fetchMarkets"] = ["spot"]
    _exchange.options["defaultType"] = "spot"


def fetch_ohlcv(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    raw = _exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"]
    df["ema20"] = c.ewm(span=20, adjust=False).mean()
    df["ema50"] = c.ewm(span=50, adjust=False).mean()
    df["ema200"] = c.ewm(span=200, adjust=False).mean()

    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-12)
    df["rsi"] = 100 - 100 / (1 + rs)

    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - c.shift()).abs(),
            (df["low"] - c.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()

    df["vol_avg20"] = df["volume"].rolling(20).mean()
    return df


def swing_levels(df: pd.DataFrame, lookback: int = 60, window: int = 3):
    """Recent swing highs/lows for support/resistance context."""
    sub = df.tail(lookback).reset_index(drop=True)
    highs, lows = [], []
    for i in range(window, len(sub) - window):
        seg = sub.iloc[i - window : i + window + 1]
        if sub.loc[i, "high"] == seg["high"].max():
            highs.append(round(float(sub.loc[i, "high"]), 8))
        if sub.loc[i, "low"] == seg["low"].min():
            lows.append(round(float(sub.loc[i, "low"]), 8))
    return sorted(set(highs))[-6:], sorted(set(lows))[:6]


def snapshot(symbol: str, entry_tf: str, context_tf: str, candles: int) -> dict:
    """Everything the screener and Claude need for one symbol."""
    e = add_indicators(fetch_ohlcv(symbol, entry_tf, candles))
    ctx = add_indicators(fetch_ohlcv(symbol, context_tf, candles))
    res, sup = swing_levels(e)
    res4, sup4 = swing_levels(ctx, lookback=80)
    return {
        "symbol": symbol,
        "entry_tf": e,
        "context_tf": ctx,
        "tf_entry": entry_tf,
        "tf_ctx": context_tf,
        "resistance_1h": res,
        "support_1h": sup,
        "resistance_4h": res4,
        "support_4h": sup4,
    }


# ── Yahoo Finance source for forex / gold / stocks ──────────────────────────
# Produces the exact same snapshot shape as the crypto path, so the whole
# pipeline (screener → Gemini → risk → chart → outcome tracking) is shared.

_YF_CACHE: dict = {}          # ticker -> (ts, DataFrame 1h)
_YF_CACHE_TTL = 240           # seconds


def _yf_hourly(ticker: str) -> pd.DataFrame:
    import time as _t
    import yfinance as yf
    hit = _YF_CACHE.get(ticker)
    if hit and _t.time() - hit[0] < _YF_CACHE_TTL:
        return hit[1]
    raw = yf.download(ticker, interval="1h", period="90d", progress=False,
                      auto_adjust=True, multi_level_index=False)
    if raw is None or raw.empty:
        raise RuntimeError(f"yfinance: no data for {ticker}")
    df = raw.reset_index()
    ts_col = "Datetime" if "Datetime" in df.columns else "Date"
    df = df.rename(columns={ts_col: "ts", "Open": "open", "High": "high",
                            "Low": "low", "Close": "close", "Volume": "volume"})
    df = df[["ts", "open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    _YF_CACHE[ticker] = (_t.time(), df)
    return df


def _resample_4h(df1h: pd.DataFrame) -> pd.DataFrame:
    g = df1h.set_index("ts").resample("4h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["close"]).reset_index()
    return g


def _yf_interval(ticker: str, interval: str, period: str) -> pd.DataFrame:
    import time as _t
    import yfinance as yf
    key = f"{ticker}:{interval}"
    hit = _YF_CACHE.get(key)
    if hit and _t.time() - hit[0] < _YF_CACHE_TTL:
        return hit[1]
    raw = yf.download(ticker, interval=interval, period=period, progress=False,
                      auto_adjust=True, multi_level_index=False)
    if raw is None or raw.empty:
        raise RuntimeError(f"yfinance: no {interval} data for {ticker}")
    df = raw.reset_index()
    ts_col = "Datetime" if "Datetime" in df.columns else "Date"
    df = df.rename(columns={ts_col: "ts", "Open": "open", "High": "high",
                            "Low": "low", "Close": "close", "Volume": "volume"})
    df = df[["ts", "open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    _YF_CACHE[key] = (_t.time(), df)
    return df


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.set_index("ts").resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["close"]).reset_index()


def snapshot_yf(symbol: str, ticker: str, candles: int = 300,
                entry_tf: str = "1h", context_tf: str = "4h") -> dict:
    """Snapshot for non-crypto instruments — same shape as snapshot().
    Supported entry TFs: 15m (ctx 1h), 1h (ctx 4h), 4h (ctx 1d), 1d (ctx 1w)."""
    if entry_tf == "15m":
        e_df, c_df = _yf_interval(ticker, "15m", "30d"), _yf_hourly(ticker)
        context_tf = "1h"
    elif entry_tf == "4h":
        e_df, c_df = _resample_4h(_yf_hourly(ticker)), _yf_interval(ticker, "1d", "2y")
        context_tf = "1d"
    elif entry_tf == "1d":
        d = _yf_interval(ticker, "1d", "2y")
        e_df, c_df = d, _resample(d, "1W")
        context_tf = "1w"
    else:
        entry_tf = "1h"
        e_df, c_df = _yf_hourly(ticker), _resample_4h(_yf_hourly(ticker))
        context_tf = "4h"
    e = add_indicators(e_df.tail(candles).reset_index(drop=True).copy())
    ctx = add_indicators(c_df.tail(candles).reset_index(drop=True).copy())
    res, sup = swing_levels(e)
    res4, sup4 = swing_levels(ctx, lookback=80)
    return {
        "symbol": symbol,
        "entry_tf": e,
        "context_tf": ctx,
        "tf_entry": entry_tf,
        "tf_ctx": context_tf,
        "resistance_1h": res,
        "support_1h": sup,
        "resistance_4h": res4,
        "support_4h": sup4,
    }


def yf_last_and_range(ticker: str) -> tuple[float, float, float]:
    """(last, recent_high, recent_low) from the last ~3 5m bars — outcome checks."""
    import yfinance as yf
    raw = yf.download(ticker, interval="5m", period="1d", progress=False,
                      auto_adjust=True, multi_level_index=False)
    if raw is None or raw.empty:
        raise RuntimeError(f"yfinance: no 5m data for {ticker}")
    tail = raw.tail(3)
    return float(tail["Close"].iloc[-1]), float(tail["High"].max()), float(tail["Low"].min())


def market_open(kind: str) -> bool:
    """Coarse market-hours gate (UTC). Crypto is always open."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    wd, hm = now.weekday(), now.hour + now.minute / 60
    if kind in ("forex", "gold"):
        # FX week: Sun 22:00 UTC – Fri 21:00 UTC
        if wd == 5:
            return False
        if wd == 6 and hm < 22:
            return False
        if wd == 4 and hm >= 21:
            return False
        return True
    if kind == "stock":
        # NYSE/NASDAQ regular session 13:30–20:00 UTC, Mon–Fri
        return wd < 5 and 13.5 <= hm < 20
    return True


def df_for_prompt(df: pd.DataFrame, rows: int = 60) -> str:
    cols = ["ts", "open", "high", "low", "close", "volume", "ema20", "ema50", "ema200", "rsi", "atr", "vol_avg20"]
    out = df[cols].tail(rows).copy()
    out["ts"] = out["ts"].dt.strftime("%m-%d %H:%M")
    return out.round(6).to_csv(index=False)
