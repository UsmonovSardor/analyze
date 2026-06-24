"""Gemini analysis layer — uses google-generativeai (free tier)."""
import json
import os

import google.generativeai as genai

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


def _gemini():
    genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
    return genai.GenerativeModel(
        model_name=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
        system_instruction=_skill(),
    )


def _performance_note(perf: dict) -> str:
    if not perf:
        return ""
    rows = []
    for setup, s in perf.items():
        rows.append(f"- Setup {setup}: {s['wins']}/{s['closed']} win ({s['win_rate']}%), {s['total_r']:+.2f}R total")
    return ("\n=== Recent performance of each setup (last 30d) — be MORE selective on under-performing "
            "setups, demand higher confluence there ===\n" + "\n".join(rows) + "\n")


def build_prompt(snap, setup_hint: str, btc_snap, perf: dict | None = None, short: bool = False) -> str:
    e1h, e4h, ebtc = (30, 20, 15) if short else (60, 50, 30)
    return f"""Analyze this candidate setup. Screener hint: Setup {setup_hint} (verify it yourself, the hint may be wrong).
{_performance_note(perf or {})}
SYMBOL: {snap['symbol']}

=== 1h candles with indicators (newest last) ===
{df_for_prompt(snap['entry_tf'], e1h)}

=== 4h candles with indicators (newest last) ===
{df_for_prompt(snap['context_tf'], e4h)}

1h resistance levels: {snap['resistance_1h']}
1h support levels: {snap['support_1h']}
4h resistance levels: {snap['resistance_4h']}
4h support levels: {snap['support_4h']}

=== BTC 4h context (newest last) ===
{df_for_prompt(btc_snap['context_tf'], ebtc)}

Follow the skill process exactly. Output ONLY the JSON object."""


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


async def analyze_tv_direct(symbol: str, e1h, e4h, setup_hint: str, perf: dict | None = None) -> dict:
    """Analyze any instrument (forex, stocks, indices) using TradingView indicator snapshot."""
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

    prompt = f"""Analyze this trading setup. Screener hint: Setup {setup_hint} (verify yourself).
{_performance_note(perf or {})}
SYMBOL: {symbol}

=== 1H TradingView indicators (current snapshot) ===
{fmt_ta(e1h)}

=== 4H TradingView indicators (current snapshot) ===
{fmt_ta(e4h)}

This may be forex, commodity, or stock — apply universal price-action principles.
Follow the skill process exactly. Output ONLY the JSON object."""

    import traceback as _tb
    for attempt in range(2):
        try:
            model = _gemini()
            resp = model.generate_content(prompt)
            text = resp.text
            result = _parse_json(text, symbol)
            if result.get("signal") != "none":
                print(f"[analyzer] {symbol} → signal={result.get('signal')} score={result.get('score')}")
            return result
        except Exception:
            print(f"[analyzer] {symbol} attempt {attempt+1} error:\n{_tb.format_exc()[:1200]}")
            if attempt == 0:
                continue
            return {"signal": "none", "symbol": symbol, "reason": "Gemini API error", "score": 0}
    return {"signal": "none", "symbol": symbol, "reason": "analyze_tv_direct failed", "score": 0}


async def analyze(snap, setup_hint: str, btc_snap, perf: dict | None = None) -> dict:
    symbol = snap["symbol"]
    for short in (False, True):
        try:
            model = _gemini()
            resp = model.generate_content(build_prompt(snap, setup_hint, btc_snap, perf, short=short))
            text = resp.text
            result = _parse_json(text, symbol)
            if result.get("signal") != "none":
                print(f"[analyzer] {symbol} → signal={result.get('signal')} score={result.get('score')}")
            return result
        except json.JSONDecodeError:
            return {"signal": "none", "symbol": symbol, "reason": "invalid JSON from model", "score": 0}
        except Exception as e:
            if not short:
                continue
            raise
    return {"signal": "none", "symbol": symbol, "reason": "Gemini error after retry", "score": 0}
