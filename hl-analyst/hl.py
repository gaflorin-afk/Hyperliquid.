#!/usr/bin/env python3
"""Read-only Hyperliquid analyst: snapshot, technicals, funding, book walls,
any wallet's positions, and a time-machine replay of a long or short plan.

Standard library only. Talks only to https://api.hyperliquid.xyz/info (public,
no key). It never signs, never places, cancels or changes an order.
"""
import argparse
import datetime as _dt
import json
import math
import os
import random
import statistics
import sys
import time
import urllib.error
import urllib.request

API = "https://api.hyperliquid.xyz/info"
UA = "hl-analyst/1.0 (read-only)"
IV_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000,
         "4h": 14_400_000, "1d": 86_400_000}
WATCHLIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.json")
DEFAULT_COINS = ["BTC", "ETH", "SOL"]
FUNDING_HOT = 0.00005      # 0.005 % an hour, about 44 % a year: a crowded side


# ---------------------------------------------------------------- watchlist

def load_coins():
    try:
        with open(WATCHLIST, encoding="utf-8") as fh:
            coins = json.load(fh).get("coins") or []
        return coins or list(DEFAULT_COINS)
    except (OSError, ValueError):
        return list(DEFAULT_COINS)


def save_coins(coins):
    tmp = WATCHLIST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"coins": coins}, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, WATCHLIST)


def norm(c):
    return c if ":" in c else c.upper()


# ---------------------------------------------------------------- data

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
            sys.exit(f"Hyperliquid answered HTTP {e.code} for {body.get('type')}.")
        except (urllib.error.URLError, TimeoutError) as e:
            if k < tries - 1:
                time.sleep(2 * (k + 1))
                continue
            sys.exit(f"Could not reach api.hyperliquid.xyz: {e}")


def now_ms():
    return int(time.time() * 1000)


