---
name: crypto-scanner
description: >-
  Crypto Chart Scanner. Scans only your coins (default the top 10 Hyperliquid
  perps) for opening-range breakouts today: the first 60 minutes from 00:00
  UTC on 15-minute bars, then the first close above or below the range, long
  or short. Also a daily scan (20-day breakout or breakdown, MA20 reclaim or
  loss, oversold, oversold bounce, overbought). Writes crypto/watchlist.json.
  Use when the user says "scan crypto", "scanează monedele", "ce crypto a
  ieșit din range", "crypto setups", or at the start of a crypto trading day.
argument-hint: "[orb | daily] [--coins BTC,ETH]"
---

# crypto-scanner

One step of the crypto version of the Day Trader pack. The engine and the
full rules live in `../crypto-trader/` (read its SKILL.md once if you have
not). Read-only Hyperliquid data; it never places an order. Files go under
`crypto/` in the current folder; `--now "YYYY-MM-DD HH:MM"` (UTC, before the
command) replays a past day.

```bash
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" scan
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" scan daily
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" scan --coins BTC,ETH,SOL
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" coins list
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" coins set BTC ETH SOL
```

## Steps

1. The opening range closes at 01:00 UTC (04:00 in Romania in summer, 03:00 in winter); before that it says so.
2. Run `scan`. Tell the user how many coins were usable, which broke out, when and which way, and that a later hit is closer to the price now.
3. In a 24/7 market a 60-minute range is narrow, so most coins break it on most days: the Time Machine is what tells whether a breakout was worth anything.
4. The user picks one. Hand it to `/crypto-entry COIN`. Never pick for them.

## Safety

- Education and tooling, not financial advice. Leveraged crypto loses most day traders money.
- Nothing here places an order. The user types any trade into Hyperliquid themselves.
- Never ask for, accept or store a private key or seed phrase.
