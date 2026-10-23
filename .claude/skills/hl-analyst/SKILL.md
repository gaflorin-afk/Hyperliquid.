---
name: hl-analyst
description: >-
  Hyperliquid Analyst (read-only). Analyses BTC or any Hyperliquid perp from
  the public API (api.hyperliquid.xyz, no key): price, funding, open interest,
  technicals (EMA 20/50/200, RSI, MACD, ATR, ranges, daily pivots) on any
  interval, funding history, order-book walls, any wallet's open positions,
  and a Time Machine that replays a long or short plan (entry, stop, target,
  optional leverage with an estimated liquidation price) 10,000 times from
  the coin's own 15-minute bars plus the real history of the same bracket.
  Never signs or places an order. Use when the user says "analyse BTC",
  "BTC pe Hyperliquid", "funding", "open interest", "RSI pe BTC", "order
  book", "ce poziții are portofelul X", "simulează un long/short", "unde e
  lichidarea la 20x", or asks about a crypto perp on Hyperliquid.
  Keeps a watchlist of only the coins the user cares about and scans just
  those ("scanează monedele mele", "doar BTC, ETH și SOL", "adaugă DOGE").
argument-hint: "[scan | coins list|set|add|remove | snapshot | ta | funding | book | wallet ADDR | sim] [--coin BTC]"
---

# hl-analyst

Read-only analysis of Hyperliquid perps. It is the crypto counterpart of the
day-trader pack: the stock skills stop at US stocks and NYSE hours; this one
reads a 24/7 market. It only describes what the data shows. Crypto perps with
leverage can wipe out an account in minutes, and most leveraged traders lose.

## The watchlist: only the coins the user picked

`watchlist.json` in this folder holds the coins (default BTC, ETH, SOL).
`scan` reads only those, never the whole exchange. Every symbol is checked
against Hyperliquid's list before it is saved.

```bash
python3 "${CLAUDE_SKILL_DIR}/hl.py" coins list
python3 "${CLAUDE_SKILL_DIR}/hl.py" coins set BTC ETH SOL        # replace the list
python3 "${CLAUDE_SKILL_DIR}/hl.py" coins add DOGE               # add / remove one or more
python3 "${CLAUDE_SKILL_DIR}/hl.py" coins remove DOGE
python3 "${CLAUDE_SKILL_DIR}/hl.py" scan                         # watchlist, 1h bars
python3 "${CLAUDE_SKILL_DIR}/hl.py" scan --interval 4h           # or 15m, 1d...
python3 "${CLAUDE_SKILL_DIR}/hl.py" scan --coins BTC,ETH --json  # this run only
```

`scan` prints one row a coin: price, 24h change, hourly funding, open
interest, RSI14, trend vs EMA 20/50/200 (`+` above, `-` below), ATR as % of
price, where the price sits in its 7-day range, and the setups that matched
on the last closed bar: `breakout_20` / `breakdown_20` (close above the
highest / under the lowest of the 20 closes before), `reclaim_ema50` /
`lost_ema50` (crossed the 50 EMA on this bar), `oversold` / `overbought`
(RSI under 30 / over 70), `funding_hot_*` (funding at or past 0.005 % an
hour, about 44 % a year: one side is crowded and paying). Report them as
matched rules, never as buys or sells; follow up on a coin with `ta` and
`sim`. Change the watchlist only when the user asks.

## Single coin

```bash
python3 "${CLAUDE_SKILL_DIR}/hl.py" snapshot                     # price, 24h, volume, OI, funding, max leverage
python3 "${CLAUDE_SKILL_DIR}/hl.py" ta --interval 1h             # 1m 5m 15m 1h 4h 1d
python3 "${CLAUDE_SKILL_DIR}/hl.py" funding --days 7
python3 "${CLAUDE_SKILL_DIR}/hl.py" book --walls 3
python3 "${CLAUDE_SKILL_DIR}/hl.py" wallet 0xADDRESS
python3 "${CLAUDE_SKILL_DIR}/hl.py" sim --side long --entry 81800 --stop 80800 --target 83800 --hours 24 --lev 20
python3 "${CLAUDE_SKILL_DIR}/hl.py" --coin ETH snapshot          # any perp: ETH, SOL, xyz:GOLD...
```

Sim flags: `--replays` (10000), `--seed` (19), `--window` (+-2 bars of time
of day), `--step` (history starts every N bars, 4 = hourly).

## Steps

1. Start with `snapshot`, then `ta` on the interval the user trades (1h and
   4h for swing, 5m/15m for intraday). Add `funding` and `book` when
   positioning matters.
2. Report in plain words: where the price sits against the EMAs and its 24h /
   7d range, RSI, MACD direction, ATR as the normal bar size, nearest
   pivots. Facts, not calls.
3. For a planned trade, run `sim` with the user's own entry, stop, target,
   horizon and leverage. Repeat the verdict line exactly, say the seed, and
   say plainly when it leans toward the stop or is close to break-even.
   If the leverage puts liquidation before the stop, say that first.
4. Positioning by profitability tier and liquidation heatmaps are not in the
   public API; the Coinversa Pulse connector has them on its paid plan.

## Rules

- Read-only. Never ask for, accept or store a private key, seed phrase or API
  wallet secret; if the user pastes one, tell them to move their funds and
  rotate it. Never place, cancel or change an order.
- Every number comes from the tool. Never round a coin flip into an edge.
- Indicators and simulations describe the past; they are not forecasts.
- The liquidation price is an isolated-margin estimate (maintenance = half
  the initial margin at max leverage), ignoring fees and funding. Cross
  margin depends on the whole account; the exchange's own number wins.
- A wallet's positions are public data, not a signal to copy.
- Education and tooling, not financial advice.
