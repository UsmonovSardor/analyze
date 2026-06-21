"""Claude analysis layer. Works with either CLAUDE_CODE_OAUTH_TOKEN (subscription
token from `claude setup-token`) or ANTHROPIC_API_KEY — the Agent SDK handles both."""
import json
import os

from claude_agent_sdk import ClaudeAgentOptions, query

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


async def _run_query(prompt: str, options) -> str:
    text = ""
    async for message in query(prompt=prompt, options=options):
        for block in getattr(message, "content", []) or []:
            if hasattr(block, "text"):
                text += block.text
    return text


async def analyze(snap, setup_hint: str, btc_snap, perf: dict | None = None) -> dict:
    options = ClaudeAgentOptions(
        system_prompt=_skill(),
        model=config.CLAUDE_MODEL,
        max_turns=1,
        allowed_tools=[],
    )
    symbol = snap["symbol"]
    # Try full prompt first, fall back to shorter prompt on error
    for short in (False, True):
        try:
            text = await _run_query(build_prompt(snap, setup_hint, btc_snap, perf, short=short), options)
            start, end = text.find("{"), text.rfind("}")
            if start == -1 or end == -1:
                return {"signal": "none", "symbol": symbol, "reason": f"unparseable output: {text[:200]}", "score": 0}
            return json.loads(text[start: end + 1])
        except json.JSONDecodeError:
            return {"signal": "none", "symbol": symbol, "reason": "invalid JSON from model", "score": 0}
        except Exception as e:
            if "success" in str(e).lower() and not short:
                continue  # retry with shorter prompt
            raise
    return {"signal": "none", "symbol": symbol, "reason": "Claude error after retry", "score": 0}
