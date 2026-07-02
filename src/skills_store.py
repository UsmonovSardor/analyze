"""Skill/strategy browser + Telegram-managed custom strategies.

Built-in knowledge lives in skill/*.md (versioned in GitHub). User-added
strategies are stored next to the journal DB (/data on the server), so they
survive container rebuilds, and are appended to the Gemini system prompt with
equal standing to the built-in strategies.
"""
import os
import re

from . import config

# (filename, menu label) — strategy.md is browsed per-strategy, not as a doc.
DOCS = [
    ("SKILL.md",                "📖 Asosiy tahlil qoidalari"),
    ("candlestick-patterns.md", "🕯 Sham naqshlari (Nison)"),
    ("price-action.md",         "📊 Price Action (Brooks)"),
    ("risk-rules.md",           "🛡 Risk qoidalari"),
    ("signal-format.md",        "📋 Signal formati"),
]

PAGE_CHARS = 3200   # per Telegram message page (limit 4096 incl. HTML tags)


def _read(name: str) -> str:
    with open(os.path.join(config.SKILL_DIR, name)) as f:
        return f.read()


def custom_path() -> str:
    """Custom strategies live next to the DB — /data volume in production."""
    return os.path.join(os.path.dirname(os.path.abspath(config.DB_PATH)),
                        "custom_strategies.md")


def _paginate(text: str) -> list:
    lines, pages, buf = text.splitlines(keepends=True), [], ""
    for ln in lines:
        if len(buf) + len(ln) > PAGE_CHARS and buf:
            pages.append(buf)
            buf = ""
        buf += ln
    if buf:
        pages.append(buf)
    return pages or [""]


def doc_pages(idx: int) -> tuple:
    """(label, [page, ...]) for a built-in doc."""
    name, label = DOCS[idx]
    return label, _paginate(_read(name))


def strategies() -> list:
    """[(name, section_text), ...] from every ## / ### heading in strategy.md."""
    text = _read("strategy.md")
    parts = re.split(r"^(#{2,3} .+)$", text, flags=re.M)
    out = []
    for i in range(1, len(parts) - 1, 2):
        name = parts[i].lstrip("#").strip()
        out.append((name, (parts[i] + "\n" + parts[i + 1]).strip()))
    return out


def list_custom() -> list:
    """[(name, body), ...] user-added strategies."""
    p = custom_path()
    if not os.path.exists(p):
        return []
    parts = re.split(r"^### (.+)$", open(p).read(), flags=re.M)
    return [(parts[i].strip(), parts[i + 1].strip())
            for i in range(1, len(parts) - 1, 2)]


def _write_custom(items: list):
    p = custom_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write("# Foydalanuvchi strategiyalari (Telegram orqali qo'shilgan)\n\n")
        for name, body in items:
            f.write(f"### {name}\n{body}\n\n")


def add_custom(name: str, body: str) -> bool:
    """Add or replace a custom strategy; returns True if it replaced an old one."""
    items = list_custom()
    replaced = any(n.lower() == name.lower() for n, _ in items)
    items = [(n, b) for n, b in items if n.lower() != name.lower()]
    items.append((name.strip(), body.strip()))
    _write_custom(items)
    return replaced


def remove_custom(idx: int):
    """Delete by index; returns the removed name or None."""
    items = list_custom()
    if not (0 <= idx < len(items)):
        return None
    name = items[idx][0]
    del items[idx]
    _write_custom(items)
    return name


def prompt_block() -> str:
    """Custom strategies as a system-prompt section ('' when none exist)."""
    items = list_custom()
    if not items:
        return ""
    body = "\n\n".join(f"### {n}\n{b}" for n, b in items)
    return ("<<< custom_strategies.md >>>\n"
            "# User-Added Strategies (Telegram orqali qo'shilgan — built-in "
            "strategiyalar bilan TENG huquqli, mos kelganda qo'lla va "
            "strategy_name sifatida ishlat)\n\n" + body)
