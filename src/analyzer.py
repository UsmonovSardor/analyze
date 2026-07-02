"""Gemini analysis layer — uses google-generativeai (free tier)."""
import asyncio
import json
import os

from google import genai
from google.genai import types

from . import config
from .data import df_for_prompt


def _load_skill() -> str:
    parts = []
    for name in ["SKILL.md", "strategy.md", "candlestick-patterns.md", "price-action.md", "risk-rules.md", "signal-format.md"]:
        with open(os.path.join(config.SKILL_DIR, name)) as f:
            parts.append(f"<<< {name} >>>\n{f.read()}")
    return "\n\n".join(parts)


_SKILL = None


def _skill() -> str:
    global _SKILL
    if _SKILL is None:
        _SKILL = _load_skill()
    return _SKILL


_GEMINI_MODELS_DEFAULT = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-2.0-flash"]


def _gemini_client():
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))


_MODEL_COOLDOWN: dict = {}   # model -> unix ts until which we skip it (quota exhausted)


def _gemini_generate(prompt: str, model_name: str | None = None) -> str:
    """Call Gemini with automatic model fallback on 503."""
    import time as _time
    client = _gemini_client()
    # Strongest model first (GEMINI_MODEL_FINAL, default 2.5-pro) — quota/503
    # automatically falls through to the flash chain, so signals never stop.
    if model_name:
        models = [model_name]
    else:
        chain = [config.GEMINI_MODEL_FINAL, config.GEMINI_MODEL] + _GEMINI_MODELS_DEFAULT
        models = list(dict.fromkeys(m for m in chain if m))
        models = [m for m in models if _MODEL_COOLDOWN.get(m, 0) < _time.time()] or models
    last_exc = None
    for m in models:
        for attempt in range(2):
            try:
                resp = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(system_instruction=_skill()),
                )
                if resp.text:
                    return resp.text
                raise RuntimeError(f"empty response from {m}")
            except Exception as exc:
                last_exc = exc
                msg = str(exc)
                if "503" in msg or "UNAVAILABLE" in msg:
                    wait = 5 * (attempt + 1)
                    print(f"[gemini] {m} 503 — waiting {wait}s (attempt {attempt+1})")
                    _time.sleep(wait)
                    continue
                # 404 (retired model), 400, quota etc. — don't kill the whole call,
                # fall through to the next model in the chain.
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    _MODEL_COOLDOWN[m] = _time.time() + 600  # skip for 10 min
                print(f"[gemini] {m} failed: {msg[:150]} — trying next model")
                break
    raise last_exc


def _performance_note(perf: dict) -> str:
    if not perf:
        return ""
    rows = []
    for setup, s in perf.items():
        rows.append(f"- Setup {setup}: {s['wins']}/{s['closed']} win ({s['win_rate']}%), {s['total_r']:+.2f}R total")
    return ("\n=== Recent performance of each setup (last 30d) — be MORE selective on under-performing "
            "setups, demand higher confluence there ===\n" + "\n".join(rows) + "\n")


def _hint_str(setup_hint) -> tuple[str, str]:
    """Accept either a string ('A') or a dict {'setup','side'}; return (setup, side)."""
    if isinstance(setup_hint, dict):
        return setup_hint.get("setup", "A"), setup_hint.get("side", "long")
    return (setup_hint or "A"), "long"


def build_prompt(snap, setup_hint, btc_snap, perf: dict | None = None, short: bool = False) -> str:
    e1h, e4h, ebtc = (30, 20, 15) if short else (60, 50, 30)
    setup, side = _hint_str(setup_hint)
    tf_e = snap.get("tf_entry", "1h")
    tf_c = snap.get("tf_ctx", "4h")
    btc_note = "" if "/" in snap["symbol"] else " (context only — this instrument is NOT crypto)"
    return f"""Analyze this candidate setup. Screener hint: Setup {setup}, direction {side.upper()} (verify it yourself, the hint may be wrong).
Timeframes: entry TF = {tf_e}, higher context TF = {tf_c}. Apply every 1h/4h rule in the skill to THESE timeframes.
{_performance_note(perf or {})}
SYMBOL: {snap['symbol']}

=== {tf_e} candles with indicators (newest last) ===
{df_for_prompt(snap['entry_tf'], e1h)}

=== {tf_c} candles with indicators (newest last) ===
{df_for_prompt(snap['context_tf'], e4h)}

{tf_e} resistance levels: {snap['resistance_1h']}
{tf_e} support levels: {snap['support_1h']}
{tf_c} resistance levels: {snap['resistance_4h']}
{tf_c} support levels: {snap['support_4h']}

=== BTC 4h context (newest last){btc_note} ===
{df_for_prompt(btc_snap['context_tf'], ebtc)}

Follow the skill process exactly. ALL text fields (reason, reasoning, confirmations) MUST be in UZBEK. Output ONLY the JSON object."""


