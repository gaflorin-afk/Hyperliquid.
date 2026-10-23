---
name: crypto-daily
description: >-
  Agentul zilnic pentru crypto pe Hyperliquid. Rulează automat pașii 1-6 ai
  lanțului (scanner, intrare, ieșire, Time Machine, buget, risc) pe toate
  monedele din listă și prezintă scurt și la obiect primele 5 opțiuni de
  ordin ale zilei, ordonate după scor, doar cele care trec toate limitele.
  Nu plasează nimic. Use when the user says "top 5", "opțiunile de azi",
  "ce ordine pot pune azi", "rulează agentul", "raportul zilnic crypto",
  or when the daily scheduled task fires.
argument-hint: "[-n 5] [--stop or-mid] [--r 2]"
---

# crypto-daily

Agentul care face în locul utilizatorului pașii zilnici din `/crypto-trader`
și îi dă doar ce contează: primele 5 opțiuni de ordin. Motorul e
`../crypto-trader/crypto.py`; regulile lui complete sunt în
`../crypto-trader/SKILL.md`.

```bash
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" config          # limitele utilizatorului
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" top             # pașii 1-6 pe fiecare monedă, top 5
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" top --pick 2    # opțiunea 2 devine plan + ordin
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" risk
python3 "${CLAUDE_SKILL_DIR}/../crypto-trader/crypto.py" ticket
```

## Ce face `top`, pentru fiecare monedă din listă

1. **Scanner**: a ieșit azi din intervalul primei ore (00:00-01:00 UTC)?
2. **Intrare**: prima bară de 15 minute închisă dincolo de interval, long sau short.
3. **Ieșire**: stop după regulă (implicit mijlocul intervalului). Dacă de la
   breakout prețul a atins deja stopul sau ținta, moneda iese din listă.
   Altfel intrarea se recalculează la prețul de acum și ținta la 2R de el.
4. **Time Machine**: 5.000 de simulări ale restului zilei + aceeași regulă pe
   ultimele ~40-50 de zile reale.
5. **Buget**: mărimea după pierderea maximă, levier și marjă.
6. **Risc**: toate limitele (pierdere pe tranzacție și pe zi, număr de
   tranzacții, levier, lichidare înaintea stopului, $10 minim, fereastra).

Rămân doar opțiunile care trec tot. **Scorul** = media dintre R-ul mediu al
simulărilor și R-ul mediu al regulii pe zilele trecute, înainte de taxe.

## Cum prezinți rezultatul

Scurt, în română, fără umplutură. Întâi o linie de context, apoi câte o
linie-două pe opțiune, apoi un rând cu ce a ieșit și de ce:

```
Top 3 azi (vineri 23 oct., 09:53 UTC) · $100, 10x, max $5/tranzacție

1. SOL LONG · intrare ~104,16 · stop 103,76 · țintă 104,96
   7,2 SOL ($750, marjă $75) · pierdere la stop $2,88 · scor +0,04R
   Simulări: țintă 30% / stop 70%. Istoric 42 zile: 16 ținte / 25 stopuri.
2. ...

Au ieșit: ETH, DOGE, BNB, HYPE, SUI (stop deja atins), AVAX, LINK (ținta deja atinsă).
Pentru a folosi una: „alege 1” → bilet de ordin.
```

Reguli:

- Folosește doar cifrele tipărite de tool. Nu rotunji un scor în avantaj.
- Dacă sunt mai puțin de 5, spune câte și de ce. Nu completa lista.
- Scor negativ: spune clar „a pierdut în medie”. Dacă toate sunt negative sau
  „close to break-even”, spune că azi nu e un avantaj clar și că a nu
  tranzacționa e o opțiune validă.
- Spune prețul de lichidare când e la mai puțin de 10% distanță.
- Intrările marcate cu breakout mai vechi sunt intrări târzii, la prețul de
  acum: spune-o.
- O singură frază de final: simulare și regulă, nu predicție și nu sfat
  financiar; taxele nu sunt incluse.
- Când utilizatorul alege o opțiune: `top --pick N`, apoi `risk`, apoi
  `ticket`, și îi arăți biletul. Nu plasa nimic, nu cere chei.

## Când rulează singur

Sarcina programată pornește în fiecare dimineață o sesiune nouă cu acest
depozit. Limitele utilizatorului sunt în `crypto/config.json`, în depozit.
Rulează din rădăcina depozitului (`crypto/` e relativ la folderul curent).
Între 22:00 și 01:00 UTC nu există opțiuni noi: spune asta și atât.
