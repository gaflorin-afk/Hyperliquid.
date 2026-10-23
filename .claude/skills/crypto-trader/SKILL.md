---
name: crypto-trader
description: >-
  The Day Trader pack rebuilt for crypto perps on Hyperliquid, for a short
  list of coins (default the top 10: BTC ETH SOL XRP DOGE BNB HYPE SUI AVAX
  LINK). The trading day starts at 00:00 UTC; the opening range is its first
  60 minutes on 15-minute bars. The same chain as the stock pack: scan ->
  entry -> exit -> Time Machine -> budget -> risk -> ticket -> alerts, long
  or short, with leverage, an estimated liquidation price and a trade
  journal. It ends at a ticket the user types into Hyperliquid themselves:
  it never signs or places an order. Use when the user says "crypto day
  trading", "scanează crypto", "breakout pe BTC", "pachetul pe crypto", "how
  many BTC can I trade", "risk check my crypto trade", or names one of the
  crypto-* commands.
argument-hint: "[init | coins | scan | entry | exit | tm | budget | risk | ticket | alerts]"
---

# crypto-trader

Jake Schincariol's Day Trader pack is built on the NYSE: a 9:30 open, a
4:00 close, US stocks only, and a risk check that blocks crypto. This is the
same method moved to a market that never closes. Everything comes from
Hyperliquid's public API (`api.hyperliquid.xyz`, no key). Leveraged crypto
moves fast and most people who day trade it lose money; nothing here changes
that.

One engine, `crypto.py` in this folder, runs every step. The commands
`/crypto-scanner`, `/crypto-entry`, `/crypto-exit`, `/crypto-timemachine`,
`/crypto-budget`, `/crypto-risk`, `/crypto-ticket` and `/crypto-alerts` are
thin skills over it, one per step, like the stock pack.

```bash
python3 "${CLAUDE_SKILL_DIR}/crypto.py" init                # crypto/config.json with the defaults
python3 "${CLAUDE_SKILL_DIR}/crypto.py" coins list          # set | add | remove
python3 "${CLAUDE_SKILL_DIR}/crypto.py" scan                # opening-range breakouts so far today
python3 "${CLAUDE_SKILL_DIR}/crypto.py" scan daily          # setups on daily closes
python3 "${CLAUDE_SKILL_DIR}/crypto.py" entry BTC           # waiting / triggered (long or short) / expired
python3 "${CLAUDE_SKILL_DIR}/crypto.py" exit --stop or-mid --target 2R --write
python3 "${CLAUDE_SKILL_DIR}/crypto.py" tm                  # 10,000 replays + every past day
python3 "${CLAUDE_SKILL_DIR}/crypto.py" budget --write
python3 "${CLAUDE_SKILL_DIR}/crypto.py" risk
python3 "${CLAUDE_SKILL_DIR}/crypto.py" ticket              # placed --index 1 --price P | closed --coin BTC --price P | log
python3 "${CLAUDE_SKILL_DIR}/crypto.py" alerts
python3 "${CLAUDE_SKILL_DIR}/crypto.py" top                 # steps 1-6 on every coin, the 5 best options
python3 "${CLAUDE_SKILL_DIR}/crypto.py" top --pick 2        # option 2 becomes the plan and the order
python3 "${CLAUDE_SKILL_DIR}/crypto.py" config budget=100 leverage=10   # show or set limits
```

`/crypto-daily` is the agent that runs `top` every day and presents the
five best options in short Romanian.

`--now "2026-10-22 01:45"` (UTC, before the command) pins the clock to replay
a past day on real data. Everything is written under `crypto/` in the
current folder.

## How it differs from the stock pack

| | stock pack | crypto-trader |
| --- | --- | --- |
| market | US stocks, Yahoo | Hyperliquid perps, top 10 by default |
| day | 9:30-16:00 New York | 24 h from `day_start_utc` (00:00 UTC) |
| opening range | 15 min on 5m bars | `or_minutes` (60) on 15m bars |
| entries | 9:45-15:30 | end of the range to `no_entries_after` (22:00 UTC) |
| flat by | 15:55 | `flat_by` (23:45 UTC) |
| side | long only | long or short (`allow_short`) |
| size | whole shares | the coin's size step, with leverage and margin |
| extra checks | PDT, cash | leverage cap, liquidation before the stop, $10 minimum |
| last step | Alpaca order after your yes | a ticket you type into Hyperliquid yourself |
| Time Machine pool | 60 days of 5m bars | ~50 days of 15m bars (Hyperliquid keeps 5,000 bars) |

## The config (`crypto/config.json`)

Run `init` once, then ask the user for each value in plain words and edit the
file: `budget` (only money they can afford to lose), `max_loss_per_trade_usd`,
`max_daily_loss_usd`, `max_trades_per_day`, `min_reward_risk`, `leverage` and
`max_leverage` (keep them low), `cash_buffer_pct`, `max_position_pct`,
`allow_short`, `blocked`, `coins`, and the clock: `day_start_utc`,
`or_minutes` (a multiple of 15), `no_entries_after`, `flat_by`. Never change a
limit on your own.

## Rules

- Say what was scanned, when, and on which bars. A breakout "matched a rule";
  never call it a buy, a sell or a winner.
- Stop and target are set before the entry. Never move a stop further away.
- Repeat the Time Machine's verdict line as printed and say the seed. Say
  plainly when it is a coin flip, close to break-even or leans to the stop.
- Every number comes from the tool. The liquidation price is an
  isolated-margin estimate; Hyperliquid's own confirm screen wins.
- A BLOCK is final for that order. A PASS is not a yes.
- Never ask for, accept or store a private key, seed phrase or API wallet
  secret. If the user pastes one, tell them to move their funds now. Never
  place, cancel or change an order; the user does it on Hyperliquid.
- `ticket placed` records only what the user says they placed, so the daily
  limits count it. Never record a trade they did not confirm.
- Education and tooling, not financial advice.
