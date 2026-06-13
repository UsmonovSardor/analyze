"""Display metadata for strategies and the confluence scorecard.
Kept separate from the trading logic so the Telegram reports stay readable."""

STRATEGIES = {
    "A": {
        "name": "Trend Pullback",
        "emoji": "📈",
        "tagline": "Ko'tarilish trendida chegaraga qaytishni sotib olish",
        "logic": "4h trend yuqoriga, narx EMA50 zonasiga tushdi, RSI tiklandi va yuqoriga burildi, "
                 "tasdiqlovchi sham yopildi.",
    },
    "B": {
        "name": "Range Breakout + Retest",
        "emoji": "🚀",
        "tagline": "Diapazon yuqorisini probboy qilib qayta-test'da kirish",
        "logic": "Narx diapazon yuqorisini katta hajm bilan probboy qildi va sindirilgan darajani "
                 "qaytadan test qilmoqda.",
    },
}

# (key, label, max_points) — order defines how the scorecard renders
SCORECARD_FACTORS = [
    ("trend", "Trend (4h)", 2),
    ("level", "Daraja", 2),
    ("volume", "Hajm", 2),
    ("rsi", "RSI", 1),
    ("btc", "BTC kontekst", 1),
    ("room", "Tepada joy", 1),
    ("candle", "Sham sifati", 1),
]


def strategy(setup: str) -> dict:
    return STRATEGIES.get(setup, {"name": f"Setup {setup}", "emoji": "•", "tagline": "", "logic": ""})


def render_scorecard(scorecard: dict) -> str:
    """Visual bars per confluence factor, e.g. 'Trend (4h)  ██ 2/2'."""
    lines = []
    n = len(SCORECARD_FACTORS)
    for i, (key, label, mx) in enumerate(SCORECARD_FACTORS):
        got = int(scorecard.get(key, 0)) if scorecard else 0
        got = max(0, min(got, mx))
        bar = "█" * got + "░" * (mx - got)
        branch = "└" if i == n - 1 else "├"
        lines.append(f"{branch} {label:<13} {bar} {got}/{mx}")
    return "\n".join(lines)
