---
name: crypto-entry
description: >-
  Crypto Entry Timer. For one Hyperliquid coin, builds today's opening range
  (first 60 minutes from 00:00 UTC) and calls the entry on the first CLOSED
  15-minute bar beyond it: above the high (long) or below the low (short).
  Says waiting and how far, triggered with time, side, price and volume, or
  expired, and writes crypto/entry.json. Never places an order. Use when the
  user says "entry BTC", "a ieșit BTC din range", "când intru", "time my
  crypto entry".
argument-hint: "[COIN] [--side long|short]"
---

# crypto-entry

One step of the crypto version of the Day Trader pack. The engine and the
full rules live in `../crypto-trader/` (read its SKILL.md once if you have
not). Read-only Hyperliquid data; it never places an order. Files go under
`crypto/` in the current folder; `--now "YYYY-MM-DD HH:MM"` (UTC, before the
command) replays a past day.

```bash
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" entry BTC
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" entry BTC --side long
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" entry
```

## Steps

1. Run `entry COIN` (or `entry` for every scanner hit). Say the status in one line.
2. If the trigger is more than a bar old, say so: a late entry is a different trade, and /crypto-budget will measure the risk from the price now.
3. A bar counts only once closed. Never call an entry early.
4. Hand off to `/crypto-exit` before anything is bought.

## Safety

- Education and tooling, not financial advice. Leveraged crypto loses most day traders money.
- Nothing here places an order. The user types any trade into Hyperliquid themselves.
- Never ask for, accept or store a private key or seed phrase.
