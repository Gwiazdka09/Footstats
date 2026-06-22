# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-22
**Wersja:** v3.4-stable
**Accuracy:** model offline 51.3% 10 lig (DC, NED 54.9%, kalibracja monotoniczna) | live 31.7% (stare, sprzed fixów Cel B — czeka na świeże)
**Cel:** M1 = 55% win rate

> Ukończone: `git log` + `CHANGELOG.md`. Fazy DONE: 16-20, GUI/UX, SEO, RODO, multi-user (15.6),
> audyt core (A1-A3), λ: kontuzje + xG+obrona, Cel A (walk-forward), Cel B bug 1,
> Cel C (Dixon-Coles w prod), audyt settlement + audyt głęboki (06-18), dług techniczny #1-#5,
> decyzje D1a/D1b/D2/D4/D5/D6/D7, TECHNICZNE/SECURITY (stealth, cli/analyzer decompose, daily_io),
> trainer crash fix + D3 część 1+2 (prob/guard) + Telegram escape/cli import + flaky test +
> email Resend + rynek GG2H+HT (06-22 → `CHANGELOG.md`). Suite: **1209 testów pass / 4 skip**
> (2 fail + 2 error niezwiązane z sesją — checkpoint order, file_integrity length — do zbadania).

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M1** | 55% win rate | 🔴 W toku | świeże settled + walidacja A/B |
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

- [ ] **Dixon-Coles opponent-adjusted** — λ skorygowane o siłę rywala (z istniejącej historii,
  bez nowych danych). Najwyższy następny lewar.
- [ ] **Kontuzje v2** — waga udziałem w golach (utrata strzelca > rezerwowy); wymaga scrape per-gracz.
- [ ] **ImportanceIndex** (motywacja spadek/tytuł) — `football_data.tabela(kod)` daje kolumny,
  ale brak: mapy nazwa-ligi Bzzoiro→kod football-data.org + cache standings. **Tylko końcówka
  sezonu** ma wartość → odłożone do startu lig (teraz off-season = NORMAL).

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

## 🌐 SCRAPERY — multi-source + cross-walidacja (start 06-22)

> **Cel:** wiele źródeł danych (wyniki/HT/kursy) + warstwa porównująca → (1) redundancja gdy
> API-Football nie pokrywa meczu, (2) cross-walidacja — rozjazdy między źródłami = sygnał błędu
> danych albo wartości bukmacherskiej. Framework w budowie, osobny commit (jeszcze NIE w git).

- [ ] **Architektura** `scrapers/sources/`: wspólny adapter `MatchData` (typ ujednolicony:
  wynik/HT/kursy/timestamp/source) + `ResultsSource` protocol (interfejs każdego scrapera) +
  `aggregator` (porównanie wielu źródeł → konsensus / flag rozjazdu).
- [ ] **Źródła do dodania (darmowe, do oceny per-stabilność/anti-bot):** Flashscore, Soccer24,
  Sofascore (już 403 — wymaga stealth, patrz TECHNICZNE), Meczyki, LiveScore, sport.tvp.pl,
  polsatsport, Eurosport, Interia, Transfermarkt.
- [ ] Status: framework w budowie — brak commitu jeszcze, czeka na pierwszy adapter + testy.

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
