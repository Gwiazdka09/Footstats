# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-25
**Wersja:** v3.4-stable
**Accuracy:** model offline 51.3% 10 lig (DC, NED 54.9%, kalibracja monotoniczna) | live: świeże ≥06-19 **47.8%** (23 settled, fixy Cel B działają) vs stare 31% (sprzed fixów, kontaminują monitor)
**Cel:** M1 = 55% win rate

> Ukończone: `git log` + `CHANGELOG.md`. Fazy DONE: 16-20, GUI/UX, SEO, RODO, multi-user (15.6),
> audyt core (A1-A3), λ: kontuzje + xG+obrona, Cel A (walk-forward), Cel B bug 1,
> Cel C (Dixon-Coles w prod), audyt settlement + audyt głęboki (06-18), dług techniczny #1-#5,
> decyzje D1a/D1b/D2/D4/D5/D6/D7, TECHNICZNE/SECURITY (stealth, cli/analyzer decompose, daily_io),
> trainer crash fix + D3 część 1+2 (prob/guard) + Telegram escape/cli import + flaky test +
> email Resend + rynek GG2H+HT (06-22) + scrapery multi-source framework + 3 źródła
> (AF/football-data.co.uk/FlashScore) z cross-walidacją live + FlashScore live-leak fix +
> brain graph szczegółowy (06-23) + consensus→settlement + CI lint/security gate +
> hardening OWASP (live) + dekompozycja superbet + Dependabot CI fix (gitleaks skip) +
> coverage gate (55%) + dekompozycja daily_agent (output+decision) + TheSportsDB 4. źródło +
> dekompozycja utils/logging (exceptions+safe_http) + CRON_SECRET rotacja + ALLOWED_ORIGINS cleanup
> + Cloud Scheduler zweryfikowany (06-24/25 → `CHANGELOG.md`).
> Suite: **1300 testów pass / 6 skip** (coverage 56.3%).

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M1** | 55% win rate | 🔴 W toku | świeże settled (~88) → selekcja 65%+ conf (offline=68%) + gating lig |
| **M2** | 60% win rate | ⏸️ | Po M1 — tuning |
| **M3** | 65% selected | ⏸️ | Po M2 |
| **BETA** | Testerzy | ⏸️ | Po M1 |

---

## 🔴 PRIORYTET — WALIDACJA (czekaj i mierz, pasywne — NIE dokładaj zmian λ)

> Root-cause'y Cel B (bug 1 conf, kalibracja per-wynik) usunięte. Kalibracja OFF (gate
> `CALIBRATION_ENABLED`), auto-refit czeka na dane (D2). Kursy odblokowane (AF `/odds` fallback).
> STOP na nowe λ aż zbierzemy świeże dane.

- [x] **D3 część 1+2 — Cel B bug 2 (Groq selekcja)** (06-22, `4823ac9c0`):
  - Prerekwizyt: prob modelu (pw/pr/pp) zapisywane w `predictions` (migracja 8) — wcześniej brak
    → retrospektywna analiza Groq-tip vs argmax niemożliwa. Teraz rośnie z każdym runem.
  - Guard konserwatywny `koryguj_tip_wg_modelu`: Groq tip 1X2 z prob modelu <15% → override
    na argmax. Wpięty w zapis predykcji. Tylko skrajne przypadki.
- [ ] **D3 — PEŁNA decyzja a/b/c** (próg guardu, czy argmax na stałe) — po ~20 ŚWIEŻYCH settled
    z zapisanym prob (analyst, gdy 529 minie). Zwaliduj że guard pomaga, dostrój próg.
  - [ ] **DECYZJA (nie bug):** Bzzoiro etykietuje towarzyskie kadr jako "World Cup 2026" → przechodzą
    przez whitelist MŚ (D1a, dodane świadomie dla danych). Norway-Senegal/Jordan-Algeria 06-22:
    conf 22/42 (low), brak kursów AF → System NIE obstawi; predykcje nie settlują (jak #175,
    brak coverage). Niska szkoda + downstream łapią (guard D3, stale-VOID). Opcje gdy zechcesz:
    (a) zostaw MŚ (więcej danych, trochę szumu), (b) wyklucz kadry z budowy kuponów Groq,
    (c) zawęź whitelist do realnych fixture'ów WC (wymaga źródła fixture). Domyślnie: zostaw (a).
- [ ] Co kilka dni: `python scripts/calibration_monitor.py` (Neon, read-only)
  - System (bez Groq) vs Pipeline (Groq) — werdykt bottlenecku LLM (potrzeba ≥15 System settled)
  - czy accuracy ruszyła z 31.7%
  - monitoruj licznik settled (D2 auto-refit odpala się sam przy delcie +30 od n_train, patrz `CHANGELOG.md`)
