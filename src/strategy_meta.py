"""Display metadata for strategies and the confluence scorecard."""

STRATEGIES = {
    # ── Original setups ──────────────────────────────────────────────────────
    "A": {
        "name": "Trend Pullback",
        "emoji": "📈",
        "tagline": "Ko'tarilish trendida EMA50 ga qaytishda kirish",
    },
    "B": {
        "name": "Range Breakout",
        "emoji": "🚀",
        "tagline": "Diapazon yuqorisini probboy qilib retest'da kirish",
    },
    "TV": {
        "name": "TV Strong Alignment",
        "emoji": "📊",
        "tagline": "TradingView ko'p indikator birlashuvi",
    },
    # ── ICT Models ───────────────────────────────────────────────────────────
    "ICT_AMD":      {"name": "ICT AMD / PO3",       "emoji": "⚡"},
    "ICT_JUDAS":    {"name": "ICT Judas Swing",     "emoji": "🎭"},
    "ICT_UNICORN":  {"name": "ICT Unicorn Model",   "emoji": "🦄"},
    "ICT_VENOM":    {"name": "ICT Venom Model",     "emoji": "🐍"},
    "ICT_TURTLE":   {"name": "ICT Turtle Soup",     "emoji": "🐢"},
    "ICT_MMXM":     {"name": "ICT MMXM Model",      "emoji": "📐"},
    # ── Additional strategies ────────────────────────────────────────────────
    "MATTS_WICKS":  {"name": "Matt's Wicks Setup",          "emoji": "📌"},
    "ALI_DRT":      {"name": "Ali Khan DRT",                "emoji": "📏"},
    "FIB_SWING":    {"name": "Fibonacci Swing",             "emoji": "🌀"},
    "QUARTERLY":    {"name": "Quarterly Theory SSMT",       "emoji": "🕐"},
    "ORB":          {"name": "Opening Range Break",         "emoji": "🔔"},
    "DOYLE":        {"name": "Doyle Exchange S&D",          "emoji": "🏪"},
    "BERND":        {"name": "Bernd's Globex Trap",         "emoji": "🪤"},
    "MAYNE":        {"name": "Trader Mayne Monday Range",   "emoji": "📅"},
    "TORI":         {"name": "Tori Trend Line Swing",       "emoji": "📐"},
    "SMB":          {"name": "SMB Offsides Scalp",         "emoji": "📡"},
    "JOOVIERS":     {"name": "Jooviers Gems Superscalp",    "emoji": "💎"},
    "SCARFACE":     {"name": "Scarface 5m ORB",            "emoji": "⚡"},
    "EBP":          {"name": "Omar Agag EBP",              "emoji": "📊"},
    "CBR":          {"name": "Tomtrades CBR",              "emoji": "🔄"},
    "SBL":          {"name": "Toto Capital SBL",           "emoji": "🎯"},
    "AVWAP":        {"name": "Nvidia Anchored VWAP",        "emoji": "🔵"},
    "NOWICK":       {"name": "Bard FX Nowick",             "emoji": "🕯"},
    "OXFIB":        {"name": "0xfibonacci Confluence",      "emoji": "🔗"},
    "KANE":         {"name": "Trader Kane Lab Model",       "emoji": "🧪"},
    "FAILED2":      {"name": "Trader Mike Failed 2s",       "emoji": "📉"},
    "WAQAR":        {"name": "Waqar Asim Forex Scalp",      "emoji": "💱"},
    "JJSIMON":      {"name": "JJ Simon Fair Value NQ",      "emoji": "⚖️"},
}

# (key, label, max_points) — order defines how the scorecard renders
SCORECARD_FACTORS = [
    ("trend",  "Trend (4h)",    2),
    ("level",  "Daraja/Zone",   2),
    ("volume", "Hajm",          2),
    ("rsi",    "RSI",           1),
    ("btc",    "BTC kontekst",  1),
    ("room",   "Tepada joy",    1),
    ("candle", "Sham sifati",   1),
]


def strategy(setup: str) -> dict:
    """Lookup by short code OR by partial strategy_name match."""
    if setup in STRATEGIES:
        return STRATEGIES[setup]
    # fuzzy match by name substring
    su = (setup or "").upper()
    for k, v in STRATEGIES.items():
        if su in v["name"].upper() or su in k:
            return v
    return {"name": setup or "Signal", "emoji": "📊", "tagline": ""}


def render_scorecard(scorecard: dict) -> str:
    """Visual bars per confluence factor, e.g. 'Trend (4h)  ██ 2/2'."""
    lines = []
    n = len(SCORECARD_FACTORS)
    for i, (key, label, mx) in enumerate(SCORECARD_FACTORS):
        got = int(scorecard.get(key, 0)) if scorecard else 0
        got = max(0, min(got, mx))
        bar = "█" * got + "░" * (mx - got)
        branch = "└" if i == n - 1 else "├"
        lines.append(f"{branch} {label:<14} {bar} {got}/{mx}")
    return "\n".join(lines)
