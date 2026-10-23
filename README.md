# Hyperliquid skills

Skill-uri Claude pentru day trading crypto pe Hyperliquid. Metoda vine din
[Day Trader skill pack](https://github.com/Jakeschincariol/day-trader-skill)
al lui Jake Schincariol (făcut pentru acțiuni americane și bursa din New
York), rescrisă pentru o piață care merge non-stop.

Python standard, fără nimic de instalat, fără cont și fără cheie. Datele vin
din API-ul public Hyperliquid (`api.hyperliquid.xyz`).

**Niciun skill nu plasează ordine.** Lanțul se termină cu un bilet pe care îl
introduci tu pe Hyperliquid. Nu da niciodată cheia privată sau seed phrase-ul
nimănui, nici lui Claude.

## Lanțul de day trading

Ziua începe la 00:00 UTC. Intervalul de deschidere e prima oră, pe bare de
15 minute. Fiecare pas scrie un fișier în folderul `crypto/`, iar următorul
pornește de la el.

| # | comanda | ce face |
| --- | --- | --- |
| 1 | `/crypto-scanner` | caută breakout-uri din intervalul de deschidere, doar pe monedele tale; sau setup-uri pe grafic zilnic |
| 2 | `/crypto-entry BTC` | prima bară de 15 minute închisă peste sau sub interval: long sau short |
| 3 | `/crypto-exit` | stopul și ținta, înainte de intrare |
| 4 | `/crypto-timemachine` | 10.000 de simulări ale restului zilei, plus aceeași regulă pe ultimele ~50 de zile reale |
| 5 | `/crypto-budget` | mărimea poziției după buget, pierderea maximă și levier, cu prețul de lichidare estimat |
| 6 | `/crypto-risk` | PASS sau BLOCK față de limitele tale |
| 7 | `/crypto-ticket` | biletul de ordin, cu pașii exacți pe app.hyperliquid.xyz, și jurnalul |
| 8 | `/crypto-alerts` | s-a atins stopul, ținta sau ora de închidere |

`/crypto-trader` explică tot lanțul.

### Agentul zilnic: `/crypto-daily`

Face singur pașii 1-6 pe toate monedele și îți arată primele 5 opțiuni de
ordin, doar cele care trec toate limitele tale, ordonate după scor (media
R-ului din simulări și din istoricul regulii, înainte de taxe). Monedele care
au atins deja stopul sau ținta după breakout ies din listă; restul se
recalculează la prețul de acum.

```bash
python3 .claude/skills/crypto-trader/crypto.py top             # top 5 de acum
python3 .claude/skills/crypto-trader/crypto.py top --pick 1    # opțiunea 1 devine plan + ordin
python3 .claude/skills/crypto-trader/crypto.py risk && python3 .claude/skills/crypto-trader/crypto.py ticket
``` Toți pașii folosesc același motor,
`.claude/skills/crypto-trader/crypto.py`.

```bash
python3 .claude/skills/crypto-trader/crypto.py init            # crypto/config.json cu valorile implicite
python3 .claude/skills/crypto-trader/crypto.py coins list      # set | add | remove
python3 .claude/skills/crypto-trader/crypto.py scan            # sau: scan daily
python3 .claude/skills/crypto-trader/crypto.py entry BTC
python3 .claude/skills/crypto-trader/crypto.py exit --stop or-mid --target 2R --write
python3 .claude/skills/crypto-trader/crypto.py tm
python3 .claude/skills/crypto-trader/crypto.py budget --write
python3 .claude/skills/crypto-trader/crypto.py risk
python3 .claude/skills/crypto-trader/crypto.py ticket          # placed --index 1 --price P | closed --coin BTC --price P | log
python3 .claude/skills/crypto-trader/crypto.py alerts
python3 .claude/skills/crypto-trader/crypto.py config budget=100 leverage=10   # vezi sau schimbă limitele
```

`--now "2026-10-22 01:45"` (UTC, pus înaintea comenzii) fixează ceasul, ca să
reiei o zi trecută pe date reale.

### Setările (`crypto/config.json`)

Fișierul e în depozit, cu limitele tale; `config key=valoare` le schimbă.
Planurile, ordinele și jurnalul rămân doar local (ignorate de git).

| cheie | implicit | ce înseamnă |
| --- | --- | --- |
| `coins` | BTC ETH SOL XRP DOGE BNB HYPE SUI AVAX LINK | doar aceste monede |
| `day_start_utc` | 00:00 | când începe ziua |
| `or_minutes` | 60 | lungimea intervalului de deschidere (multiplu de 15) |
| `no_entries_after` / `flat_by` | 22:00 / 23:45 | ultima intrare / închiderea tuturor pozițiilor, UTC |
| `budget` | 1000 | doar bani pe care îți permiți să-i pierzi |
| `max_loss_per_trade_usd` / `max_daily_loss_usd` | 10 / 30 | pierderea maximă pe tranzacție / pe zi |
| `max_trades_per_day` | 3 | |
| `min_reward_risk` | 1.0 | |
| `leverage` / `max_leverage` | 2 / 3 | păstrează-le mici |
| `cash_buffer_pct` / `max_position_pct` | 10 / 75 | |
| `allow_short` | true | |
| `blocked` | [] | monede pe care nu vrei să le tranzacționezi |

### Exemplu real: BTC, joi 22 oct. 2026

Interval 00:00–01:00 UTC: 84.046 – 84.312. La 01:45 bara de 01:30 s-a închis
la 83.750, sub interval: **short**. Stop 84.179 (mijlocul intervalului), țintă
82.892 (2R). Time Machine: „close to break-even”; pe 50 de zile regula s-a
declanșat de 38 de ori (13 ținte, 25 stopuri). Cu $1.000 și levier 2x:
0,01791 BTC, pierdere maximă $7,68. Risc: PASS. Ținta a fost atinsă la
02:15 (+2R). La 02:00, cu prețul deja mișcat, același plan e refuzat
(reward:risk 0,59).

## Analistul

`/hl-analyst` analizează orice monedă de pe Hyperliquid, doar în citire:

```bash
python3 .claude/skills/hl-analyst/hl.py scan                   # doar monedele din lista ta
python3 .claude/skills/hl-analyst/hl.py coins set BTC ETH SOL
python3 .claude/skills/hl-analyst/hl.py snapshot               # preț, funding, open interest
python3 .claude/skills/hl-analyst/hl.py ta --interval 4h       # EMA, RSI, MACD, ATR, pivoți
python3 .claude/skills/hl-analyst/hl.py funding --days 7
python3 .claude/skills/hl-analyst/hl.py book
python3 .claude/skills/hl-analyst/hl.py wallet 0xADRESA        # pozițiile publice ale unui portofel
python3 .claude/skills/hl-analyst/hl.py sim --side long --entry 81800 --stop 80800 --target 83800 --lev 10
```

## Instalare

Ca plugin, în Claude Code:

```
/plugin marketplace add gaflorin-afk/Hyperliquid.
/plugin install hyperliquid-skills@hyperliquid-skills
```

Ca plugin, comenzile apar cu prefix: `/hyperliquid-skills:crypto-scanner`.
Într-o sesiune Claude Code deschisă în acest depozit, comenzile `/crypto-*` apar
singure (skill-urile sunt în `.claude/skills/`). Pentru comenzi simple pe
calculatorul tău, în orice proiect, copiază folderele:

```bash
git clone https://github.com/gaflorin-afk/Hyperliquid..git hyperliquid
cp -r hyperliquid/.claude/skills/* ~/.claude/skills/
```

Ai nevoie de Python 3.8 sau mai nou. Într-o sesiune Claude în cloud, adaugă
`api.hyperliquid.xyz` la domeniile permise ale mediului.

## Atenție

- **Nu e sfat financiar.** E software care citește date publice și face
  calcule. Majoritatea celor care fac day trading pierd bani, iar cu crypto
  și levier pierd mai repede.
- **Time Machine e o simulare, nu o predicție.** Se bazează pe ultimele ~50
  de zile ale monedei. Știrile, hack-urile și cascadele de lichidări pot face
  lucruri pe care acele zile nu le-au făcut.
- **Un stop e un plan, nu o garanție.** Într-o piață rapidă se poate executa
  mult mai jos.
- **Prețul de lichidare e o estimare** pentru marjă izolată. Cifrele de pe
  ecranul de confirmare Hyperliquid sunt cele reale.
- **Taxe și funding** nu sunt incluse în calcule.
