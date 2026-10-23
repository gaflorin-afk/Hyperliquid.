#!/usr/bin/env python3
"""crypto-trader: the Day Trader pack's chain, rebuilt for crypto perps on
Hyperliquid (24/7, the trading day starts at 00:00 UTC by default).

  scan      opening-range breakouts on today's 15-minute bars, or daily setups
  entry     the first closed 15m bar beyond the opening range (long or short)
  exit      stop and target before the entry  -> crypto/plan.json
  tm        Time Machine: 10,000 replays + the same rule on every past day
  budget    size to your max loss, leverage and margin -> crypto/orders.json
  risk      PASS / BLOCK against your limits   -> crypto/state/risk.json
  ticket    the order as a ticket you type into Hyperliquid yourself
  alerts    has the plan's stop, target or flat-by time been hit

Standard library only. Reads https://api.hyperliquid.xyz/info (public, no key).
It never signs and never places, cancels or changes an order.
"""
import argparse
import datetime as _dt
import hashlib
import json
import os
import random
import statistics
import sys
import time
import urllib.error
import urllib.request

API = "https://api.hyperliquid.xyz/info"
UA = "crypto-trader/1.0 (read-only)"
BAR = 900_000                      # 15 minutes
DAY = 86_400_000
SLOTS = DAY // BAR                 # 96 bars a day
DIR = "crypto"
STATE = os.path.join(DIR, "state")
DEFAULTS = {
    "coins": ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "HYPE", "SUI", "AVAX", "LINK"],
    "day_start_utc": "00:00",
    "or_minutes": 60,
    "no_entries_after": "22:00",
    "flat_by": "23:45",
    "budget": 1000,
    "cash_buffer_pct": 10,
    "max_loss_per_trade_usd": 10,
    "max_daily_loss_usd": 30,
    "max_trades_per_day": 3,
    "min_reward_risk": 1.0,
    "leverage": 2,
    "max_leverage": 3,
    "max_position_pct": 75,
    "allow_short": True,
    "blocked": [],
    "paper": True,
}
NOW = None                         # pinned clock (ms), or None for live


# ================================================================ basics

def now_ms():
    return NOW if NOW is not None else int(time.time() * 1000)


def utc(ms, fmt="%Y-%m-%d %H:%M UTC"):
    return _dt.datetime.fromtimestamp(ms / 1000, _dt.timezone.utc).strftime(fmt)


def hhmm(ms):
    return utc(ms, "%H:%M")


