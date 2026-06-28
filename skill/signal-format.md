# Output Format

Respond with ONLY a JSON object, no markdown fences, no prose outside it.

Rejection:
{"signal": "none", "symbol": "<SYMBOL>", "reason": "<one short sentence why>", "score": <0-10>}

Signal:
{
  "signal": "long" | "short",
  "symbol": "<SYMBOL>",
  "setup": "A" | "B" | "TV" | "<strategy_short_code>",
  "strategy_name": "<exact strategy name from strategy.md, e.g. 'ICT Judas Swing' or 'Omar Agag EBP'>",
  "market_type": "BINANCE_FUTURES" | "FOREX" | "STOCKS" | "GOLD",
  "score": <6-10>,
  "entry": <price>,
  "stop_loss": <price>,
  "tp1": <price>,
  "tp2": <price>,
  "tp3": <price>,
  "confirmations": [
    "<Confirmation 1: specific factor, e.g. '4h EMA50 > EMA200 — bullish trend confirmed'>",
    "<Confirmation 2: specific factor, e.g. 'ICT Judas Swing — London swept Asian low at 1.0842'>",
    "<Confirmation 3: specific factor, e.g. 'RSI reset to 38 and turning up on 1h'>",
    "<Confirmation 4: specific factor, e.g. 'BTC 4h above EMA200 — risk-on context'>",
    "<Confirmation 5: specific factor, e.g. 'Volume spike 1.4x average at entry candle'>",
    "<Confirmation 6 (optional): additional factor>",
    "<Confirmation 7 (optional): additional factor>"
  ],
  "reasoning": "<2-4 sentences in Uzbek: which strategy, why this direction, key structure, invalidation>",
  "scorecard": {"trend": 0-2, "level": 0-2, "volume": 0-2, "rsi": 0-1, "btc": 0-1, "room": 0-1, "candle": 0-1}
}

CRITICAL RULES:
1. `confirmations` MUST have at least 5 items. Each must be a SPECIFIC, FACTUAL statement with actual data values (price levels, EMA values, RSI numbers, etc.). Generic phrases like "trend is bullish" are REJECTED — write "4h EMA50=42,100 > EMA200=38,500 — bullish structure".
2. `strategy_name` MUST match one of the strategies in strategy.md (e.g. "ICT Venom Model", "ORB", "Doyle Exchange", "Trader Kane Lab Model", "Omar Agag EBP", "Ali Khan DRT", etc.).
3. `market_type` defines where to trade: BINANCE_FUTURES (crypto shorts/longs on perpetuals), FOREX (currency pairs via broker), STOCKS (US equities), GOLD (XAUUSD).
4. For BINANCE_FUTURES: entry order type is STOP-LIMIT (stop order placed above/below current price). Do NOT suggest limit orders for futures entry.

Price ordering MUST be:
  - long:  stop_loss < entry < tp1 < tp2 < tp3
  - short: stop_loss > entry > tp1 > tp2 > tp3

All prices must respect the symbol's natural precision from the provided data.
