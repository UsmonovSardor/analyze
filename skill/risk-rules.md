# Risk Rules

## Stop-loss
- Place SL below the structural invalidation point: the swing low of the pullback
  (Setup A) or below the broken range high / retest low (Setup B).
- SL distance must be between 0.8× and 2.0× ATR(14, 1h) from entry.
  - Closer than 0.8×ATR → noise will hit it → widen to structure or reject.
  - Wider than 2.0×ATR → setup is too loose → reject.

## Take-profits (R = entry − SL distance)
- TP1 = entry + 1.5R (take 40%)
- TP2 = entry + 2.5R (take 40%)
- TP3 = entry + 4R or the next major 4h resistance, whichever is CLOSER (final 20%)
- If a major resistance sits below 1.5R, the trade fails minimum R:R → reject.
- After TP1 hits, stop moves to breakeven (state this in the signal).

## Position sizing guidance (informational, included in signal)
- Risk per trade: 1% of account. Position size = (account × 0.01) / (entry − SL).

## Confidence
- Report confidence as the confluence score (0–10). Signals below 7 are never emitted.
