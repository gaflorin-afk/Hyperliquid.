---
name: crypto-exit
description: >-
  Crypto Exit Planner. Sets the stop and the target before the entry for the
  crypto/entry.json trade, long or short: stop at the opening-range midpoint
  (or-mid, default), the far side of the range (or-far), pct:X, atr:K on 15m
  bars, or price:X, rounded away from the entry to Hyperliquid's tick; target
  2R by default (or 1R, 1.5R, price:X); flat by 23:45 UTC. Refuses a stop on
  the wrong side or tighter than 0.05%. Writes crypto/plan.json. Use when the
  user says "stop și țintă", "plan the exit", "unde pun stopul", or after
  /crypto-entry triggers.
argument-hint: "[--stop or-mid|or-far|pct:X|atr:K|price:X] [--target 2R|1R|price:X]"
---

# crypto-exit

One step of the crypto version of the Day Trader pack. The engine and the
full rules live in `../crypto-trader/` (read its SKILL.md once if you have
not). Read-only Hyperliquid data; it never places an order. Files go under
`crypto/` in the current folder; `--now "YYYY-MM-DD HH:MM"` (UTC, before the
command) replays a past day.

```bash
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" exit --write
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" exit --stop or-far --target 1R --write
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" exit --stop atr:1.5 --write
```

## Steps

1. Run it right after `/crypto-entry` triggers. Use the default stop unless the user names one.
2. Read back entry, stop and its rule, target and its R, risk per coin, reward:risk, flat by.
3. If it refuses, say why and the fix. Never loosen anything yourself.
4. Say once that a stop is a plan, not a guarantee. Hand off to `/crypto-timemachine`.

## Safety

- Education and tooling, not financial advice. Leveraged crypto loses most day traders money.
- Nothing here places an order. The user types any trade into Hyperliquid themselves.
- Never ask for, accept or store a private key or seed phrase.