- [ ] Po ~88 settled → D2 auto-refit odpali sam; gdy krzywa zdrowa → włącz `CALIBRATION_ENABLED=1`.
- **Zbieranie:** System paper-trading autonomiczne (Task Scheduler 08:00, draft-only po D5) + settle 23:00.
- **Stare 41 settled** są sprzed fixów → wciąż odwrócone, to oczekiwane.

---

## 🎯 JAKOŚĆ λ — kandydaci PO walidacji (nie wcześniej)

> **Walk-forward A/B (06-25, out-of-sample, n=7934, kalibracja OFF):**
> poisson_only **48.8%** < baseline (ensemble+devig) **50.3%** < **dixoncoles (DC, W=0.5) 51.8%**.
> Sweep `W_BAYESIAN`: 0.3→51.4, **0.5→51.8 (optimum)**, 0.7→51.7, 1.0→50.4 → **0.5 już optymalne, nie ruszać**.
> Opponent-adjusted λ (atak×obrona) + DC τ + DC bayesian ramię **JUŻ w prod** (`USE_DIXON_COLES=1`).
> **Kluczowe: kalibracja per pasmo** — 65-101% conf = **68% trafność** (robustnie, ~27% meczów),
> 55-65% = 54.6%. Per-liga: NED 56 / SCO 55 / ITA 54 / ENG 54 ≥M1; POL 44 / ESP 49 / FRA 49 ciągną w dół.
>
> **WNIOSEK dla M1 (55% win rate na postawionych):** model NIE wymaga przepisania (51.8% raw, DC on,
> W optymalne). Droga do M1 = **SELEKCJA**: model już produkuje 68%-trafny subset (65%+ conf).
> Lewary (deploy PO walidacji): (1) **ciaśniejszy próg confidence** na budowę kuponu (65%+ → ~68%),
> (2) **gating słabych lig** (POL/ESP/FRA out, faworyzuj NED/ITA/ENG/SCO). Zgodne z Cel B (gap=selekcja).

- [x] **Dixon-Coles opponent-adjusted** — JUŻ w prod (atak×obrona w λ bazowej + DC τ rho=-0.05 +
  bayesian ramię `blend_dixon_coles`, `W_BAYESIAN=0.5` potwierdzone optymalne walk-forwardem 06-25).
