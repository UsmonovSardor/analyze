"""Unified AI client — Grok (xAI) primary, Gemini legacy fallback.

The rest of the codebase calls `ai_generate(prompt, system=...)` and does not
care which model answered. Grok is used by default because its real-time X/news
awareness improves sentiment/news filtering for trading setups; Gemini stays
available via AI_PROVIDER=gemini or as an automatic fallback when Grok errors.
"""
import os
import time

from . import config

# ─── Grok (xAI) via OpenAI-compatible SDK ────────────────────────────────────
_GROK_CLIENT = None


def _grok_client():
    global _GROK_CLIENT
    if _GROK_CLIENT is None:
        from openai import OpenAI  # lazy import so Gemini-only installs still work
        _GROK_CLIENT = OpenAI(
            api_key=config.XAI_API_KEY or os.getenv("XAI_API_KEY", ""),
            base_url=config.XAI_BASE_URL,
        )
    return _GROK_CLIENT


_GROK_COOLDOWN: dict = {}   # model -> unix ts until which we skip it (quota/error)


def _grok_generate(prompt: str, system: str, model_name: str | None = None) -> str:
    """Call Grok with automatic model fallback (grok-4 -> grok-3-mini)."""
    client = _grok_client()
    if model_name:
        models = [model_name]
    else:
        chain = [config.GROK_MODEL_FINAL, config.GROK_MODEL]
        models = list(dict.fromkeys(m for m in chain if m))
        models = [m for m in models if _GROK_COOLDOWN.get(m, 0) < time.time()] or models
    last_exc = None
    for m in models:
        for attempt in range(2):
            try:
                resp = client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=config.GROK_TEMPERATURE,
                    response_format={"type": "json_object"},
                )
                text = resp.choices[0].message.content
                if text:
                    return text
                raise RuntimeError(f"empty response from {m}")
            except Exception as exc:
                last_exc = exc
                msg = str(exc)
                if "503" in msg or "overloaded" in msg.lower() or "timeout" in msg.lower():
                    wait = 5 * (attempt + 1)
                    print(f"[grok] {m} transient error — waiting {wait}s (attempt {attempt+1})")
                    time.sleep(wait)
                    continue
                if "429" in msg or "rate" in msg.lower() or "quota" in msg.lower():
                    _GROK_COOLDOWN[m] = time.time() + 600  # skip for 10 min
                print(f"[grok] {m} failed: {msg[:150]} — trying next model")
                break
    raise last_exc


# ─── Gemini (legacy) ─────────────────────────────────────────────────────────
_GEMINI_MODELS_DEFAULT = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-2.0-flash"]
_GEMINI_COOLDOWN: dict = {}
_GEMINI_CLIENT = None


def _gemini_client():
    global _GEMINI_CLIENT
    if _GEMINI_CLIENT is None:
        from google import genai
        _GEMINI_CLIENT = genai.Client(api_key=config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", ""))
    return _GEMINI_CLIENT


def _gemini_generate(prompt: str, system: str, model_name: str | None = None) -> str:
    from google.genai import types
    client = _gemini_client()
    if model_name:
        models = [model_name]
    else:
        chain = [config.GEMINI_MODEL_FINAL, config.GEMINI_MODEL] + _GEMINI_MODELS_DEFAULT
        models = list(dict.fromkeys(m for m in chain if m))
        models = [m for m in models if _GEMINI_COOLDOWN.get(m, 0) < time.time()] or models
    last_exc = None
    for m in models:
        for attempt in range(2):
            try:
                resp = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(system_instruction=system),
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
                    time.sleep(wait)
                    continue
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    _GEMINI_COOLDOWN[m] = time.time() + 600
                print(f"[gemini] {m} failed: {msg[:150]} — trying next model")
                break
    raise last_exc


# ─── Public API ──────────────────────────────────────────────────────────────
def ai_generate(prompt: str, system: str, model_name: str | None = None) -> str:
    """Generate a completion from the configured provider, falling back to the
    other provider if the primary one has no key or raises."""
    provider = config.AI_PROVIDER
    primary, secondary = (_grok_generate, _gemini_generate) if provider == "grok" \
        else (_gemini_generate, _grok_generate)
    try:
        return primary(prompt, system, model_name)
    except Exception as exc:
        # Only fall back if the secondary provider is actually configured.
        has_secondary = (
            config.GEMINI_API_KEY if provider == "grok" else config.XAI_API_KEY
        )
        if has_secondary:
            print(f"[ai] primary provider '{provider}' failed ({str(exc)[:100]}) — falling back")
            return secondary(prompt, system, None)
        raise
