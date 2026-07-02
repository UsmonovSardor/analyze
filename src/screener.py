"""Cheap pre-filter that runs 24/7 without Claude.

Finds *candidate* setups only — final judgment belongs to the Claude layer.
Rules intentionally looser than skill/strategy.md so good setups aren't missed,
but tight enough that Claude is called only a handful of times per day.
"""


def _last(df, col):
    return float(df[col].iloc[-1])


def btc_context_ok(btc_snap) -> bool:
    ctx = btc_snap["context_tf"]
    # Block alt longs only when BTC 4h is decisively below EMA200 and falling
    return not (_last(ctx, "close") < _last(ctx, "ema200") and _last(ctx, "ema50") < _last(ctx, "ema200"))


def find_candidate(snap):
    """Return {"setup": "A"|"B", "side": "long"|"short"} or None."""
    from . import config

    e, ctx = snap["entry_tf"], snap["context_tf"]
    close = _last(e, "close")
    atr = _last(e, "atr")

    uptrend_4h = (
        _last(ctx, "close") > _last(ctx, "ema200")
        and _last(ctx, "ema50") > _last(ctx, "ema200")
    )
    downtrend_4h = (
        _last(ctx, "close") < _last(ctx, "ema200")
        and _last(ctx, "ema50") < _last(ctx, "ema200")
    )

    # --- Setup A long: pullback to EMA50 zone in an uptrend ---
    if uptrend_4h:
        near_ema50 = abs(close - _last(e, "ema50")) <= 1.0 * atr
        rsi_now = _last(e, "rsi")
        rsi_prev = float(e["rsi"].iloc[-2])
        rsi_reset = rsi_now < 55 and rsi_now > rsi_prev and min(e["rsi"].tail(6)) < 45
        if near_ema50 and rsi_reset:
            return {"setup": "A", "side": "long"}

    # --- Setup B long: breakout of recent range high on volume ---
    range_high = float(e["high"].iloc[-40:-2].max())
    vol_spike = _last(e, "volume") >= 1.3 * _last(e, "vol_avg20")
    broke_out = close > range_high and (close - range_high) <= 1.5 * atr
    if broke_out and vol_spike and uptrend_4h:
        return {"setup": "B", "side": "long"}

    # --- Setup TV long: strong trend continuation (momentum) ---
    if uptrend_4h:
        rsi_now = _last(e, "rsi")
        stacked = close > _last(e, "ema20") > _last(e, "ema50")
        vol_ok = _last(e, "volume") >= 0.9 * _last(e, "vol_avg20")
        if stacked and 50 <= rsi_now < 68 and vol_ok:
            return {"setup": "TV", "side": "long"}

    # --- EMA200 bounce long: hold/reclaim of the 1h EMA200 in a non-bear context ---
    if not downtrend_4h:
        near200 = abs(close - _last(e, "ema200")) <= 1.0 * atr
        rsi_turn = _last(e, "rsi") > float(e["rsi"].iloc[-2]) and _last(e, "rsi") < 55
        if near200 and rsi_turn:
            return {"setup": "B", "side": "long"}

    if config.ALLOW_SHORTS:
        # --- Setup A short: bounce up to EMA50 zone in a downtrend ---
        if downtrend_4h:
            near_ema50 = abs(close - _last(e, "ema50")) <= 1.0 * atr
            rsi_now = _last(e, "rsi")
            rsi_prev = float(e["rsi"].iloc[-2])
            rsi_reset = rsi_now > 45 and rsi_now < rsi_prev and max(e["rsi"].tail(6)) > 55
            if near_ema50 and rsi_reset:
                return {"setup": "A", "side": "short"}

        # --- Setup B short: breakdown of recent range low on volume ---
        range_low = float(e["low"].iloc[-40:-2].min())
        broke_down = close < range_low and (range_low - close) <= 1.5 * atr
        if broke_down and vol_spike and downtrend_4h:
            return {"setup": "B", "side": "short"}

        # --- Setup TV short: strong downtrend continuation (momentum) ---
        if downtrend_4h:
            rsi_now = _last(e, "rsi")
            stacked = close < _last(e, "ema20") < _last(e, "ema50")
            vol_ok = _last(e, "volume") >= 0.9 * _last(e, "vol_avg20")
            if stacked and 32 < rsi_now <= 50 and vol_ok:
                return {"setup": "TV", "side": "short"}

        # --- EMA200 rejection short: failure at the 1h EMA200 in a non-bull context ---
        if not uptrend_4h:
            near200 = abs(close - _last(e, "ema200")) <= 1.0 * atr
            rsi_turn = _last(e, "rsi") < float(e["rsi"].iloc[-2]) and _last(e, "rsi") > 45
            if near200 and rsi_turn:
                return {"setup": "B", "side": "short"}

    return None