- [ ] **Selekcja na confidence (M1 lever #1)** — podnieś próg budowy kuponu do pasma 65%+ (=68% offline).
  Deploy PO walidacji (~88 fresh), zwaliduj na świeżych że live trzyma kalibrację.
- [ ] **Gating słabych lig (M1 lever #2)** — POL/ESP/FRA <50% offline; faworyzuj NED/ITA/ENG/SCO/AUT.
- [ ] **Schedule-adjusted ratings** — `_oblicz_sile_wazona` liczy atak=gole/średnia bez korekty siły
  rywala (gole vs słabe obrony zawyżają). Iteracyjne ratingi mogłyby dodać ~0.5-1pp do raw. Drugorzędne vs selekcja.
- [ ] **Kontuzje v2** — waga udziałem w golach (utrata strzelca > rezerwowy); wymaga scrape per-gracz.
- [x] **ImportanceIndex — ZBADANE 06-25, ŚLEPA ULICZKA.** `core/standings.py` (rekonstrukcja tabeli
  z wyników, no-lookahead, +13 testów) → backtest A/B na 14205 meczach z aktywnym importance:
  OFF 47.3% vs ON 47.2% (**-0.1pp**); na high-stakes (tytuł/spadek, n=4100) jeszcze gorzej:
  OFF 51.2 vs ON 50.6 (**-0.59pp**). Crude multiplier ±20% pogarsza (high-stakes = więcej niespodzianek).
  **Nie wpinać.** Standings infra zostaje — pozycja/punkty = dobre CECHY do modelu ML (poniżej).
- [ ] **Własny model ML (LightGBM/XGBoost) — pomysł B (research w toku).** 32400 meczów × 28 cech
  (strzały/xG/rożne/kartki/kursy — większość nieużywana przez Poisson). Cel: nowe ramię ensemble.
  Realistycznie +1-3pp (rynek efektywny). Wymaga `pip install`. Walk-forward + kalibracja + zero leakage.

---

## 🟡 TECHNICZNE / SECURITY

- [x] **Sofascore stealth** (06-21, `a5af86ecf` + security fix `d085b5815`) — no-dep:
  ukrycie `navigator.webdriver`/AutomationControlled. NIE gwarantuje obejścia 403 (AF /odds
  pozostaje podstawą kursów). Sandbox Chromium przywrócony (review MEDIUM).
- [x] **God-moduły rozbite** (06-21): `cli.py` 1112→773 (`210d9ec46`, → `cli_commands.py`),
  `analyzer.py` 930→793 (`6fa110177`, czyste helpery → `analyzer_helpers.py`). Behavior-preserving.
- [x] **daily_io — testy** (06-21, `3be80d1b9`) — +10 testów (`_zapisz_kupon_do_db`, mock prod).
- [x] **`_bzz_parse_prob` NameError** (06-22, `6ad1dfd9a`) — `cli_commands._analiza_kuponu` wołał
  bez importu → dodano `from footstats.scrapers.bzzoiro import _bzz_parse_prob`.
- [x] **Trainer crash na float korekcie** (06-22, `c99d41fe9`) — `get_kalibracja_inject` `:+d`
  (int-only) na float `korekta_pewnosci` → cały Groq (KROK 3) crashował, 0 predykcji zapisanych.
  Fix `:+.0f`. +3 testy.
- [x] **Telegram HTML escape** (06-22, `6ad1dfd9a`) — nazwy drużyn z `</&` łamały `parse_mode=HTML`
  → HTTP 400 cicha porażka. `html.escape` w send_draft_kupon/send_kupon/_format_zdarzenia.
- [x] **Flaky test deterministyczny** (06-22, `fa61cd63b`) — `test_zapisz_kupon_final_promotes`
  order-zależny, zmockowany `resolve_admin_user_id→1`.

---

## 💰 MONETYZACJA / LAUNCH (wymaga Ciebie)

### Prawne
- [ ] **D8 — Konsultacja z prawnikiem (ToS bukmacherów) + JDG (CEIDG)** — WSTRZYMANE (sam koniec).
  User waha się: konsekwencje JDG jak się nie uda; prawnik za drogi. Bez akcji. Wrócić po
  walidacji modelu.

### Email transakcyjny
- [x] **Resend wpięty** (06-22, `8dcb76a27`+`a7f815381`) — `utils/mailer.py` (HTTP, no-dep), klucz w .env
  (`resend_api_key`). Welcome po /auth/register (live OK, email dostarczony). `send_password_reset_email`
  gotowe. **LIMIT Free: 100/dzień, 3000/mc, 1 domena** — welcome=1/rejestrację, bezpieczne.
- [ ] FROM: teraz `onboarding@resend.dev` (test-sender) → podmień na zweryfikowaną domenę przed prod.
- [ ] Reset hasła — wpiąć flow tokenów (`send_password_reset_email` już jest) + endpoint.
- [ ] Faktura (po płatnościach).

### Płatności (Lemon Squeezy / Paddle — zdecydowane, po JDG)
- [ ] Cennik przed checkout + warunki auto-renewal
- [ ] Webhooks: subscription.updated/cancelled/payment_failed
- [ ] Email: potwierdzenie, faktura, retry, ostrzeżenie przed odnowieniem
- [ ] Upgrade/downgrade + proration

### Hosting
- [ ] Custom domain (opcjonalne)

---

## 🌐 SCRAPERY — multi-source + cross-walidacja

- [x] **Architektura** `scrapers/sources/`** (06-23, `5c0a9adc2`): adapter `MatchData` (typ
  ujednolicony: wynik/HT/kursy/timestamp/source) + `ResultsSource` protocol (interfejs każdego
  scrapera) + `aggregator` (porównanie wielu źródeł → konsensus / flag rozjazdu).
- [x] **3 źródła wpięte + cross-walidacja live OK** (06-23): API-Football (`5c0a9adc2`),
  football-data.co.uk CSV (`6ad9899d4`), FlashScore mobi (`0383a11ff`); rejestr aggregatora
  (`d35a074b4`, `a0c22d2c6`). Live: AF 79 + FlashScore 98 meczów, **27 potwierdzonych przez
  ≥2 źródła, 0 rozjazdów**.
- [x] **4. źródło: TheSportsDB** (06-25, `3b16a64f5`) — darmowe JSON API (bez anti-bot), FT.
  Pokrycie reprezentacji/towarzyskich/turniejów które ligowe źródła gubią (settlement orphan
  predykcji MŚ/friendly, D1a). Graceful + cache 6h + 14 testów. Free test-key, env `THESPORTSDB_KEY`.
- [ ] **Kolejne źródła (ocena per-stabilność/anti-bot):** Soccer24 (klon FlashScore — redundancja,
  skip), Meczyki/LiveScore (anti-bot, scraping), Transfermarkt (raczej squad/value niż wyniki).
- [x] **Wpięcie `aggregator.consensus_result` do settlementu** (06-24, `349fd919a`) —
  Źródło 5 w `_find_leg_result`, additive fallback po źródłach 1-4. +3 testy.

---

## 🏗 AUDYT ARCHITEKTURY / STANDARDY (06-23)

> Audyt CI/CD + jakość kodu. Werdykt: spełnia większość wymagań produkcyjnych (CI/CD, **1254
> testy**, JWT/RODO/Sentry/Docker/Neon/migracje). Gapy do poziomu "enterprise" poniżej.

- [x] **CI lint/type/security gate** (06-24/25) — `ci.yml` 5 jobów: lint (`ruff` E9+F + `mypy`
  sources, `e7ea3ea50`), security (`bandit`+`pip-audit`, `6afa46f6a`), secrets (`gitleaks`,
  `9a09e6beb`), test, docker. Config w `pyproject.toml` + `.pre-commit-config.yaml` + Dependabot.
  CI+CD green na main.
- [x] **Próg coverage** (06-25, `4a85f91ab`) — `ci.yml` job `test` liczy `--cov` i wymusza
  `--cov-fail-under=55` (floor anty-regresyjny; zmierzone ~57%). Ratchet w górę do 80% z czasem.
- [x] **`superbet.py` rozbity** (06-25, `3ad91a844`) — 1128→867, parsery → `superbet_parsing.py`, +22 testy.
- [x] **`daily_agent.py` rozbity** (06-25, `c48ab449f`) — 1078→818, `daily_agent_output.py` (prezentacja
  rich) + `daily_agent_decision.py` (decision score), behavior-preserving + re-export.
- [x] **`utils/logging.py` rozbity** (06-25, `9bad59ac4`) — 723→539, `exceptions.py` (Blad*) +
  `safe_http.py` (BezpiecznyHTTP/BezpiecznePobieranie), re-export (identity klas zachowana).
- [x] **PROD security drobne** (06-25): `ALLOWED_ORIGINS` wyczyszczony (secret v3, rev 00263 — usunięto
  `localhost:5173/3000`, został Vercel+run.app); CRON_SECRET **rotowany** (rev 00262 + headery scheduler).
  Cloud Scheduler AKTYWNY (`footstats-settle-morning/evening` → `/api/cron/settle`, NIE opcjonalny).

---

## 📋 Następne kroki

> Dług techniczny #1-#5 i decyzje D1a/D1b/D2/D4/D5/D6/D7 ZROBIONE (06-20/21, → `CHANGELOG.md`).
> D3 część 1+2 (prob+guard) ZROBIONE 06-22, pełna decyzja a/b/c czeka na dane. D8 wstrzymane.
> Suite **1209 pass / 4 skip**. Kursy odblokowane (AF `/odds`).
> Drobne ✅: Telegram "blad wysylki" = HTML parse 400 (nazwy z </&) → naprawione html.escape (`6ad1dfd9a`).

1. **✅ ZWERYFIKOWANE LIVE (06-21):** System tworzy kupony — **13 ACTIVE** dziś (było 0) + 7 nowych
   predykcji. 🔴 ROOT przyczyny "0 kuponów": **agent auto-zapauzowany od 06-16** (stop-loss
   tygodniowy 20%, drawdown z zepsutego pipeline'u Cel B) → `daily_agent` exit 0 CICHO, zero
   pracy 5 dni. Naprawione: stop-loss auto-pauza WYŁĄCZONA dla fazy paper (`WEEKLY_DRAWDOWN_PCT`
   wysokie w .env) — bankroll to symboliczna liczba, nie realne pieniądze, więc auto-pauza =
   zbędna friction. (Przy ew. real-money: obniż próg w .env.)
2. **✅ OBSERWOWALNOŚĆ NAPRAWIONA (06-21):** taski Scheduler logują do `data/logs/sched_*.log`
   (pełny stdout/stderr) + `daily_agent` alarmuje (Telegram + log) gdy run kończy się 0
   kuponów/kandydatów. Koniec cichych awarii.
3. **Pasywne:** zbieraj świeże settled (wolne tempo OK). Pilnuj budżetu AF (100/dzień; dziś 14).
4. **Po walidacji (~88 settled):** D2 auto-refit odpali sam; gdy krzywa zdrowa →
   włącz `CALIBRATION_ENABLED=1`; D3 decyzja Cel B bug 2 (Groq selekcja).
5. **Opcjonalnie:** Sofascore 403 stealth (tylko jeśli AF coverage za cienki na egzotyki).
6. **Sam koniec (D8):** JDG/prawnik — wstrzymane (koszt/ryzyko). Email/płatności po walidacji.
