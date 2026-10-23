---
name: crypto-risk
description: >-
  Crypto Risk Manager. Checks every order in crypto/orders.json before it can
  become a ticket: coin in your list and not blocked, shorts allowed, a stop
  on the right side, loss at the stop (from the worse of plan entry and
  current mark) within max loss, reward:risk, the day's total risk within the
  daily loss limit, trades per day, one open position per coin, leverage cap,
  liquidation not before the stop, Hyperliquid's $10 minimum and the entry
  window. Prints PASS or BLOCK with the reason and records the verdicts. Use
  when the user says "risk check", "pot lua trade-ul", "cât am riscat azi", or
  before /crypto-ticket, always.
argument-hint: ""
---

# crypto-risk

One step of the crypto version of the Day Trader pack. The engine and the
full rules live in `../crypto-trader/` (read its SKILL.md once if you have
not). Read-only Hyperliquid data; it never places an order. Files go under
`crypto/` in the current folder; `--now "YYYY-MM-DD HH:MM"` (UTC, before the
command) replays a past day.

```bash
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" risk
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" risk --no-write
```

## Steps

1. Run `risk`. Exit 0 means every order passed.
2. Tell the user order by order: max loss at the stop, reward:risk, how much of today's limits it uses. For a BLOCK, the reason and the fix (fewer coins, a closer stop, wait, or skip). Never change a limit yourself.
3. If the order changes, run it again: the ticket matches each order to its verdict by fingerprint.

## Safety

- Education and tooling, not financial advice. Leveraged crypto loses most day traders money.
- Nothing here places an order. The user types any trade into Hyperliquid themselves.
- Never ask for, accept or store a private key or seed phrase.
