---
name: crypto-alerts
description: >-
  Crypto Alerts. For the crypto/plan.json trade: has a closed 15-minute bar
  touched the stop or the target since the entry, and has the 23:45 UTC flat-
  by time come. Prints the mark now. Use when the user says "a atins stopul",
  "cum stă trade-ul", "watch my crypto trade", or on a /loop while a trade is
  open.
argument-hint: ""
---

# crypto-alerts

One step of the crypto version of the Day Trader pack. The engine and the
full rules live in `../crypto-trader/` (read its SKILL.md once if you have
not). Read-only Hyperliquid data; it never places an order. Files go under
`crypto/` in the current folder; `--now "YYYY-MM-DD HH:MM"` (UTC, before the
command) replays a past day.

```bash
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" alerts
```

## Steps

1. Run `alerts` while a trade is open, by hand or on `/loop 15m`.
2. A touched stop or target means the TP/SL has probably filled: the user checks Hyperliquid, then `/crypto-ticket closed`.
3. Flat-by: the user closes what is still open themselves. Never act for them.

## Safety

- Education and tooling, not financial advice. Leveraged crypto loses most day traders money.
- Nothing here places an order. The user types any trade into Hyperliquid themselves.
- Never ask for, accept or store a private key or seed phrase.