def _parse_json(text: str, symbol: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        print(f"[analyzer] {symbol} unparseable output: {text[:300]}")
        return {"signal": "none", "symbol": symbol, "reason": f"unparseable: {text[:200]}", "score": 0}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        print(f"[analyzer] {symbol} JSON error: {e} | text: {text[start:end+1][:300]}")
        return {"signal": "none", "symbol": symbol, "reason": "invalid JSON", "score": 0}


async def analyze_tv_direct(symbol: str, e1h, e4h, setup_hint, perf: dict | None = None) -> dict:
    """Analyze any instrument (forex, stocks, indices) using TradingView indicator snapshot."""
    setup, side = _hint_str(setup_hint)

    def fmt_ta(a) -> str:
        i = a.indicators
        s = a.summary
        return (
            f"Close={i.get('close','?')}  Open={i.get('open','?')}  High={i.get('high','?')}  Low={i.get('low','?')}\n"
            f"EMA20={i.get('EMA20','?')}  EMA50={i.get('EMA50','?')}  EMA200={i.get('EMA200','?')}\n"
            f"RSI={i.get('RSI','?')}  Stoch.K={i.get('Stoch.K','?')}  Stoch.D={i.get('Stoch.D','?')}\n"
            f"MACD={i.get('MACD.macd','?')}  Signal={i.get('MACD.signal','?')}  Hist={i.get('MACD.hist','?')}\n"
            f"BB_upper={i.get('BB.upper','?')}  BB_mid={i.get('BB.basis','?')}  BB_lower={i.get('BB.lower','?')}\n"
            f"ATR={i.get('ATR','?')}  Volume={i.get('volume','?')}\n"
            f"TV Rec: {s.get('RECOMMENDATION','?')} (BUY={s.get('BUY',0)} SELL={s.get('SELL',0)})"
        )

    prompt = f"""Analyze this trading setup. Screener hint: Setup {setup}, direction {side.upper()} (verify yourself).
{_performance_note(perf or {})}
SYMBOL: {symbol}

=== 1H TradingView indicators (current snapshot) ===
{fmt_ta(e1h)}

=== 4H TradingView indicators (current snapshot) ===
{fmt_ta(e4h)}

This may be forex, commodity, or stock — apply universal price-action principles.
Both LONG and SHORT signals are allowed (trade with the 4H trend).

DATA LIMITATION: you only have a CURRENT indicator snapshot, not candle history.
Skip the candle-pattern and volume-history steps (they cannot be verified here) —
judge on what IS verifiable: EMA stack/trend, momentum (RSI, Stoch, MACD), location
(Bollinger, distance to EMAs in ATR units) and the TV recommendation counts.
Do NOT reject just because candle patterns can't be checked; base every confirmation
on the numbers provided. Anchor entry/SL/TP to EMA levels, BB bands and ATR multiples.
Follow the rest of the skill process exactly. Output ONLY the JSON object."""

    import traceback as _tb
    try:
        text = await asyncio.to_thread(_gemini_generate, prompt)
        result = _parse_json(text, symbol)
        if result.get("signal") != "none":
            print(f"[analyzer] {symbol} → signal={result.get('signal')} score={result.get('score')}")
        return result
    except Exception:
        print(f"[analyzer] {symbol} error:\n{_tb.format_exc()[:800]}")
        return {"signal": "none", "symbol": symbol, "reason": "Gemini API error", "score": 0}


async def analyze(snap, setup_hint: str, btc_snap, perf: dict | None = None) -> dict:
    import traceback as _tb
    symbol = snap["symbol"]
    for short in (False, True):
        try:
            text = await asyncio.to_thread(_gemini_generate, build_prompt(snap, setup_hint, btc_snap, perf, short=short))
            result = _parse_json(text, symbol)
            if result.get("signal") != "none":
                print(f"[analyzer] {symbol} → signal={result.get('signal')} score={result.get('score')}")
            return result
        except json.JSONDecodeError:
            return {"signal": "none", "symbol": symbol, "reason": "invalid JSON from model", "score": 0}
        except Exception:
            if not short:
                continue
            print(f"[analyzer] {symbol} error:\n{_tb.format_exc()[:800]}")
            return {"signal": "none", "symbol": symbol, "reason": "Gemini error", "score": 0}
    return {"signal": "none", "symbol": symbol, "reason": "Gemini error after retry", "score": 0}