def utc(ms):
    return _dt.datetime.fromtimestamp(ms / 1000, _dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def asset(coin):
    meta, ctxs = post({"type": "metaAndAssetCtxs"})
    names = [u["name"] for u in meta["universe"]]
    if coin not in names:
        sys.exit(f"{coin} is not a Hyperliquid perp (names are case-sensitive: BTC, ETH, SOL...).")
    i = names.index(coin)
    return meta["universe"][i], ctxs[i]


def candles(coin, interval, bars):
    """Closed candles only, oldest first, as dicts of floats."""
    end = now_ms()
    start = end - (bars + 2) * IV_MS[interval]
    raw = post({"type": "candleSnapshot", "req": {
        "coin": coin, "interval": interval, "startTime": start, "endTime": end}})
    out = []
    for c in raw:
        if c["T"] >= end:          # still forming
            continue
        out.append({"t": c["t"], "o": float(c["o"]), "h": float(c["h"]),
                    "l": float(c["l"]), "c": float(c["c"]), "v": float(c["v"])})
    return out[-bars:]


# ---------------------------------------------------------------- math

def ema(xs, n):
    if len(xs) < n:
        return None
    k = 2 / (n + 1)
    e = sum(xs[:n]) / n
    for x in xs[n:]:
        e = x * k + e * (1 - k)
    return e


def rsi(xs, n=14):
    if len(xs) <= n:
        return None
    gains = [max(xs[i] - xs[i - 1], 0) for i in range(1, len(xs))]
    losses = [max(xs[i - 1] - xs[i], 0) for i in range(1, len(xs))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag, al = (ag * (n - 1) + g) / n, (al * (n - 1) + l) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def atr(cs, n=14):
    if len(cs) <= n:
        return None
    trs = [max(c["h"] - c["l"], abs(c["h"] - p["c"]), abs(c["l"] - p["c"]))
           for p, c in zip(cs, cs[1:])]
    a = sum(trs[:n]) / n
    for t in trs[n:]:
        a = (a * (n - 1) + t) / n
    return a


def ema_series(xs, n):
    """EMA at every index from n-1 on (None before)."""
    out = [None] * len(xs)
    if len(xs) < n:
        return out
    k = 2 / (n + 1)
    e = sum(xs[:n]) / n
    out[n - 1] = e
    for i in range(n, len(xs)):
        e = xs[i] * k + e * (1 - k)
        out[i] = e
    return out


def macd(xs):
    if len(xs) < 35:
        return None
    k12, k26, k9 = 2 / 13, 2 / 27, 2 / 10
    e12 = sum(xs[:12]) / 12
    e26 = sum(xs[:26]) / 26
    line = []
    for i, x in enumerate(xs):
        if i >= 12:
            e12 = x * k12 + e12 * (1 - k12)
        if i >= 26:
            e26 = x * k26 + e26 * (1 - k26)
            line.append(e12 - e26)
    sig = sum(line[:9]) / 9
    for v in line[9:]:
        sig = v * k9 + sig * (1 - k9)
    return line[-1], sig, line[-1] - sig


def fmt(x, d=1):
    return "n/a" if x is None else f"{x:,.{d}f}"


def pct(a, b):
    return (a / b - 1) * 100


# ---------------------------------------------------------------- commands

def cmd_snapshot(a):
    u, c = asset(a.coin)
    mark, prev = float(c["markPx"]), float(c["prevDayPx"])
    f = float(c["funding"])
    oi = float(c["openInterest"])
    print(f"{a.coin} perp on Hyperliquid, {utc(now_ms())}")
    print(f"  mark {fmt(mark)}  oracle {fmt(float(c['oraclePx']))}  mid {fmt(float(c['midPx']))}")
    print(f"  24h change {pct(mark, prev):+.2f}% (prev day {fmt(prev)})")
    print(f"  24h volume ${float(c['dayNtlVlm']) / 1e9:,.2f}B")
    print(f"  open interest {oi:,.2f} {a.coin} = ${oi * mark / 1e9:,.2f}B")
    side = "longs pay shorts" if f > 0 else "shorts pay longs" if f < 0 else "flat"
    print(f"  funding {f * 100:+.5f}% an hour ({side}), {f * 24 * 365 * 100:+.1f}% a year if it stayed")
    print(f"  premium {float(c['premium']) * 100:+.4f}%   max leverage {u['maxLeverage']}x")


def cmd_ta(a):
    cs = candles(a.coin, a.interval, 300)
    if len(cs) < 60:
        sys.exit("Too few closed candles for technicals.")
    cl = [c["c"] for c in cs]
    last = cs[-1]
    p = cl[-1]
    print(f"{a.coin} {a.interval} technicals, last closed bar {utc(last['t'])} (close {fmt(p)}), {len(cs)} bars")
    for n in (20, 50, 200):
        e = ema(cl, n)
        if e:
            print(f"  EMA{n:<4} {fmt(e):>12}  price {'above' if p > e else 'below'} it ({pct(p, e):+.2f}%)")
    r = rsi(cl)
    tag = "overbought (>70)" if r > 70 else "oversold (<30)" if r < 30 else "neutral"
    print(f"  RSI14    {r:12.1f}  {tag}")
    m = macd(cl)
    if m:
        print(f"  MACD     line {m[0]:+.1f}  signal {m[1]:+.1f}  histogram {m[2]:+.1f}"
              f" ({'above' if m[2] > 0 else 'below'} signal)")
    t = atr(cs)
    print(f"  ATR14    {fmt(t):>12}  ({t / p * 100:.2f}% of price: a typical {a.interval} bar's range)")
    # ranges and daily pivots from 1h bars (UTC days)
    hs = candles(a.coin, "1h", 24 * 8)
    for label, n in (("24h", 24), ("7d", 24 * 7)):
        w = hs[-n:]
        hi, lo = max(c["h"] for c in w), min(c["l"] for c in w)
        print(f"  {label} range {fmt(lo)} to {fmt(hi)}; price at {(p - lo) / (hi - lo) * 100:.0f}% of it")
    today = _dt.datetime.now(_dt.timezone.utc).date()
    yday = [c for c in hs if _dt.datetime.fromtimestamp(c["t"] / 1000, _dt.timezone.utc).date()
            == today - _dt.timedelta(days=1)]
    if len(yday) == 24:
        H, L, C = max(c["h"] for c in yday), min(c["l"] for c in yday), yday[-1]["c"]
        P = (H + L + C) / 3
        print(f"  pivots (yesterday UTC H {fmt(H)} L {fmt(L)} C {fmt(C)}):"
              f" S2 {fmt(P - (H - L))}  S1 {fmt(2 * P - H)}  P {fmt(P)}  R1 {fmt(2 * P - L)}  R2 {fmt(P + (H - L))}")
    print("Indicators describe the past bars. They are not a forecast.")


def cmd_funding(a):
    rows = post({"type": "fundingHistory", "coin": a.coin, "startTime": now_ms() - a.days * 86_400_000})
    if not rows:
        sys.exit("No funding history returned.")
    fr = [float(r["fundingRate"]) for r in rows]
    print(f"{a.coin} hourly funding, last {a.days} days ({len(fr)} hours), {utc(rows[0]['time'])} to {utc(rows[-1]['time'])}")
    print(f"  latest {fr[-1] * 100:+.5f}%  mean {statistics.mean(fr) * 100:+.5f}%  "
          f"min {min(fr) * 100:+.5f}%  max {max(fr) * 100:+.5f}%")
    print(f"  hours positive {sum(1 for x in fr if x > 0)}, negative {sum(1 for x in fr if x < 0)}")
    print(f"  a 1x long held the whole window paid {sum(fr) * 100:+.3f}% of its notional"
          f" (x your leverage for % of margin)")
    days = {}
    for r in rows:
        d = utc(r["time"])[:10]
        days.setdefault(d, []).append(float(r["fundingRate"]))
    for d, v in sorted(days.items())[-7:]:
        print(f"    {d}  sum {sum(v) * 100:+.4f}%  ({len(v)}h)")


def cmd_book(a):
    b = post({"type": "l2Book", "coin": a.coin})
    bids, asks = b["levels"]
    if not bids or not asks:
        sys.exit("Empty book.")
    bb, ba = float(bids[0]["px"]), float(asks[0]["px"])
    mid = (bb + ba) / 2
    print(f"{a.coin} order book {utc(b['time'])}: best bid {fmt(bb)}, best ask {fmt(ba)},"
          f" spread {ba - bb:.2f} ({(ba - bb) / mid * 1e4:.2f} bp)")
    bsz = sum(float(x["sz"]) for x in bids)
    asz = sum(float(x["sz"]) for x in asks)
    print(f"  visible depth: bids {bsz:,.2f} {a.coin} down to {fmt(float(bids[-1]['px']))},"
          f" asks {asz:,.2f} up to {fmt(float(asks[-1]['px']))} (imbalance {(bsz - asz) / (bsz + asz) * 100:+.0f}%)")
    for name, side in (("bids", bids), ("asks", asks)):
        top = sorted(side, key=lambda x: -float(x["sz"]))[:a.walls]
        print(f"  biggest {name}: " + ", ".join(
            f"{fmt(float(x['px']))} x {float(x['sz']):.2f} ({x['n']} orders)" for x in top))
    print("Hyperliquid shows about 20 levels a side; resting orders can be pulled at any time.")


def cmd_wallet(a):
    s = post({"type": "clearinghouseState", "user": a.address})
    ms = s.get("marginSummary", {})
    print(f"wallet {a.address}: account value ${float(ms.get('accountValue', 0)):,.2f},"
          f" notional ${float(ms.get('totalNtlPos', 0)):,.2f}, withdrawable ${float(s.get('withdrawable', 0)):,.2f}")
    pos = [p["position"] for p in s.get("assetPositions", [])]
    if not pos:
        print("  no open perp positions")
    for p in pos:
        sz = float(p["szi"])
        lev = p.get("leverage", {})
        print(f"  {p['coin']:<8} {'LONG ' if sz > 0 else 'SHORT'} {abs(sz):,.4f}"
              f"  entry {fmt(float(p['entryPx'] or 0), 2)}  value ${float(p['positionValue']):,.0f}"
              f"  uPnL ${float(p['unrealizedPnl']):,.0f}  lev {lev.get('value')}x {lev.get('type', '')}"
              f"  liq {fmt(float(p['liquidationPx']), 2) if p.get('liquidationPx') else 'n/a'}")
    print("Public on-chain data. A wallet's positions are not advice to copy them.")


def cmd_coins(a):
    coins = load_coins()
    if a.action == "list":
        print(f"Watchlist ({len(coins)}): {', '.join(coins)}")
        print(f"File: {WATCHLIST}")
        return
    names = {u["name"] for u in post({"type": "meta"})["universe"]}
    want = [norm(c) for c in a.symbols]
    if a.action != "remove":
        bad = [c for c in want if c not in names]
        if bad:
            sys.exit(f"Not Hyperliquid perps: {', '.join(bad)}. Nothing changed.")
    if a.action == "set":
        coins = list(dict.fromkeys(want))
    elif a.action == "add":
        coins += [c for c in want if c not in coins]
    else:
        coins = [c for c in coins if c not in want]
    if not coins:
        sys.exit("The watchlist cannot be empty. Nothing changed.")
    save_coins(coins)
    print(f"Watchlist ({len(coins)}): {', '.join(coins)}")


def setups(cs, rsi_now):
    """Rules on closed bars. Facts about the chart, not signals to trade."""
    cl = [c["c"] for c in cs]
    last, prev = cl[-1], cl[-2]
    e50 = ema_series(cl, 50)
    hits = []
    if last > max(cl[-21:-1]):
        hits.append("breakout_20")
    if last < min(cl[-21:-1]):
        hits.append("breakdown_20")
    if e50[-2] and prev < e50[-2] and last > e50[-1]:
        hits.append("reclaim_ema50")
    if e50[-2] and prev > e50[-2] and last < e50[-1]:
        hits.append("lost_ema50")
    if rsi_now < 30:
        hits.append("oversold")
    if rsi_now > 70:
        hits.append("overbought")
    return hits


def cmd_scan(a):
    coins = [norm(c) for c in a.coins.split(",")] if a.coins else load_coins()
    meta, ctxs = post({"type": "metaAndAssetCtxs"})
    idx = {u["name"]: i for i, u in enumerate(meta["universe"])}
    rows, skipped = [], []
    for coin in coins:
        if coin not in idx:
            skipped.append(coin)
            continue
        c = ctxs[idx[coin]]
        cs = candles(coin, a.interval, 300)
        time.sleep(0.2)
        if len(cs) < 60:
            skipped.append(coin)
            continue
        cl = [x["c"] for x in cs]
        p = cl[-1]
        r = rsi(cl)
        trend = "".join("+" if e and p > e else "-" for e in (ema(cl, 20), ema(cl, 50), ema(cl, 200)))
        w = cs[-min(len(cs), int(7 * 86_400_000 / IV_MS[a.interval]) or 1):]
        hi, lo = max(x["h"] for x in w), min(x["l"] for x in w)
        f = float(c["funding"])
        hits = setups(cs, r)
        if abs(f) >= FUNDING_HOT:
            hits.append("funding_hot_" + ("longs_pay" if f > 0 else "shorts_pay"))
        mark = float(c["markPx"])
        rows.append({
            "coin": coin, "price": mark, "chg24": pct(mark, float(c["prevDayPx"])),
            "funding": f, "oi_usd": float(c["openInterest"]) * mark, "rsi": r, "trend": trend,
            "atr_pct": atr(cs) / p * 100, "pos7d": (p - lo) / (hi - lo) * 100 if hi > lo else 50,
            "setups": hits, "bar": cs[-1]["t"]})
    if a.json:
        print(json.dumps({"interval": a.interval, "as_of": utc(now_ms()), "rows": rows,
                          "skipped": skipped}, indent=2))
        return
    print(f"Scan of {len(rows)} watchlist coin(s), {a.interval} bars, {utc(now_ms())}"
          f" (last closed bar {utc(rows[0]['bar']) if rows else 'n/a'})")
    print(f"  {'coin':<9}{'price':>12}{'24h':>8}{'fund/h':>10}{'OI $M':>9}{'RSI':>6}"
          f"{'EMA':>5}{'ATR%':>6}{'7d%':>5}  setups")
    for x in rows:
        pr = x["price"]
        ptxt = f"{pr:,.0f}" if pr >= 1000 else f"{pr:,.2f}" if pr >= 1 else f"{pr:.5g}"
        print(f"  {x['coin']:<9}{ptxt:>12}{x['chg24']:>+7.2f}%{x['funding'] * 100:>+9.5f}%"
              f"{x['oi_usd'] / 1e6:>9,.0f}{x['rsi']:>6.1f}{x['trend']:>5}{x['atr_pct']:>6.2f}"
              f"{x['pos7d']:>5.0f}  {', '.join(x['setups']) or '-'}")
    if skipped:
        print(f"  skipped (not a perp or too few bars): {', '.join(skipped)}")
    print("EMA: price above (+) or below (-) EMA 20/50/200. 7d%: where the price sits in its 7-day range"
          " (0 = low, 100 = high).")
    print("A setup is a chart that matched a rule, not a trade or a forecast. Check it with `ta` and `sim`.")


def liq_price(side, entry, lev, max_lev):
    """Isolated-margin estimate: liquidation when the loss eats the margin down
    to maintenance (half the initial margin at max leverage). Ignores fees and
    funding; cross margin liquidates later, depending on the whole account."""
    mm = 1 / (2 * max_lev)
    d = 1 / lev - mm
    if d <= 0:
        return None
    return entry * (1 - d) if side == "long" else entry * (1 + d)


def cmd_sim(a):
    long_ = a.side == "long"
    e, s, t = a.entry, a.stop, a.target
    if long_ and not (s < e < t):
        sys.exit("For a long the stop must be under the entry and the target above it.")
    if not long_ and not (t < e < s):
        sys.exit("For a short the stop must be above the entry and the target under it.")
    u, _ = asset(a.coin)
    liq = None
    if a.lev:
        if a.lev > u["maxLeverage"]:
            sys.exit(f"{a.coin} allows at most {u['maxLeverage']}x.")
        liq = liq_price(a.side, e, a.lev, u["maxLeverage"])
    cs = candles(a.coin, "15m", 5000)
    if len(cs) < 96 * 14:
        sys.exit("Fewer than 14 days of 15-minute bars: too few for a fair pool.")
    nb = int(a.hours * 4)
    risk = abs(e - s)
    R = abs(t - e) / risk
    # pool: each bar as ratios to the close before it, by quarter-hour slot of the UTC day
    slots = [[] for _ in range(96)]
    ratios = []
    for p, c in zip(cs, cs[1:]):
        r = (c["h"] / p["c"], c["l"] / p["c"], c["c"] / p["c"])
        ratios.append(r)
        slots[(c["t"] // IV_MS["15m"]) % 96].append(r)
    start_slot = (now_ms() // IV_MS["15m"]) % 96
    rng = random.Random(a.seed)
    stop_lvl = s
    liq_first = liq is not None and ((long_ and liq > s) or (not long_ and liq < s))
    if liq_first:
        stop_lvl = liq
    res = {"target": 0, "stop": 0, "liq": 0, "neither": 0}
    ends, rs = [], []
    for _ in range(a.replays):
        px, out = e, None
        for k in range(nb):
            sl = (start_slot + k) % 96
            cand = slots[(sl + rng.randint(-a.window, a.window)) % 96]
            rh, rl, rc = cand[rng.randrange(len(cand))]
            hi, lo = px * rh, px * rl
            if long_:
                if lo <= stop_lvl:
                    out = "liq" if liq_first else "stop"
                    break
                if hi >= t:
                    out = "target"
                    break
            else:
                if hi >= stop_lvl:
                    out = "liq" if liq_first else "stop"
                    break
                if lo <= t:
                    out = "target"
                    break
            px *= rc
        if out is None:
            out = "neither"
            ends.append(px)
            rs.append(((px - e) if long_ else (e - px)) / risk)
        else:
            ends.append(t if out == "target" else stop_lvl)
            rs.append(R if out == "target" else -abs(e - stop_lvl) / risk)
        res[out] += 1
    n = a.replays
    ends.sort()
    print(f"{a.coin} {a.side.upper()}: entry {fmt(e)}, stop {fmt(s)}, target {fmt(t)}"
          f" ({R:.2f}R, risk {fmt(risk)} = {risk / e * 100:.2f}%), next {a.hours:g}h ({nb} bars of 15m)")
    if a.lev:
        print(f"  leverage {a.lev}x: estimated isolated liquidation {fmt(liq) if liq else 'none'}"
              + ("  << BEFORE your stop: the stop can never fill, liquidation comes first" if liq_first else
                 f" ({abs(pct(liq, e)):.2f}% away; stop is {risk / e * 100:.2f}% away)"))
    print(f"{n:,} replays, each 15m bar drawn from {a.coin}'s own bars at the same UTC time of day"
          f" (+-{a.window} bars) over {len(cs) / 96:.0f} days ({utc(cs[0]['t'])[:10]} to {utc(cs[-1]['t'])[:10]}), seed {a.seed}.")
    print(f"  target first  {res['target'] / n * 100:5.1f} %")
    print(f"  stop first    {res['stop'] / n * 100:5.1f} %")
    if liq_first:
        print(f"  LIQUIDATED    {res['liq'] / n * 100:5.1f} %")
    print(f"  neither       {res['neither'] / n * 100:5.1f} %   still open after {a.hours:g}h")
    print(f"  price at the exit (or after {a.hours:g}h if still open): median {fmt(ends[n // 2])}, 90% between {fmt(ends[int(n * .05)])} and {fmt(ends[int(n * .95)])}")
    print(f"  average R {statistics.mean(rs):+.3f}  (open replays counted at their price after {a.hours:g}h;"
          " fees and funding not included)")
    # real history: the same % bracket from every past bar close
    up, dn = (t / e - 1, s / e - 1) if long_ else (s / e - 1, t / e - 1)
    h = {"target": 0, "stop": 0, "neither": 0}
    for i in range(0, len(ratios) - nb, a.step):
        f, out = 1.0, "neither"
        for rh, rl, rc in ratios[i + 1:i + 1 + nb]:
            hi, lo = f * rh - 1, f * rl - 1
            if long_:
                if lo <= dn:
                    out = "stop"; break
                if hi >= up:
                    out = "target"; break
            else:
                if hi >= up:
                    out = "stop"; break
                if lo <= dn:
                    out = "target"; break
            f *= rc
        h[out] += 1
    tot = sum(h.values())
    print(f"History: the same % stop and target from a bar close every {a.step * 15} min over those days"
          f" ({tot} starts, overlapping): target {h['target'] / tot * 100:.1f}%, stop {h['stop'] / tot * 100:.1f}%,"
          f" neither {h['neither'] / tot * 100:.1f}%.")
    hit = res["target"] + res["stop"] + res["liq"]
    if hit:
        need = 1 / (1 + R) * 100
        got = res["target"] / hit * 100
        gap = got - need
        word = ("Close to break-even" if abs(gap) < 5 else
                ("Leans toward the target" if gap > 0 else "Leans toward the stop") if abs(gap) < 15 else
                ("Strongly toward the target" if gap > 0 else "Strongly toward the stop"))
        print(f"{word}: of the replays that hit a side, the target came first in {got:.1f}%"
              f" (break-even at {R:.2f}R needs {need:.1f}%).")
    print("A simulation from the coin's own recent bars, not a prediction. A gap or a cascade of liquidations"
          " can move past any stop; same seed, same numbers.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--coin", default="BTC")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot")
    p = sub.add_parser("ta"); p.add_argument("--interval", default="1h", choices=list(IV_MS))
    p = sub.add_parser("funding"); p.add_argument("--days", type=int, default=7)
    p = sub.add_parser("book"); p.add_argument("--walls", type=int, default=3)
    p = sub.add_parser("wallet"); p.add_argument("address")
    p = sub.add_parser("coins", help="list / set / add / remove the watchlist")
    p.add_argument("action", choices=["list", "set", "add", "remove"])
    p.add_argument("symbols", nargs="*")
    p = sub.add_parser("scan", help="the watchlist coins only")
    p.add_argument("--interval", default="1h", choices=list(IV_MS))
    p.add_argument("--coins", help="comma list for this run only, e.g. BTC,ETH")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("sim")
    p.add_argument("--side", choices=["long", "short"], required=True)
    p.add_argument("--entry", type=float, required=True)
    p.add_argument("--stop", type=float, required=True)
    p.add_argument("--target", type=float, required=True)
    p.add_argument("--hours", type=float, default=24)
    p.add_argument("--lev", type=float)
    p.add_argument("--replays", type=int, default=10000)
    p.add_argument("--seed", type=int, default=19)
    p.add_argument("--window", type=int, default=2)
    p.add_argument("--step", type=int, default=4, help="history: start every N bars")
    a = ap.parse_args()
    a.coin = norm(a.coin)
    if a.cmd == "coins" and a.action != "list" and not a.symbols:
        sys.exit(f"coins {a.action} needs at least one symbol, e.g. coins {a.action} ETH SOL")
    {"snapshot": cmd_snapshot, "ta": cmd_ta, "funding": cmd_funding, "book": cmd_book,
     "wallet": cmd_wallet, "sim": cmd_sim, "coins": cmd_coins, "scan": cmd_scan}[a.cmd](a)


if __name__ == "__main__":
    main()
