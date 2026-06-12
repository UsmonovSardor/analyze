# Output Format

Respond with ONLY a JSON object, no markdown fences, no prose outside it.

Rejection:
{"signal": "none", "symbol": "<SYMBOL>", "reason": "<one short sentence why>", "score": <0-10>}

Signal:
{
  "signal": "long",
  "symbol": "<SYMBOL>",
  "setup": "A" | "B",
  "score": <7-10>,
  "entry": <price>,
  "stop_loss": <price>,
  "tp1": <price>,
  "tp2": <price>,
  "tp3": <price>,
  "reasoning": "<2-4 sentences in Uzbek: which setup, key confluence factors, the invalidation logic>",
  "scorecard": {"trend": 0-2, "level": 0-2, "volume": 0-2, "rsi": 0-1, "btc": 0-1, "room": 0-1, "candle": 0-1}
}

All prices must respect the symbol's natural precision from the provided data.
