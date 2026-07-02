# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-26
**Wersja:** v3.4-stable
**Accuracy:** model offline **51.8%** (walk-forward A/B, DC W=0.5) | live: świeże ≥06-19 **47.8%** (23 settled, fixy Cel B) vs stare 31%
**Cel:** M1 = 55% win rate
**Suite:** ~1375 testów pass / 6 skip (coverage 57.66%, floor 57)
**LIVE (06-26):** reweight `ENSEMBLE_MARKET_WEIGHT=0.70` (rev 00274) + quick_picks Poisson fix (default ON) + cloud-draft scheduler `footstats-draft-morning` 07:30 CEST
**ZBUDOWANE flag-OFF (flip po walidacji):** `SELECTION_MIN_CONF` (lever #1) + `LEAGUE_GATING` (lever #2)

---

## 🔴 ODKRYCIE + FIX (06-26) — live nie używał naszego modelu (NAPRAWIONE, default ON)

> Bug: `quick_picks` ładował `load_cached()` (schemat **angielski** home/away/hg/ag), ale walidował
> **polski** (gospodarz/goscie/...) → `df_mecze=None` → **Poisson CICHO pomijany → Bzzoiro-ML.**
> Czyli live (47.8%) = Bzzoiro-ML, NIE nasz Poisson-DC (51.8% offline) — prawdopodobnie duży element luki Cel B.

- [x] **FIX wdrożony (default ON)** — adapter schematu w quick_picks (`adapt_to_prod_schema`).
  Escape-hatch `QUICK_PICKS_USE_POISSON_CACHE=0`. **De-risk 06-26:** na meczach reprezentacji (WC, teraz)
  typy IDENTYCZNE (Poisson nie ma historii kadr — dataset to ligi klubowe) → zero zmiany teraz; realna
  poprawa **gdy wrócą ligi klubowe (sierpień)** → Poisson 51.8% zamiast Bzzoiro-ML. Suite 1340 pass.
- [ ] **MONITORUJ na restart lig klubowych** (sierpień): czy live z Poissonem ruszy ku 51.8%
  (`calibration_monitor.py`). Gdyby Poisson okazał się gorszy od Bzzoiro-ML → `=0` (escape-hatch).
- [ ] **Walidacja — uwaga:** dotychczasowe settled to Bzzoiro-ML (nie nasz model). Świeże po fixie
  (klubowe) = Poisson. Stare dane Bzzoiro-ML nie walidują naszego modelu.

---

## ✅ Cloud-draft WŁĄCZONY LIVE (06-26) — System paper-trading PC-niezależny

> `/cron/draft` + `core/cloud_draft.py` (lite draft, requests-only: Bzzoiro→quick_picks, bez
> Playwright/Groq/Telegram). **WDROŻONE LIVE** — Cloud Scheduler `footstats-draft-morning`
> (07:30 CEST, `dry_run=false`) przed settle 08:00. Auth via `X-Cron-Secret` (Cloud Run env, nie Secret Manager).
> `/api/cron/draft` w `_LONG_RUNNING_PATHS` (120s). Odblokowany bottleneck — draft był tylko lokalny (PC on).

- [x] **Endpoint + scheduler LIVE** — pierwszy live run created:0 = **BENIGN (idempotencja)**: 12 kandydatów
  WC już miało kupony System (dedup per mecz/data). System user istnieje (leaderboard total:15).
- [x] **Data-freshness guard (06-26)** — `/cron/draft` zwraca `{stale_days, stale}` + `log.warning` gdy
  ≥3 dni bez kuponu System → rozróżnia BENIGN-0 od STARVATION-0 (`core/draft_health.py`). Alert w Cloud Logging.
- [ ] **`model_source=bzzoiro-ml` na cloud** (parquet nieobecny) → cloud-draft NIE używa Poisson-DC.
  Aby włączyć Poisson na cloud: dostarcz `full_dataset.parquet` (562KB) — (a) GCS-pull przy starcie
  [najlepsze, wymaga kodu startup+bucket] lub (b) COPY do obrazu (force-add binary do git).
  **DECYZJA 06-26: ODŁOŻONE DO SIERPNIA** — off-season WC=kadry → Poisson i tak nie ruszy (dataset
  klubowy), bzzoiro-ml OK teraz; realny zysk dopiero na restart lig klubowych. Wrócić wtedy.
- [ ] **Monitoruj** `calibration_monitor.py` — dane walidacyjne rosną PC-niezależnie → odblokuje M1 flipy.

### 🌙 JUTRO (07-03) — przenieść PEŁNY pipeline na cloud (całkowite PC-off)
> **Powód:** user nie chce, by PC chodził nocą. Stan: System paper-draft JUŻ cloud
> (`footstats-draft-morning` 07:30 CEST) + settlement cloud (06:00/21:30 UTC). LOKALNIE zostaje
> (Task Scheduler, wymaga PC on): `daily_agent --faza final` 11:00 (kupony Groq A-D + Telegram) +
> `evening_agent` 23:00 (**nocny — główny powód migracji**). **Decyzja: cloud, nie Raspberry Pi** —
> infra już stoi (Cloud Run + Neon + /cron/draft działa); Pi = port ARM (torch/playwright) + dubel + dom-net.
- [ ] Migracja pełnego pipeline → **Cloud Run Jobs** (nie request-timeout-bound; Playwright+Groq OK).
  Etapy: (1) obraz z Playwright/chromium, (2) Job `final` 11:00 CEST + Job `evening` 23:00 CEST przez Cloud Scheduler,
  (3) sekrety Groq/Telegram w Cloud Run env, (4) potwierdź parytet z lokalnym runem, (5) wyłącz lokalne
  taski (`FootStats-DailyAgentFinal`, `FootStats-EveningAgent`, `FootStats-DailyAgentDraft`). Koszt ~$0-5/mc.

---

> **Ukończone → `CHANGELOG.md` + `git log`.** Skrót ostatnich (06-24/25): hardening OWASP (live) +
> CI lint/security/coverage gate + Dependabot fix + dekompozycja superbet/daily_agent/utils-logging +
> TheSportsDB 4. źródło + consensus→settlement + CRON_SECRET rotacja + ALLOWED_ORIGINS cleanup +
> Cloud Scheduler audyt + Daily DB Backup (Neon pg_dump) + walk-forward A/B (DC 51.8% potwierdzone) +
> ImportanceIndex/LightGBM zbadane→ślepa uliczka + reweight ku rynkowi (flip live) + quick_picks Poisson fix +
> cloud-draft live + M1 lewary #1/#2 zbudowane (flag-OFF) + schedule-adj zbadane (marginal) + coverage 57.
> Wcześniej: Cel A/B/C, D1-D7, multi-source framework, RODO, multi-user.
> Suite: **~1375 testów pass / 6 skip** (coverage 57.66%).

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M1** | 55% win rate | 🔴 W toku | świeże settled (~88) → selekcja 65%+ conf (offline=68%) + gating lig |
| **M2** | 60% win rate | ⏸️ | Po M1 — tuning |
| **M3** | 65% selected | ⏸️ | Po M2 |
| **BETA** | Testerzy | ⏸️ | Po M1 |

---

## 🚀 NAJWAŻNIEJSZE — reweight ensemble ku rynkowi (FLIP WDROŻONY LIVE 06-26)

> **Model R&D zakończone 06-25** (4 eksperymenty, 1 win — szczegóły → CHANGELOG):
> ImportanceIndex −0.1pp ❌ · W_BAYESIAN 0.5 już optimum ❌ · LightGBM 51.6% < rynek 53.1% ❌ ·
> **reweight ku rynkowi +1.4pp ✅**. Wniosek: model przy praktycznym suficie, **rynek (kursy) ~53% nieprzekraczalny**.
> Skuteczność ≠ accuracy; realna gra = **value** (model vs rynek) + **selekcja high-conf** + dane.

- [x] **FLIP WDROŻONY: `ENSEMBLE_MARKET_WEIGHT=0.70`** (=30/70 model/rynek) — Cloud Run **rev 00274 LIVE**.
  WF A/B: 70/30→51.8% vs 30/70→52.8% (z kursami 52.5→53.8). Zostawia 30% głosu modelu na value.
  Escape-hatch: usuń env / ustaw inną wartość. **Monitoruj** calibration check (log-loss) na świeżych settled.
- [ ] (opcj.) re-optymalizacja per-league wag ku rynkowi (`ensemble_optimizer`).

---

## 🔴 PRIORYTET — WALIDACJA (pasywne — NIE dokładaj zmian λ)

> Root-cause'y Cel B usunięte. Kalibracja OFF (`CALIBRATION_ENABLED`), auto-refit czeka na dane (D2).
> STOP na nowe λ aż zbierzemy świeże dane (zmiana teraz zaciemnia czy fixy działają).

- [ ] **D3 — PEŁNA decyzja a/b/c** (próg guardu, czy argmax na stałe) — po ~20 ŚWIEŻYCH settled z zapisanym prob.
  Zwaliduj że guard pomaga, dostrój próg. (D3 część 1+2 prob+guard ZROBIONE 06-22 → CHANGELOG.)
- [ ] **DECYZJA (nie bug):** Bzzoiro etykietuje towarzyskie kadr jako "World Cup 2026" → whitelist MŚ (D1a).
  Niska szkoda + downstream łapią. Opcje: (a) zostaw MŚ [domyślnie], (b) wyklucz kadry z kuponów Groq,
  (c) zawęź whitelist do realnych fixture'ów WC.
- [ ] Co kilka dni: `python scripts/calibration_monitor.py` (Neon, read-only) — System vs Pipeline,
  czy accuracy ruszyła, licznik settled (D2 auto-refit przy delcie +30 od n_train).
  **NOWE (06-26):** monitor ma per-liga + **flip-advisor** (`core/flip_advisor.py`) — sam rekomenduje
  czy flipnąć `SELECTION_MIN_CONF` (high-conf bije ogół?) i które ligi do `LEAGUE_GATING` (<50%, n≥8).
- [ ] Po ~88 settled → D2 auto-refit sam; gdy krzywa zdrowa → włącz `CALIBRATION_ENABLED=1`.
- **Zbieranie:** draft lokalny (Task Scheduler 08:00) + settle cloud (06:00/21:30 UTC) + lokalny 23:00.
  ⚠️ **Draft TYLKO lokalny** — PC off = 0 nowych predykcji/dzień (bottleneck danych do walidacji).

---

## 🎯 JAKOŚĆ λ — kandydaci PO walidacji (nie wcześniej)

> **Walk-forward A/B (06-25, out-of-sample, n=7934, kalibracja OFF):** poisson_only 48.8 < baseline 50.3
> < **dixoncoles (DC W=0.5) 51.8**. Sweep W_BAYESIAN: **0.5 optimum** (nie ruszać). Opponent-adjusted λ
> (atak×obrona) + DC τ + bayesian ramię **JUŻ w prod** (`USE_DIXON_COLES=1`). **Kalibracja: 65%+ conf = 68%**
> (robustnie). Per-liga: NED 56/SCO 55/ITA 54/ENG 54 ≥M1; POL 44/ESP 49/FRA 49 w dół.
> **WNIOSEK M1:** model OK, droga = **SELEKCJA** (65%+ subset) + gating lig. Zgodne z Cel B (gap=selekcja).

- [x] **Selekcja na confidence (M1 lever #1) — ZBUDOWANE** (flaga `SELECTION_MIN_CONF`, default OFF=40).
  Podnosi próg `najlepszy_typ` do pasma high-conf (offline 65%+=68%). Wpływa na System paper + cloud-draft.
  **Flip po walidacji** (~88 fresh): ustaw `SELECTION_MIN_CONF=65`, zwaliduj że live trzyma kalibrację.
- [x] **Gating słabych lig (M1 lever #2) — ZBUDOWANE** (flaga `LEAGUE_GATING`, default OFF). `LIGI_SLABE`
  (POL/ESP/FRA <50% offline) odrzucane w `_pre_filtruj_ligi` gdy ON; faworyzuje NED/SCO/ITA/ENG.
  **Flip po walidacji**: `LEAGUE_GATING=1`.
- [ ] **Kontuzje v2** — waga udziałem w golach (utrata strzelca > rezerwowy); wymaga scrape per-gracz.

### Zbadane → odrzucone (nie wracać)
- **ImportanceIndex** (crude ±20% multiplier): backtest A/B −0.1pp, high-stakes −0.59pp → ślepa uliczka
  (CHANGELOG 06-25). `core/standings.py` zostaje jako CECHY do modelu ML.
- **LightGBM / własny model ML** (pomysł B): 51.6% (z kursami) / 50.9% (bez) < rynek 53.1% < baseline.
  Rynek nieprzekraczalny (jak literatura). `core/ml_features.py` zostaje jako infra (pi-ratings/elo).
  Jedyny realny owoc = reweight ensemble ku rynkowi (sekcja NAJWAŻNIEJSZE).
- **Schedule-adjusted ratings (M1 lever #5)** (06-26): opponent-adjusted ratingi w `_oblicz_sile_wazona`
  (flaga `SCHEDULE_ADJUSTED_RATINGS`). Offline A/B (DC, n=2976): baseline 50.97% vs adj 51.18% =
  **+0.20pp (szum, se~0.92pp)**, poniżej hipotezy +0.5-1pp, +57% wolniej. **Flag zostaje OFF.**
  Kod + 7 testów zostają jako infra; flip tylko gdyby pełne n potwierdziło (mało prawdopodobne).

---

## 💰 MONETYZACJA / LAUNCH (wymaga Ciebie)

- [ ] **D8 — prawnik (ToS bukmacherów) + JDG (CEIDG)** — WSTRZYMANE (koszt/ryzyko). Wrócić po walidacji.
- [ ] Resend FROM: `onboarding@resend.dev` (test) → zweryfikowana domena przed prod. (Resend wpięty ✅ → CHANGELOG.)
- [ ] Reset hasła — flow tokenów (`send_password_reset_email` jest) + endpoint.
- [ ] Płatności (Lemon Squeezy/Paddle, po JDG): cennik+auto-renewal, webhooks, email potwierdzenie/faktura, upgrade/proration.
- [ ] Faktura (po płatnościach). Custom domain (opcjonalne).

---

## 🌐 SCRAPERY — kolejne źródła (opcjonalne)

- [ ] **Ocena per-stabilność/anti-bot:** Soccer24 (klon FlashScore — redundancja, skip),
  Meczyki/LiveScore (anti-bot, scraping), Transfermarkt (raczej squad/value niż wyniki).
  (4 źródła wpięte: AF/football-data.co.uk/FlashScore/TheSportsDB ✅ → CHANGELOG.)

---

## 📋 Następne kroki

1. **Pasywne (PRIORYTET):** zbieraj świeże settled — draft leci **PC-niezależnie** (cloud-draft scheduler 07:30 CEST
   + lokalny). Co kilka dni `calibration_monitor.py`: czy reweight 30/70 + Poisson ruszyły accuracy. Budżet AF 100/dzień.
2. **Sierpień (restart lig klubowych):** zweryfikuj że quick_picks-fix → Poisson live (51.8%) zamiast Bzzoiro-ML.
3. **Po walidacji (~88 settled):** D2 auto-refit sam → `CALIBRATION_ENABLED=1`; D3 decyzja; selekcja 65%+ + gating lig.
4. **Opcjonalne:** parquet na cloud (→ cloud-draft używa Poisson zamiast bzzoiro-ml).
5. **Sam koniec (D8):** JDG/prawnik (wstrzymane). Email/płatności po walidacji.
