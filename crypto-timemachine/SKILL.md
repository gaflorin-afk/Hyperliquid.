---
name: crypto-timemachine
description: >-
  Crypto Time Machine. Replays the rest of the day 10,000 times for the
  crypto/plan.json trade, each 15-minute bar drawn from the coin's own bars at
  the same UTC time of day over its last ~50 full days, and re-runs the same
  rule (range, side, stop rule, R target) on every one of those real days.
  Prints target first, stop first, neither, green, the price range, average R,
  the history and one verdict. Use when the user says "run the time machine",
  "care sunt șansele", "simulează trade-ul", "backtest", or after /crypto-
  exit.
argument-hint: "[--seed 19] [--replays 10000]"
---

# crypto-timemachine

One step of the crypto version of the Day Trader pack. The engine and the
full rules live in `../crypto-trader/` (read its SKILL.md once if you have
not). Read-only Hyperliquid data; it never places an order. Files go under
`crypto/` in the current folder; `--now "YYYY-MM-DD HH:MM"` (UTC, before the
command) replays a past day.

```bash
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" tm
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" tm --seed 7
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" tm --write
```

## Steps

1. Make sure crypto/plan.json is today's plan.
2. Run `tm`. Tell the user, in order: the four odds, the price range, average R, the history line, then the verdict line exactly as printed, and the seed.
3. Coin flip or close to break-even: say so plainly. If history and replays disagree, say that too.
4. Say once it is built from the last ~50 days, not a prediction; news, listings, hacks and liquidation cascades can do things those days never did. If the user still wants it, `/crypto-budget`.

## Safety

- Education and tooling, not financial advice. Leveraged crypto loses most day traders money.
- Nothing here places an order. The user types any trade into Hyperliquid themselves.
- Never ask for, accept or store a private key or seed phrase.
