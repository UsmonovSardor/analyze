"""Claude analysis layer. Works with either CLAUDE_CODE_OAUTH_TOKEN (subscription
token from `claude setup-token`) or ANTHROPIC_API_KEY — the Agent SDK handles both."""
import json
import os

from claude_agent_sdk import ClaudeAgentOptions, query

from . import config
from .data import df_for_prompt


def _load_skill() -> str:
    parts = []
    for name in ["SKILL.md", "strategy.md", "risk-rules.md", "signal-format.md"]:
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


def build_prompt(snap, setup_hint: str, btc_snap, perf: dict | None = None) -> str:
    return f"""Analyze this candidate setup. Screener hint: Setup {setup_hint} (verify it yourself, the hint may be wrong).
{_performance_note(perf or {})}
SYMBOL: {snap['symbol']}

=== 1h candles with indicators (newest last) ===
{df_for_prompt(snap['entry_tf'], 60)}

=== 4h candles with indicators (newest last) ===
{df_for_prompt(snap['context_tf'], 50)}

1h resistance levels: {snap['resistance_1h']}
1h support levels: {snap['support_1h']}
4h resistance levels: {snap['resistance_4h']}
4h support levels: {snap['support_4h']}

=== BTC 4h context (newest last) ===
{df_for_prompt(btc_snap['context_tf'], 30)}

Follow the skill process exactly. Output ONLY the JSON object."""


async def analyze(snap, setup_hint: str, btc_snap, perf: dict | None = None) -> dict:
    options = ClaudeAgentOptions(
        system_prompt=_skill(),
        model=config.CLAUDE_MODEL,
        max_turns=1,
        allowed_tools=[],
    )
    text = ""
    async for message in query(prompt=build_prompt(snap, setup_hint, btc_snap, perf), options=options):
        for block in getattr(message, "content", []) or []:
            if hasattr(block, "text"):
                text += block.text

    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {"signal": "none", "symbol": snap["symbol"], "reason": f"unparseable model output: {text[:200]}", "score": 0}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {"signal": "none", "symbol": snap["symbol"], "reason": "invalid JSON from model", "score": 0}