def mins(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def config():
    c = dict(DEFAULTS)
    c.update(load(os.path.join(DIR, "config.json"), {}) or {})
    return c


def die(msg):
    print(msg)
    sys.exit(1)


def post(body, tries=3):
    data = json.dumps(body).encode()
    for k in range(tries):
        req = urllib.request.Request(API, data=data, headers={
            "Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and k < tries - 1:
                time.sleep(2 * (k + 1))
                continue
            die(f"Hyperliquid answered HTTP {e.code}.")
        except (urllib.error.URLError, TimeoutError) as e:
            if k < tries - 1:
                time.sleep(2 * (k + 1))
                continue
            die(f"Could not reach api.hyperliquid.xyz: {e}")


_META = None


def meta():
    """{coin: (szDecimals, maxLeverage, ctx)}"""
    global _META
    if _META is None:
        m, ctxs = post({"type": "metaAndAssetCtxs"})
        _META = {u["name"]: (u["szDecimals"], u["maxLeverage"], c)
                 for u, c in zip(m["universe"], ctxs)}
    return _META


def norm(c):
    return c if ":" in c else c.upper()


def candles(coin, interval="15m", days=53):
    """Closed bars up to the (pinned) clock, oldest first."""
    ms = {"15m": BAR, "1d": DAY}[interval]
    end = now_ms()
    raw = post({"type": "candleSnapshot", "req": {
        "coin": coin, "interval": interval, "startTime": end - days * DAY, "endTime": end}})
    return [{"t": c["t"], "o": float(c["o"]), "h": float(c["h"]), "l": float(c["l"]),
             "c": float(c["c"]), "v": float(c["v"])} for c in raw if c["t"] + ms <= end]


def mark(coin):
    """Current mark, or the last closed bar's close on a pinned clock."""
    if NOW is not None:
        cs = candles(coin, days=1)
        return cs[-1]["c"] if cs else None
    return float(meta()[coin][2]["markPx"])


# ---------------------------------------------------------------- session clock

def offset(cfg):
    return mins(cfg["day_start_utc"]) * 60_000


def session_of(t, cfg):
    return (t - offset(cfg)) // DAY


def slot_of(t, cfg):
    return ((t - offset(cfg)) % DAY) // BAR


def session_start(sess, cfg):
    return sess * DAY + offset(cfg)


def at(sess, clock, cfg):
    """ms of a UTC clock time inside a session (wraps past midnight if the day starts later)."""
    m = (mins(clock) - mins(cfg["day_start_utc"])) % 1440
    return session_start(sess, cfg) + m * 60_000


def label(sess, cfg):
    return utc(session_start(sess, cfg), "%a %Y-%m-%d")


# ---------------------------------------------------------------- prices and math

def px_decimals(coin):
    return max(0, 6 - meta()[coin][0])


def round_px(coin, x, mode="near"):
    """Hyperliquid perps: at most 5 significant figures and 6 - szDecimals decimals."""
    import math
    d = px_decimals(coin)
    if x > 0:
        d = min(d, max(0, 5 - int(math.floor(math.log10(x))) - 1))
    q = 10 ** d
    if mode == "down":
        return math.floor(x * q + 1e-9) / q
    if mode == "up":
        return math.ceil(x * q - 1e-9) / q
    return math.floor(x * q + 0.5) / q


def fp(x, coin=None):
    if coin:
        d = px_decimals(coin)
        if x > 0:
            import math
            d = min(d, max(0, 5 - int(math.floor(math.log10(x))) - 1))
        return f"{x:,.{d}f}"
    return f"{x:,.2f}" if abs(x) >= 1 else f"{x:.6g}"


def rsi(xs, n=14):
    if len(xs) <= n:
        return None
    g = [max(b - a, 0) for a, b in zip(xs, xs[1:])]
    l = [max(a - b, 0) for a, b in zip(xs, xs[1:])]
    ag, al = sum(g[:n]) / n, sum(l[:n]) / n
    for x, y in zip(g[n:], l[n:]):
        ag, al = (ag * (n - 1) + x) / n, (al * (n - 1) + y) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def atr(cs, n=14):
    trs = [max(c["h"] - c["l"], abs(c["h"] - p["c"]), abs(c["l"] - p["c"])) for p, c in zip(cs, cs[1:])]
    if not trs:
        return None
    if len(trs) < n:
        return sum(trs) / len(trs)
    a = sum(trs[:n]) / n
    for t in trs[n:]:
        a = (a * (n - 1) + t) / n
    return a


# ================================================================ opening range

def orb(cs, sess, cfg, side_pref=None):
    """Opening range of a session and its first trigger, on closed 15m bars.
    Returns a dict: status forming | waiting | triggered | expired | nodata."""
    orn = cfg["or_minutes"] // 15
    day = [c for c in cs if session_of(c["t"], cfg) == sess]
    start = session_start(sess, cfg)
    if not day or day[0]["t"] != start:
        return {"status": "nodata", "reason": "no bar at the session start"}
    rng = day[:orn]
    if len(rng) < orn or any(b["t"] != start + i * BAR for i, b in enumerate(rng)):
        return {"status": "forming" if len(day) < orn else "nodata",
                "reason": f"{len(rng)} of {orn} opening-range bars closed"}
    hi, lo = max(b["h"] for b in rng), min(b["l"] for b in rng)
    out = {"or_high": hi, "or_low": lo, "or_end": start + orn * BAR, "session": sess}
    cutoff = at(sess, cfg["no_entries_after"], cfg)
    for i, b in enumerate(day[orn:], start=orn):
        if b["t"] != start + i * BAR:
            return dict(out, status="nodata", reason=f"bar missing at {hhmm(start + i * BAR)}")
        close_t = b["t"] + BAR
        if close_t > cutoff:
            return dict(out, status="expired", last=b["c"])
        up = b["c"] > hi and side_pref in (None, "long")
        dn = b["c"] < lo and side_pref in (None, "short") and cfg["allow_short"]
        if up or dn:
            return dict(out, status="triggered", side="long" if up else "short", price=b["c"],
                        bar=i, bar_t=b["t"], time=close_t, volume=b["v"],
                        or_volume=sum(x["v"] for x in rng) / orn, idx=cs.index(b))
    last = day[-1]
    if now_ms() >= cutoff:
        return dict(out, status="expired", last=last["c"])
    return dict(out, status="waiting", last=last["c"], last_t=last["t"] + BAR)


# ================================================================ commands

def cmd_init(a):
    p = os.path.join(DIR, "config.json")
    if os.path.exists(p) and not a.force:
        print(f"{p} already exists (use --force to reset it).")
    else:
        save(p, DEFAULTS)
        print(f"Wrote {p} with the defaults. Edit budget, max loss, leverage and coins to yours.")
    c = config()
    for k in ("coins", "budget", "max_loss_per_trade_usd", "max_daily_loss_usd", "max_trades_per_day",
              "leverage", "max_leverage", "min_reward_risk", "day_start_utc", "or_minutes",
              "no_entries_after", "flat_by", "allow_short", "paper"):
        print(f"  {k}: {c[k]}")


def cmd_coins(a):
    cfg = config()
    coins = cfg["coins"]
    if a.action != "list":
        want = [norm(x) for x in a.symbols]
        if a.action != "remove":
            bad = [x for x in want if x not in meta()]
            if bad:
                die(f"Not Hyperliquid perps: {', '.join(bad)}. Nothing changed.")
        coins = (list(dict.fromkeys(want)) if a.action == "set" else
                 coins + [x for x in want if x not in coins] if a.action == "add" else
                 [x for x in coins if x not in want])
        if not coins:
            die("The coin list cannot be empty.")
        raw = load(os.path.join(DIR, "config.json"), {}) or dict(DEFAULTS)
        raw["coins"] = coins
        save(os.path.join(DIR, "config.json"), raw)
    print(f"Coins ({len(coins)}): {', '.join(coins)}")


def cmd_scan(a):
    cfg = config()
    coins = [norm(x) for x in a.coins.split(",")] if a.coins else cfg["coins"]
    t0 = now_ms()
    if a.mode == "daily":
        return scan_daily(coins, cfg, a)
    sess = session_of(t0, cfg)
    if t0 < session_start(sess, cfg) + cfg["or_minutes"] * 60_000:
        die(f"The {cfg['or_minutes']}-minute opening range of {label(sess, cfg)} closes at "
            f"{hhmm(session_start(sess, cfg) + cfg['or_minutes'] * 60_000)} UTC. Nothing to scan yet.")
    rows, failed = [], []
    for coin in coins:
        if coin not in meta():
            failed.append(coin)
            continue
        cs = candles(coin, days=2)
        time.sleep(0.15)
        r = orb(cs, sess, cfg)
        r["coin"] = coin
        (failed if r["status"] == "nodata" else rows).append(r if r["status"] != "nodata" else coin)
    hits = [r for r in rows if r["status"] == "triggered"]
    print(f"Opening-range scan, {label(sess, cfg)}, range {cfg['day_start_utc']} + {cfg['or_minutes']} min,"
          f" 15m bars, at {utc(t0)}")
    print(f"{len(rows)} of {len(coins)} coins usable; {len(hits)} broke out of their range:")
    for r in sorted(rows, key=lambda r: (r["status"] != "triggered", r.get("time", 0))):
        c, hi, lo = r["coin"], r["or_high"], r["or_low"]
        rng = f"range {fp(lo, c)} to {fp(hi, c)} ({(hi / lo - 1) * 100:.2f}%)"
        if r["status"] == "triggered":
            lvl = hi if r["side"] == "long" else lo
            print(f"  {hhmm(r['time'])}  {c:<6} {r['side'].upper():<5} close {fp(r['price'], c):>10}  {rng}"
                  f"  {(r['price'] / lvl - 1) * 100:+.2f}% beyond")
        else:
            last = r.get("last")
            print(f"  -----  {c:<6} {r['status']:<7} last {fp(last, c) if last else 'n/a':>8}  {rng}")
    if failed:
        print(f"  no data: {', '.join(failed)}")
    if not a.no_write:
        save(os.path.join(DIR, "watchlist.json"), {
            "mode": "orb", "as_of": utc(t0), "session": label(sess, cfg),
            "hits": [{"symbol": r["coin"], "side": r["side"], "time": hhmm(r["time"]),
                      "price": r["price"], "or_high": r["or_high"], "or_low": r["or_low"]} for r in hits]})
        print(f"Wrote {DIR}/watchlist.json.")
    print("A breakout matched a rule; it is not a buy or a sell. Pick one, then: entry COIN.")
    sys.exit(0 if hits else 1)


def scan_daily(coins, cfg, a):
    hits, n = [], 0
    for coin in coins:
        if coin not in meta():
            continue
        cs = candles(coin, "1d", 60)
        time.sleep(0.15)
        if len(cs) < 30:
            continue
        n += 1
        cl = [c["c"] for c in cs]
        last, prev = cl[-1], cl[-2]
        ma = sum(cl[-20:]) / 20
        mprev = sum(cl[-21:-1]) / 20
        r, rp = rsi(cl), rsi(cl[:-1])
        tags = []
        if last > max(cl[-21:-1]):
            tags.append("breakout_20d")
        if last < min(cl[-21:-1]):
            tags.append("breakdown_20d")
        if prev < mprev and last > ma:
            tags.append("reclaim_ma20")
        if prev > mprev and last < ma:
            tags.append("lost_ma20")
        if r < 30:
            tags.append("oversold")
        if rp is not None and rp < 30 and last > prev:
            tags.append("oversold_bounce")
        if r > 70:
            tags.append("overbought")
        print(f"  {coin:<6} close {fp(last, coin):>10}  {(last / prev - 1) * 100:+6.2f}%  RSI {r:5.1f}"
              f"  vs MA20 {(last / ma - 1) * 100:+6.2f}%  {', '.join(tags) or '-'}")
        if tags:
            hits.append({"symbol": coin, "setups": tags, "close": last})
    print(f"Daily scan of {n} coins on closed UTC daily bars (last {utc(cs[-1]['t'], '%Y-%m-%d')}):"
          f" {len(hits)} matched a rule.")
    if not a.no_write:
        save(os.path.join(DIR, "watchlist.json"), {"mode": "daily", "as_of": utc(now_ms()), "hits": hits})
        print(f"Wrote {DIR}/watchlist.json.")


def cmd_entry(a):
    cfg = config()
    coins = [norm(a.coin)] if a.coin else [h["symbol"] for h in
                                           (load(os.path.join(DIR, "watchlist.json"), {}) or {}).get("hits", [])]
    if not coins:
        die("Name a coin (entry BTC) or run scan first.")
    t0 = now_ms()
    sess = session_of(t0, cfg)
    for coin in coins:
        if coin not in meta():
            die(f"{coin} is not a Hyperliquid perp.")
        cs = candles(coin, days=2)
        r = orb(cs, sess, cfg, a.side)
        print(f"{coin}  {label(sess, cfg)} {hhmm(t0)} UTC  opening-range breakout ({cfg['or_minutes']}-minute range"
              f" from {cfg['day_start_utc']}) on 15-minute bars (Hyperliquid)")
        if r["status"] in ("nodata", "forming"):
            print(f"{r['status'].upper()}  {r['reason']}.")
            continue
        hi, lo = r["or_high"], r["or_low"]
        print(f"Opening range {cfg['day_start_utc']}-{hhmm(r['or_end'])}: high {fp(hi, coin)}, low {fp(lo, coin)}.")
        if r["status"] == "waiting":
            print(f"WAITING  last close {fp(r['last'], coin)} at {hhmm(r['last_t'])}:"
                  f" {(hi / r['last'] - 1) * 100:+.2f}% to the high, {(lo / r['last'] - 1) * 100:+.2f}% to the low."
                  f" Entries until {cfg['no_entries_after']} UTC.")
            continue
        if r["status"] == "expired":
            print(f"EXPIRED  no 15m close beyond the range before {cfg['no_entries_after']} UTC.")
            continue
        lvl = hi if r["side"] == "long" else lo
        volx = r["volume"] / r["or_volume"] if r["or_volume"] else 0
        print(f"TRIGGERED {hhmm(r['time'])} UTC  {r['side'].upper()} at {fp(r['price'], coin)}: the {hhmm(r['bar_t'])}"
              f" bar closed {'above' if r['side'] == 'long' else 'below'} {fp(lvl, coin)}"
              f" ({(r['price'] / lvl - 1) * 100:+.2f}%), volume {volx:.2f}x the range's average.")
        age = (t0 - r["time"]) // BAR
        if age >= 1:
            print(f"  That close was {age * 15} minutes ago: a late entry is a different trade.")
        print("Nothing was placed. Next: exit (the stop and the target BEFORE anything is bought).")
        if a.write or len(coins) == 1:
            save(os.path.join(DIR, "entry.json"), {
                "symbol": coin, "setup": "orb", "status": "triggered", "side": r["side"],
                "price": r["price"], "time": r["time"], "bar_t": r["bar_t"], "session": sess,
                "or_high": hi, "or_low": lo, "or_minutes": cfg["or_minutes"], "day_start_utc": cfg["day_start_utc"]})
            print(f"Wrote {DIR}/entry.json.")


def cmd_exit(a):
    cfg = config()
    e = load(os.path.join(DIR, "entry.json"))
    if not e or e.get("status") != "triggered":
        die("No triggered entry in crypto/entry.json. Run entry COIN first.")
    coin, side, entry = e["symbol"], e["side"], e["price"]
    long_ = side == "long"
    hi, lo = e["or_high"], e["or_low"]
    rule = a.stop
    if rule == "or-mid":
        raw, why = (hi + lo) / 2, f"opening-range midpoint ({fp(hi, coin)} + {fp(lo, coin)}) / 2"
    elif rule == "or-far":
        raw, why = (lo if long_ else hi), "the far side of the opening range"
    elif rule.startswith("pct:"):
        k = float(rule[4:]) / 100
        raw, why = entry * (1 - k if long_ else 1 + k), f"{rule[4:]}% from the entry"
    elif rule.startswith("atr:"):
        k = float(rule[4:])
        cs = [c for c in candles(coin, days=2) if c["t"] <= e["bar_t"]]
        v = atr(cs[-15:])
        raw, why = entry - k * v if long_ else entry + k * v, f"{k} x ATR14 ({fp(v, coin)}) on 15m bars"
    elif rule.startswith("price:"):
        raw, why = float(rule[6:]), "your price"
    else:
        die("Stop: or-mid, or-far, pct:X, atr:K or price:X.")
    stop = round_px(coin, raw, "down" if long_ else "up")
    if (long_ and stop >= entry) or (not long_ and stop <= entry):
        die(f"Refused: the stop {fp(stop, coin)} is on the wrong side of the entry {fp(entry, coin)}.")
    risk = abs(entry - stop)
    if risk / entry < 0.0005:
        die(f"Refused: risk {fp(risk, coin)} is under 0.05% of the price, too tight to survive normal wiggle.")
    if a.target.endswith("R"):
        R = float(a.target[:-1])
        target = round_px(coin, entry + R * risk if long_ else entry - R * risk)
    elif a.target.startswith("price:"):
        target = float(a.target[6:])
        R = abs(target - entry) / risk
    else:
        die("Target: 2R, 1.5R, 1R... or price:X.")
    if (long_ and target <= entry) or (not long_ and target >= entry):
        die("Refused: the target is on the wrong side of the entry.")
    flat = at(e["session"], cfg["flat_by"], cfg)
    if e["time"] >= flat:
        die("Refused: the entry is at or after the flat-by time.")
    plan = {"symbol": coin, "side": side, "session": e["session"], "date": label(e["session"], cfg),
            "entry": entry, "entry_time": e["time"], "entry_bar_t": e["bar_t"], "stop": stop, "stop_rule": rule,
            "target": target, "target_r": round(R, 2), "risk": risk, "reward_risk": round(R, 2),
            "flat_by": cfg["flat_by"], "flat_by_t": flat, "or_high": hi, "or_low": lo,
            "or_minutes": e["or_minutes"], "day_start_utc": e["day_start_utc"]}
    print(f"Exit plan: {coin} {side}, {plan['date']}, opening-range breakout on 15-minute bars")
    print(f"  Entry         {fp(entry, coin)} at {hhmm(e['time'])} UTC")
    print(f"  Stop          {fp(stop, coin)}  {why}, rounded away from the entry")
    print(f"  Target        {fp(target, coin)}  {R:g}R")
    print(f"  Risk a coin   {fp(risk, coin)} ({risk / entry * 100:.2f}% of the entry)")
    print(f"  Reward:risk   {R:.2f}")
    print(f"  Flat by       {cfg['flat_by']} UTC, win or lose")
    print("A stop is a plan, not a guarantee: a fast market or a liquidation cascade can fill past it.")
    if a.write:
        save(os.path.join(DIR, "plan.json"), plan)
        print(f"Wrote {DIR}/plan.json. Next: tm (Time Machine), then budget.")


def cmd_tm(a):
    cfg = config()
    p = load(os.path.join(DIR, "plan.json"))
    if not p:
        die("No crypto/plan.json. Run exit --write first.")
    coin, long_ = p["symbol"], p["side"] == "long"
    e, s, t, risk, R = p["entry"], p["stop"], p["target"], p["risk"], p["target_r"]
    cs = candles(coin, days=53)
    psess = p["session"]
    by = {}
    for c in cs:
        by.setdefault(session_of(c["t"], cfg), []).append(c)
    full = [k for k, v in sorted(by.items()) if k < psess and len(v) == SLOTS]
    if len(full) < 20:
        die(f"Only {len(full)} full past days of 15m bars: too few for a fair pool (needs 20).")
    # pool of bar ratios by slot, each relative to the close before it
    pool = [[] for _ in range(SLOTS)]
    prevc = None
    series = []
    for k in full:
        for i, c in enumerate(by[k]):
            if prevc is not None:
                pool[i].append((c["h"] / prevc, c["l"] / prevc, c["c"] / prevc))
            prevc = c["c"]
        series.append(by[k])
    first = slot_of(p["entry_time"], cfg)
    last = slot_of(p["flat_by_t"], cfg)
    nb = last - first
    rng = random.Random(a.seed)
    res = {"target": 0, "stop": 0, "neither": 0}
    rs, ends = [], []
    for _ in range(a.replays):
        px, out = e, None
        for k in range(nb):
            sl = min(SLOTS - 1, max(0, first + k + rng.randint(-a.window, a.window)))
            rh, rl, rc = rng.choice(pool[sl])
            hi, lo = px * rh, px * rl
            if (lo <= s) if long_ else (hi >= s):
                out = "stop"
                break
            if (hi >= t) if long_ else (lo <= t):
                out = "target"
                break
            px *= rc
        out = out or "neither"
        res[out] += 1
        r = R if out == "target" else -1.0 if out == "stop" else ((px - e) if long_ else (e - px)) / risk
        rs.append(r)
        ends.append(t if out == "target" else s if out == "stop" else px)
    n = a.replays
    ends.sort()
    green = sum(1 for r in rs if r > 0)
    print(f"{coin} {p['side']}, {p['date']}: entry {fp(e, coin)} at {hhmm(p['entry_time'])} UTC, stop {fp(s, coin)},"
          f" target {fp(t, coin)} ({R:g}R, risk {fp(risk, coin)} = {risk / e * 100:.2f}%).")
    print(f"{n:,} replays of the rest of the day, {hhmm(p['entry_time'])} to {p['flat_by']} UTC ({nb} bars of 15m),"
          f" seed {a.seed}.")
    print(f"Each bar is drawn whole from {coin}'s own 15m bars at the same time of day (+-{a.window} bars)"
          f" over its last {len(full)} full days ({label(full[0], cfg)[4:]} to {label(full[-1], cfg)[4:]}).")
    print()
    print(f"  target first  {res['target'] / n * 100:5.1f} %")
    print(f"  stop first    {res['stop'] / n * 100:5.1f} %")
    print(f"  neither       {res['neither'] / n * 100:5.1f} %   still open at {p['flat_by']} UTC")
    print(f"  green         {green / n * 100:5.1f} %   target first, or in profit at {p['flat_by']}")
    print(f"  Price at the exit or {p['flat_by']}: median {fp(ends[n // 2], coin)},"
          f" 90 % between {fp(ends[int(n * .05)], coin)} and {fp(ends[int(n * .95)], coin)}.")
    print(f"  Average R: {statistics.mean(rs):+.3f} (fees and funding not included)")
    # history: the same rule on every past day
    h = {"target": 0, "stop": 0, "neither": 0}
    hr = []
    fired = 0
    for k in full:
        allc = by[k]
        r = orb(allc, k, cfg, p["side"])
        if r["status"] != "triggered":
            continue
        fired += 1
        en = r["price"]
        if p["stop_rule"] == "or-mid":
            st = (r["or_high"] + r["or_low"]) / 2
        elif p["stop_rule"] == "or-far":
            st = r["or_low"] if long_ else r["or_high"]
        else:
            st = en * (1 - risk / e) if long_ else en * (1 + risk / e)
        rk = abs(en - st)
        if rk <= 0:
            fired -= 1
            continue
        tg = en + R * rk if long_ else en - R * rk
        out, px = "neither", en
        for c in allc[r["bar"] + 1:last]:
            if (c["l"] <= st) if long_ else (c["h"] >= st):
                out = "stop"
                break
            if (c["h"] >= tg) if long_ else (c["l"] <= tg):
                out = "target"
                break
            px = c["c"]
        h[out] += 1
        hr.append(R if out == "target" else -1.0 if out == "stop" else ((px - en) if long_ else (en - px)) / rk)
    print()
    if fired:
        print(f"History: the same rule ({p['or_minutes']}-min range from {p['day_start_utc']} UTC, {p['side']} on the"
              f" first 15m close beyond it, stop {p['stop_rule']}, {R:g}R target) on each of those {len(full)} days"
              f" fired {fired} times: {h['target']} target, {h['stop']} stop, {h['neither']} neither."
              f" Average R {statistics.mean(hr):+.3f}.")
    else:
        print(f"History: the rule never fired on those {len(full)} days.")
    hit = res["target"] + res["stop"]
    if hit:
        need, got = 100 / (1 + R), res["target"] / hit * 100
        gap = got - need
        if abs(gap) < 5:
            word = "Close to a coin flip" if abs(R - 1) < 1e-9 else "Close to break-even"
        elif abs(gap) < 15:
            word = "Leans toward the target" if gap > 0 else "Leans toward the stop"
        else:
            word = "Strongly toward the target" if gap > 0 else "Strongly toward the stop"
        print(f"{word}: target first {res['target'] / n * 100:.1f} % vs stop first {res['stop'] / n * 100:.1f} %"
              f" (of the replays that hit a side the target came first in {got:.1f} %; {R:g}R breaks even at {need:.1f} %).")
    if res["neither"] / n > 0.4:
        print(f"{res['neither'] / n * 100:.1f} % of the replays hit neither by {p['flat_by']}; the price then decides those.")
    print(f"A simulation from {coin}'s own last {len(full)} days, not a prediction. Same seed, same numbers: --seed {a.seed}.")
    if a.write:
        save(os.path.join(DIR, "timemachine.json"), {"plan": p, "mc": {k: v / n for k, v in res.items()},
                                                      "avg_r": statistics.mean(rs), "history": h, "seed": a.seed})
    print("Next: budget sizes it to your max loss and leverage.")


def liq_est(side, entry, lev, max_lev):
    d = 1 / lev - 1 / (2 * max_lev)
    if d <= 0:
        return None
    return entry * (1 - d) if side == "long" else entry * (1 + d)


def size_order(p, cfg, fresh=None):
    coin, long_ = p["symbol"], p["side"] == "long"
    szd, maxlev, _ = meta()[coin]
    lev = min(cfg["leverage"], cfg["max_leverage"], maxlev)
    entry = p["entry"]
    note = "the plan's entry"
    if fresh and ((long_ and fresh > entry) or (not long_ and fresh < entry)):
        entry, note = fresh, "the current mark, worse than the plan's entry"
    risk = abs(entry - p["stop"])
    rr = abs(p["target"] - entry) / risk if (p["target"] - entry) * (1 if long_ else -1) > 0 else 0
    q = 10 ** szd
    floor = lambda x: int(x * q) / q
    margin_cap = cfg["budget"] * (1 - cfg["cash_buffer_pct"] / 100)
    lim = {
        "max loss": (floor(cfg["max_loss_per_trade_usd"] / risk),
                     f"${cfg['max_loss_per_trade_usd']} / {fp(risk, coin)} risk a coin"),
        "position cap": (floor(cfg["budget"] * cfg["max_position_pct"] / 100 * lev / entry),
                         f"{cfg['max_position_pct']}% of ${cfg['budget']:,} x {lev:g}x / {fp(entry, coin)}"),
        "margin": (floor(margin_cap * lev / entry),
                   f"(${cfg['budget']:,} - {cfg['cash_buffer_pct']}% buffer) x {lev:g}x / {fp(entry, coin)}"),
    }
    binding = min(lim, key=lambda k: lim[k][0])
    sz = lim[binding][0]
    return {"coin": coin, "side": p["side"], "entry": entry, "entry_note": note, "risk": risk, "rr": rr,
            "lev": lev, "maxlev": maxlev, "limits": lim, "binding": binding, "size": sz,
            "notional": sz * entry, "margin": sz * entry / lev, "max_loss": sz * risk,
            "liq": liq_est(p["side"], entry, lev, maxlev)}


def cmd_budget(a):
    cfg = config()
    p = load(os.path.join(DIR, "plan.json"))
    if not p:
        die("No crypto/plan.json. Run exit --write first.")
    if p["session"] != session_of(now_ms(), cfg):
        die(f"The plan is for {p['date']}, not today. Make a new one with entry and exit.")
    coin = p["symbol"]
    o = size_order(p, cfg, mark(coin))
    print(f"{coin} {p['side']}, opening-range breakout, entry {fp(p['entry'], coin)} at {hhmm(p['entry_time'])} UTC")
    print(f"Sized at {fp(o['entry'], coin)} ({o['entry_note']}). Stop {fp(p['stop'], coin)}, target {fp(p['target'], coin)}."
          f" Risk {fp(o['risk'], coin)} a coin. Reward:risk {o['rr']:.2f}. Leverage {o['lev']:g}x isolated.")
    print("Limits (size rounded down to the coin's step; the smallest wins):")
    for k, (v, m) in o["limits"].items():
        print(f"  {k:<13} {m:<55} {v:>12g} {coin}{'  <- binds' if k == o['binding'] else ''}")
    refuse = []
    if o["size"] <= 0:
        refuse.append("the size rounds to zero")
    if o["notional"] < 10:
        refuse.append(f"${o['notional']:.2f} is under Hyperliquid's $10 minimum order")
    if o["rr"] < cfg["min_reward_risk"]:
        refuse.append(f"reward:risk {o['rr']:.2f} is under your minimum {cfg['min_reward_risk']}"
                      " (the move it waited for has mostly happened)")
    if o["liq"] and ((p["side"] == "long" and o["liq"] >= p["stop"]) or (p["side"] == "short" and o["liq"] <= p["stop"])):
        refuse.append(f"at {o['lev']:g}x the estimated liquidation {fp(o['liq'], coin)} comes before the stop")
    if coin in cfg["blocked"]:
        refuse.append(f"{coin} is on your blocked list")
    if refuse:
        die("No order: " + "; ".join(refuse) + ".")
    print(f"Size: {o['size']:g} {coin} = ${o['notional']:,.2f} notional, ${o['margin']:,.2f} margin at {o['lev']:g}x.")
    print(f"Max loss at the stop: {o['size']:g} x {fp(o['risk'], coin)} = ${o['max_loss']:,.2f}"
          f" (fees and funding extra; a stop can fill worse).")
    print(f"Estimated isolated liquidation {fp(o['liq'], coin)} ({abs(o['liq'] / o['entry'] - 1) * 100:.1f}% away;"
          f" the stop is {o['risk'] / o['entry'] * 100:.2f}% away).")
    order = {"coin": coin, "side": "buy" if p["side"] == "long" else "sell", "size": o["size"], "type": "market",
             "leverage": o["lev"], "margin": "isolated", "take_profit": p["target"], "stop_loss": p["stop"],
             "reduce_only": False,
             "why": f"opening-range breakout {p['side']} on {coin}: {o['size']:g}, bound by {o['binding']}"
                    f" (${o['max_loss']:,.2f} at the stop)",
             "plan": {"entry": o["entry"], "stop": p["stop"], "target": p["target"], "risk": o["risk"],
                      "max_loss": round(o["max_loss"], 2), "liq_est": o["liq"], "session": p["session"],
                      "flat_by": p["flat_by"], "entry_time": p["entry_time"]}}
    if a.write:
        save(os.path.join(DIR, "orders.json"), {"orders": [order]})
        print(f"Wrote 1 proposed order to {DIR}/orders.json. Nothing was placed. Next: risk.")


def fingerprint(o):
    core = {k: o[k] for k in ("coin", "side", "size", "type", "leverage", "take_profit", "stop_loss", "reduce_only")}
    return hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()[:16]


def journal():
    return load(os.path.join(STATE, "journal.json"), {"entries": []})


def cmd_risk(a):
    cfg = config()
    orders = (load(os.path.join(DIR, "orders.json"), {}) or {}).get("orders", [])
    if not orders:
        die("No orders in crypto/orders.json. Run budget --write first.")
    t0 = now_ms()
    sess = session_of(t0, cfg)
    today = [x for x in journal()["entries"] if x["session"] == sess and x.get("kind") == "entry"]
    used_loss = sum(x["max_loss"] for x in today)
    open_coins = {x["coin"] for x in journal()["entries"] if x.get("status") == "open"}
    verdicts, ok_all = [], True
    for i, o in enumerate(orders, 1):
        coin = o["coin"]
        reasons, warns = [], []
        exit_ = o.get("reduce_only")
        long_ = o["side"] == "buy"
        pl = o.get("plan", {})
        if coin not in meta():
            reasons.append("not a Hyperliquid perp")
        if not exit_:
            if coin not in cfg["coins"]:
                reasons.append(f"{coin} is not in your coin list")
            if coin in cfg["blocked"]:
                reasons.append(f"{coin} is blocked")
            if not long_ and not cfg["allow_short"]:
                reasons.append("short selling is off (allow_short false)")
            st, tg = o.get("stop_loss"), o.get("take_profit")
            if st is None:
                reasons.append("no stop-loss")
            m = mark(coin)
            en = pl.get("entry", m)
            if m and ((long_ and m > en) or (not long_ and m < en)):
                warns.append(f"measured from the current mark {fp(m, coin)}, worse than the plan's {fp(en, coin)}")
                en = m
            if st is not None:
                if (long_ and st >= en) or (not long_ and st <= en):
                    reasons.append(f"the stop {fp(st, coin)} is on the wrong side of {fp(en, coin)}")
                else:
                    loss = o["size"] * abs(en - st)
                    rr = abs(tg - en) / abs(en - st) if tg else 0
                    if (tg - en) * (1 if long_ else -1) <= 0:
                        rr = 0
                    if loss > cfg["max_loss_per_trade_usd"] + 1e-9:
                        reasons.append(f"loss: {o['size']:g} x {fp(abs(en - st), coin)} = ${loss:,.2f} at the stop,"
                                       f" over your ${cfg['max_loss_per_trade_usd']} max loss per trade")
                    if rr < cfg["min_reward_risk"]:
                        reasons.append(f"reward:risk {rr:.2f} under your minimum {cfg['min_reward_risk']}")
                    if used_loss + loss > cfg["max_daily_loss_usd"] + 1e-9:
                        reasons.append(f"daily loss: ${used_loss:,.2f} already at risk today + ${loss:,.2f}"
                                       f" > ${cfg['max_daily_loss_usd']}")
                    lq = liq_est("long" if long_ else "short", en, o["leverage"], meta()[coin][1])
                    if lq and ((long_ and lq >= st) or (not long_ and lq <= st)):
                        reasons.append(f"liquidation ~{fp(lq, coin)} comes before the stop")
                    o["_loss"] = loss
                    o["_rr"] = rr
            if o["leverage"] > min(cfg["max_leverage"], meta()[coin][1]):
                reasons.append(f"leverage {o['leverage']}x over your max {cfg['max_leverage']}x")
            if o["size"] * (en or 0) < 10:
                reasons.append("under Hyperliquid's $10 minimum")
            if len(today) >= cfg["max_trades_per_day"]:
                reasons.append(f"trades: {len(today)} of {cfg['max_trades_per_day']} already today")
            if coin in open_coins:
                reasons.append(f"you already have an open {coin} position in the journal")
            cut = at(sess, cfg["no_entries_after"], cfg)
            start = session_start(sess, cfg) + cfg["or_minutes"] * 60_000
            if not (start <= t0 <= cut):
                reasons.append(f"window: new entries only {hhmm(start)}-{cfg['no_entries_after']} UTC")
            if pl.get("session") is not None and pl["session"] != sess:
                reasons.append("the plan is from another day")
        status = "BLOCK" if reasons else "PASS"
        ok_all &= not reasons
        verdicts.append({"index": i, "fp": fingerprint(o), "status": status, "reasons": reasons, "session": sess})
        print(f"{status:<5} #{i} {o['side']} {o['size']:g} {coin} {'(exit)' if exit_ else '(entry)'}"
              f" at {o['leverage']:g}x, stop {fp(o['stop_loss'], coin) if o.get('stop_loss') else '-'},"
              f" target {fp(o['take_profit'], coin) if o.get('take_profit') else '-'}")
        if "_loss" in o:
            print(f"          max loss ${o['_loss']:,.2f} (limit ${cfg['max_loss_per_trade_usd']}),"
                  f" reward:risk {o['_rr']:.2f} (min {cfg['min_reward_risk']})")
            print(f"          today before this: {len(today)} of {cfg['max_trades_per_day']} trades,"
                  f" ${used_loss:,.2f} of ${cfg['max_daily_loss_usd']} daily loss")
        for w in warns:
            print(f"        ~ {w}")
        for r in reasons:
            print(f"        - {r}")
        if status == "PASS" and not exit_:
            used_loss += o.get("_loss", 0)
    if not a.no_write:
        save(os.path.join(STATE, "risk.json"), {"as_of": t0, "verdicts": verdicts})
    acct = "paper (you type it in yourself)" if cfg["paper"] else "LIVE"
    print(f"{sum(v['status'] == 'PASS' for v in verdicts)} passed, {sum(v['status'] == 'BLOCK' for v in verdicts)}"
          f" blocked at {utc(t0)}. Account: {acct}.")
    print("A PASS is a rules check, not a recommendation and not your yes.")
    sys.exit(0 if ok_all else 1)


def cmd_ticket(a):
    cfg = config()
    t0 = now_ms()
    sess = session_of(t0, cfg)
    orders = (load(os.path.join(DIR, "orders.json"), {}) or {}).get("orders", [])
    risk = load(os.path.join(STATE, "risk.json"), {}) or {}
    ver = {v["fp"]: v for v in risk.get("verdicts", []) if v.get("session") == sess}
    j = journal()
    if a.action == "show":
        if not orders:
            die("No orders. Run budget --write, then risk.")
        for i, o in enumerate(orders, 1):
            v = ver.get(fingerprint(o))
            ready = v and v["status"] == "PASS"
            coin = o["coin"]
            pl = o.get("plan", {})
            print(f"TICKET {i} of {len(orders)}  {'READY: risk PASS' if ready else 'NOT READY: run risk' if not v else 'BLOCKED by risk'}")
            print(f"  {o['side'].upper()} {o['size']:g} {coin} perp on Hyperliquid, {o['type']}, {o['leverage']:g}x {o['margin']}")
            print(f"  take-profit {fp(o['take_profit'], coin)}   stop-loss {fp(o['stop_loss'], coin)}")
            print(f"  max loss about ${pl.get('max_loss', 0):,.2f} at the stop; estimated liquidation {fp(pl['liq_est'], coin) if pl.get('liq_est') else 'n/a'}")
            print(f"  close it by {pl.get('flat_by', cfg['flat_by'])} UTC, win or lose")
            print(f"  why: {o['why']}")
            if ready:
                print("  To place it yourself on app.hyperliquid.xyz:")
                print(f"    1. Pick {coin}-USD, set the margin mode to Isolated and leverage to {o['leverage']:g}x.")
                print(f"    2. {'Buy / Long' if o['side'] == 'buy' else 'Sell / Short'}, Market, size {o['size']:g} {coin}.")
                print(f"    3. Tick TP/SL: take profit {fp(o['take_profit'], coin)}, stop loss {fp(o['stop_loss'], coin)}.")
                print("    4. Check the numbers on Hyperliquid's own confirm screen; theirs are the real ones.")
                print(f"  Then record it: ticket placed --index {i} --price <your fill>")
            print()
        print("Claude never places this order. You decide, and you type it in yourself.")
    elif a.action == "placed":
        if not 1 <= a.index <= len(orders):
            die(f"No ticket {a.index}: there are {len(orders)} in crypto/orders.json.")
        o = orders[a.index - 1]
        v = ver.get(fingerprint(o))
        if not v or v["status"] != "PASS":
            die("Not recorded: this order has no PASS from risk today.")
        pr = a.price or o["plan"]["entry"]
        ml = o["size"] * abs(pr - o["stop_loss"])
        j["entries"].append({"kind": "entry", "session": sess, "time": utc(t0), "coin": o["coin"],
                             "side": "long" if o["side"] == "buy" else "short", "size": o["size"], "price": pr,
                             "stop": o["stop_loss"], "target": o["take_profit"], "max_loss": round(ml, 2),
                             "status": "open"})
        save(os.path.join(STATE, "journal.json"), j)
        print(f"Recorded: {o['side']} {o['size']:g} {o['coin']} at {fp(pr, o['coin'])}, max loss ${ml:,.2f}."
              " It now counts against today's limits.")
    elif a.action == "closed":
        coin = norm(a.coin or "")
        op = [x for x in j["entries"] if x.get("status") == "open" and x["coin"] == coin]
        if not op or a.price is None:
            die("Usage: ticket closed --coin BTC --price 82000 (an open journal entry is needed).")
        x = op[-1]
        sign = 1 if x["side"] == "long" else -1
        x["status"] = "closed"
        x["exit"] = a.price
        x["r"] = round(sign * (a.price - x["price"]) / abs(x["price"] - x["stop"]), 2)
        save(os.path.join(STATE, "journal.json"), j)
        print(f"Closed {coin} {x['side']} at {fp(a.price, coin)}: {x['r']:+.2f}R (before fees and funding).")
    else:
        if not j["entries"]:
            print("The journal is empty.")
        for x in j["entries"]:
            print(f"  {x['time']}  {x['coin']:<6} {x['side']:<5} {x['size']:g} at {fp(x['price'], x['coin'])}"
                  f"  stop {fp(x['stop'], x['coin'])}  max loss ${x['max_loss']:,.2f}  {x['status']}"
                  + (f"  exit {fp(x['exit'], x['coin'])} {x['r']:+.2f}R" if x.get("exit") else ""))


def cmd_alerts(a):
    cfg = config()
    p = load(os.path.join(DIR, "plan.json"))
    if not p:
        die("No crypto/plan.json.")
    coin, long_ = p["symbol"], p["side"] == "long"
    t0 = now_ms()
    cs = [c for c in candles(coin, days=2) if c["t"] >= p["entry_time"]]
    hit = None
    for c in cs:
        if (c["l"] <= p["stop"]) if long_ else (c["h"] >= p["stop"]):
            hit = ("STOP", c)
            break
        if (c["h"] >= p["target"]) if long_ else (c["l"] <= p["target"]):
            hit = ("TARGET", c)
            break
    m = mark(coin)
    print(f"{coin} {p['side']} plan: entry {fp(p['entry'], coin)}, stop {fp(p['stop'], coin)},"
          f" target {fp(p['target'], coin)}. Now {fp(m, coin)} at {utc(t0)}.")
    if hit:
        print(f"ALERT {hit[0]}: the {hhmm(hit[1]['t'])} bar touched {fp(p['stop' if hit[0] == 'STOP' else 'target'], coin)}."
              " If the TP/SL was set, it has probably filled: check Hyperliquid, then ticket closed.")
    elif t0 >= p["flat_by_t"]:
        print(f"ALERT flat by {p['flat_by']} UTC: close anything still open (reduce-only market), then ticket closed.")
    else:
        print(f"Nothing hit. {(p['flat_by_t'] - t0) // 60000} minutes to the flat-by time {p['flat_by']} UTC.")


# ================================================================ main

def main():
    global NOW
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--now", help='pin the clock, UTC: "2026-10-22 10:00"')
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("coins"); p.add_argument("action", choices=["list", "set", "add", "remove"])
    p.add_argument("symbols", nargs="*")
    p = sub.add_parser("scan"); p.add_argument("mode", nargs="?", default="orb", choices=["orb", "daily"])
    p.add_argument("--coins"); p.add_argument("--no-write", action="store_true")
    p = sub.add_parser("entry"); p.add_argument("coin", nargs="?")
    p.add_argument("--side", choices=["long", "short"]); p.add_argument("--write", action="store_true")
    p = sub.add_parser("exit"); p.add_argument("--stop", default="or-mid"); p.add_argument("--target", default="2R")
    p.add_argument("--write", action="store_true")
    p = sub.add_parser("tm"); p.add_argument("--replays", type=int, default=10000)
    p.add_argument("--seed", type=int, default=19); p.add_argument("--window", type=int, default=2)
    p.add_argument("--write", action="store_true")
    p = sub.add_parser("budget"); p.add_argument("--write", action="store_true")
    p = sub.add_parser("risk"); p.add_argument("--no-write", action="store_true")
    p = sub.add_parser("ticket"); p.add_argument("action", nargs="?", default="show",
                                                 choices=["show", "placed", "closed", "log"])
    p.add_argument("--index", type=int, default=1); p.add_argument("--price", type=float)
    p.add_argument("--coin")
    sub.add_parser("alerts")
    a = ap.parse_args()
    if a.now:
        NOW = int(_dt.datetime.strptime(a.now, "%Y-%m-%d %H:%M").replace(tzinfo=_dt.timezone.utc).timestamp() * 1000)
    if a.cmd == "coins" and a.action != "list" and not a.symbols:
        die(f"coins {a.action} needs symbols, e.g. coins {a.action} BTC ETH")
    {"init": cmd_init, "coins": cmd_coins, "scan": cmd_scan, "entry": cmd_entry, "exit": cmd_exit,
     "tm": cmd_tm, "budget": cmd_budget, "risk": cmd_risk, "ticket": cmd_ticket,
     "alerts": cmd_alerts}[a.cmd](a)


if __name__ == "__main__":
    main()
