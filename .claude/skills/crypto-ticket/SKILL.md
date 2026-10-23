---
name: crypto-ticket
description: >-
  Crypto Ticket. Shows each risk-passed order as a ticket to type into
  app.hyperliquid.xyz yourself (side, size, market, leverage, isolated margin,
  TP/SL, max loss, estimated liquidation, flat-by time) with the exact clicks.
  Records what the user says they placed (ticket placed) and closed (ticket
  closed, in R) in crypto/state/journal.json so the daily limits count it.
  Claude never places, cancels or changes an order. Use when the user says
  "arată biletul", "cum plasez ordinul", "am intrat", "am închis", "jurnal",
  or after /crypto-risk passes.
argument-hint: "[show | placed --index N --price P | closed --coin X --price P | log]"
---

# crypto-ticket

One step of the crypto version of the Day Trader pack. The engine and the
full rules live in `../crypto-trader/` (read its SKILL.md once if you have
not). Read-only Hyperliquid data; it never places an order. Files go under
`crypto/` in the current folder; `--now "YYYY-MM-DD HH:MM"` (UTC, before the
command) replays a past day.

```bash
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" ticket
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" ticket placed --index 1 --price 83750
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" ticket closed --coin BTC --price 82892
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" ticket log
```

## Steps

1. `ticket`: show only READY tickets as orders to place; a NOT READY or BLOCKED one goes back to `/crypto-risk`.
2. The user places it themselves on Hyperliquid. Never offer to do it, and never ask for keys.
3. Record only what they confirm: `ticket placed --index N --price <their fill>`, later `ticket closed --coin X --price P`.

## Safety

- Education and tooling, not financial advice. Leveraged crypto loses most day traders money.
- Nothing here places an order. The user types any trade into Hyperliquid themselves.
- Never ask for, accept or store a private key or seed phrase.
