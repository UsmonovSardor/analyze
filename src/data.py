"""Market data + indicators from Binance public endpoints (no API key needed)."""
import os

import ccxt
import pandas as pd

# Binance blocks US IPs (HTTP 451) — set EXCHANGE=okx/bybit/kraken if the host region is restricted
_exchange = getattr(ccxt, os.getenv("EXCHANGE", "binance"))({"enableRateLimit": True})
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
        "resistance_1h": res,
        "support_1h": sup,
        "resistance_4h": res4,
        "support_4h": sup4,
    }


def df_for_prompt(df: pd.DataFrame, rows: int = 60) -> str:
    cols = ["ts", "open", "high", "low", "close", "volume", "ema20", "ema50", "ema200", "rsi", "atr", "vol_avg20"]
    out = df[cols].tail(rows).copy()
    out["ts"] = out["ts"].dt.strftime("%m-%d %H:%M")
    return out.round(6).to_csv(index=False)
