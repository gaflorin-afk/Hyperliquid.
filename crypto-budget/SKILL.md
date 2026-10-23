---
name: crypto-budget
description: >-
  Crypto Budget Manager. Sizes the crypto/plan.json trade to your max loss per
  trade, leverage and margin: the smallest of max loss / risk per coin,
  position cap and margin after the cash buffer, rounded down to the coin's
  size step on Hyperliquid. Measures risk from the worse of the plan's entry
  and the current mark, refuses below min reward:risk, under $10, or when the
  estimated liquidation comes before the stop, and writes ONE order to
  crypto/orders.json. Nothing is placed. Use when the user says "cât BTC
  cumpăr", "size this trade", "am 1000 de dolari", "ce levier", or after
  /crypto-timemachine.
argument-hint: ""
---

# crypto-budget

One step of the crypto version of the Day Trader pack. The engine and the
full rules live in `../crypto-trader/` (read its SKILL.md once if you have
not). Read-only Hyperliquid data; it never places an order. Files go under
`crypto/` in the current folder; `--now "YYYY-MM-DD HH:MM"` (UTC, before the
command) replays a past day.

```bash
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" init
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" budget
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" budget --write
```

## Steps

1. If crypto/config.json does not exist, run `init` and ask the user for budget, max loss per trade, daily loss limit, trades per day, leverage and max leverage, in plain words. Keep leverage low.
2. Run `budget --write`. Show the limits, which one decided the size, notional, margin, max loss at the stop and the estimated liquidation.
3. If it refuses, give the one-line reason. Hand off to `/crypto-risk`.

## Safety

- Education and tooling, not financial advice. Leveraged crypto loses most day traders money.
- Nothing here places an order. The user types any trade into Hyperliquid themselves.
- Never ask for, accept or store a private key or seed phrase.
