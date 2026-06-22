# Changelog

> Archiwum ukończonych prac (przeniesione z TODO.md przez `footstats-scribe`).
> Aktywne zadania: `TODO.md`. Pełna historia commitów: `git log`.

## 2026-06-22

### Bugi / fixy
- **Trainer crash na float korekcie** (`c99d41fe9`): `get_kalibracja_inject` formatował korektę
  z `f"{kor:+d}"` (int-only) → `ValueError` gdy `korekta_pewnosci` float → KROK 3 (Groq) crashował
  całkowicie, 0 predykcji zapisanych (baza kalibracji zagłodzona). Fix: `:+.0f` (float i int). +3
  testy. Złapane przez obserwowalność (sched log) z 06-21 — wcześniej niewidoczne.
- **Telegram HTML escape + cli NameError** (`6ad1dfd9a`): (1) nazwy drużyn z `</&` łamały
  `parse_mode=HTML` → HTTP 400 "can't parse entities", cicha porażka wysyłki — naprawione
  `html.escape` w `send_draft_kupon`/`send_kupon`/`_format_zdarzenia` + logowanie realnej
  przyczyny. (2) `cli_commands._analiza_kuponu` wołał `_bzz_parse_prob` bez importu → `NameError`
  przy trafieniu w ev_ml — dodany import z `bzzoiro`. +test regresji.
- **Flaky test deterministyczny** (`fa61cd63b`): `test_zapisz_kupon_final_promotes` był
  order-zależny (`resolve_admin_user_id()` ≠ user_id=1 draftu w izolacji) — zmockowany
  `resolve_admin_user_id→1`.

### D3 — Cel B bug 2 (Groq selekcja), część 1+2
- **`4823ac9c0`**: prob modelu (pw/pr/pp) zapisywane w `predictions` (kolumny prob_home/draw/away,
  migracja 8, DDL + `save_prediction`) — prerekwizyt: wcześniej brak prob modelu → retrospektywna
  analiza Groq-tip vs argmax niemożliwa. Migracja zaaplikowana w prod. Plus guard konserwatywny
  `koryguj_tip_wg_modelu` (w `analyzer_helpers.py`): Groq tip 1X2 z prob modelu <15% → override na
  argmax modelu. Wpięty w `_auto_zapisz_backtest` (top3+kupony). Tylko skrajne przypadki, brak
  prob → nie rusza. +6 testów. Pełna decyzja a/b/c po ~20 świeżych settled — w `TODO.md`.

### Email transakcyjny — Resend
- **`8dcb76a27`**: `utils/mailer.py` — `send_email` via Resend HTTP API (no-dep), `load_dotenv`,
  czyta `RESEND_API_KEY`/`resend_api_key`. `send_welcome_email` wpięte w `/auth/register`
  (graceful, nie blokuje rejestracji). `send_password_reset_email` gotowe na flow reset-tokenów.
  Live test: email dostarczony. FROM=`onboarding@resend.dev` (test-sender, podmień przed prod).
  +6 testów.
- **`a7f815381`**: dokumentacja limitu Resend Free (100/dzień, 3000/mc, 1 domena) w mailer + TODO;
  reset hasła / faktura / domena = follow-up.

### Rynki — Mecz & gol w każdej połowie (GG2H) + HT capture
- **`67f5f418b`**: nowy rynek "Mecz & gol w każdej połowie" — Poisson half-model (rozbicie λ na
  1./2. połowę) + settlement z wyniku HT (`oblicz_tip_correct`) + capture HT z API-Football w
  `results_updater.py` (zapis `ht_home`/`ht_away`). Reorder grupy "Liczba goli" w `markets.py`
  (Over na górze, Under na dole, czytelniejszy UX). +4 pliki testów (`test_betting_utils.py`,
  `test_evening_agent.py`, `test_markets.py`, `test_results_updater_ht.py` nowy).

### Suite
- **1209 passed / 4 skip** (2 fail + 2 error niezwiązane z sesją — `test_checkpoint.py` order
  dependency, `test_file_integrity.py` length check `daily_agent.py` — do zbadania, nie ruszane
  w tej sesji dokumentacyjnej).

## 2026-06-20/21

### Bugi / model (root-cause Cel B + kreator)
- **Kalibracja per-wynik 1X2 — root cause Cel B** (`11cc57232`, 06-20): `calibrate_confidence`
  zaprojektowane dla jednej liczby (confidence vs tip_correct), a stosowane per-wynik na
  pw/pr/pp i bt/o25 w `quick_picks.py`. Na zdegenerowanej krzywej (n_train=41, stare odwrócone
  predykcje) spłaszczało wszystkie wyniki do tej samej wartości → po renorm = uniform. Fix: nie
  kalibruj per-wynik.
- **Gate `CALIBRATION_ENABLED` OFF domyślnie** (`9faa72067`, 06-20): zdegenerowana
  `calibration.json` psuła Kelly + value-bet (zaniżanie). Domyślnie identity, mechanizm krzywej
  zachowany jako `_calibrate_raw` do re-fit (patrz D2 poniżej).
- **Double-chance (1X/X2) devig** (`30ac7c66b`, 06-20): `dc_odds` liczyło `1/(1/a+1/b)` na
  kursach z marżą → double-count overround → kurs <1.0 dla faworyta (kreator pokazał 1X 0.93).
  Fix: zdejmij marżę z trójki 1X2 (devig) przed joint prob → kurs double-chance zawsze >1.0. +2 testy.
- **Rynki: dokładny wynik + multigoal** (`549caa782`, 06-20): grupy "Dokładny wynik" (top-10 z
  macierzy Poissona) + "Multigoal" (0-1..4-6) w `markets.py`; settlement w `oblicz_tip_correct`
  ("Wynik h:a", "Multigoal lo-hi"). GUI renderuje generycznie. +9 testów.
- **Sugerowany typ = argmax 1X2** (`5aa0b6f97`, 06-20): kreator nie zawsze pokazywał "1" jako
  sugestię — teraz argmax modelu.

### Dług techniczny #1-#5 (audyt całościowy 06-20)
- **#1 Refactor `App.jsx`** (`2e112dc2c`, 06-20): 2144→267 linii. Wydzielone components/
  (LoginView, DashboardHome, History, Leaderboard, Settings, AdminPanel, ui, Wizard/*) + lib/
  (api, leagues, tips). Behavior-preserving, build PASS, Playwright OK.
- **#2 Odporność scraperów — health-check** (`f3366933e`, 06-20): `check_and_alert_source_down`
  — alert Telegram + log WARNING gdy źródło (Bzzoiro) zwróci 0/`_valid=False`; graceful, 1 alert/run.
  Wpięte w `_pobierz_kandydatow`.
- **#3 Rozbicie `daily_agent.py`** (`391e7b1b9`, 06-20): 1553→1046 linii; 9 spójnych faz
  wyodrębnionych do `core/daily_phases.py` (injury/forma/betbuilder/kelly/groq-walidacja/
  ensemble/final-enrich). Behavior-preserving, smoke parytet OK.
- **#4 Podwójny backtest — izolacja + usunięcie** (`366b495d2`, `a7e845470`, 06-20/21):
  `backtest_engine.py` najpierw izolowany od prod (guard test-DB, rzuca gdy prod Neon bez
  opt-in), potem USUNIĘTY (moduł + `run_backtest.py` + 2 testy + baseline broad-except) —
  walk-forward zastępuje. `core/backtest.py` (save_prediction) nietknięty.

### Decyzje D1-D8 (06-20 zatwierdzone przez usera, zrealizowane w sesji)
- **D1a — Whitelist +MŚ** (`e9ad8bf1f`, 06-20): "World Cup 2026"/"World Cup"/"Mundial" w
  `LIGI_WHITELIST`; kwalifikacje MŚ nadal odrzucane (blacklist). +2 testy.
- **D1b/D6 — Kursy z 2. źródła = ROZWIĄZANE.** Fallback chain: Bzzoiro → API-Football `/odds`
  → Sofascore. Wpięte w `_wzbogac_o_kursy_fallback` (daily_phases).
  - **AF `/odds`** (`131abc1bf`, 06-21) — PODSTAWOWY fallback, reuse `APISPORTS_KEY` + budżet,
    zero anti-bot. Live smoke potwierdził (Ecuador-Curaçao: home 1.17/draw 7.4/away 13.0/
    over25 1.6/btts 2.55). Koszt ~1 req/mecz/dzień.
  - **Sofascore** (`6b3b2bfd1`, 06-20) — 2. fallback, `sofascore_odds.py`. Obecnie 403
    anti-bot (dotyczy też form_scraper) — działa tylko gdy AF nie ma meczu I 403 ustąpi.
  - +42 testy (AF parsing/fixture-match + Sofascore + fallback order).
- **D2 — Auto-refit kalibracji co +30 settled** (`dd81d829b`, 06-21): `maybe_refit_calibration()`
  w evening_agent po `update_pending`; gdy settled - n_train ≥ 30 → `fit_calibrator()` +
  ostrzeżenie gdy krzywa płaska. Gate `CALIBRATION_ENABLED` zostaje u usera. Stan 06-20:
  58 settled, n_train=41 (delta 17 < 30 → następny refit ~88 settled). +5 testów.
- **D4 — backtest_engine USUNIĘTY** (`a7e845470`, 06-21) — patrz dług techniczny #4 wyżej.
- **D5 — Scal taski 08:00** (06-21, Task Scheduler, NIE w git): `--faza draft` zapisuje
  predykcje (`_auto_zapisz_backtest` bezwarunkowo) + kupony + system_paper + propozycje →
  no-faza `FootStats-DailyAgent` redundantny (robił ściśle mniej, bez enrichu). WYŁĄCZONY
  (Disabled w Task Scheduler). 08:00 = tylko Draft, 11:00 Final, 23:00 Evening.
- **D7 — 15.7 weryfikacja czatu Telegram (nonce)** (`4cbd01d58`, 06-21): `POST /telegram/link/start`
  generuje nonce (TTL 15min), webhook `/start <nonce>` wiąże zweryfikowany chat_id (przed
  gate'em admina), jednorazowy. Migracja kolumn + 9 testów. `set_telegram_chat_id` deprecated
  (fallback).
- D3 (Cel B bug 2 — Groq selekcja) i D8 (JDG/prawnik) NIE zrealizowane — patrz `TODO.md`.

### TECHNICZNE / SECURITY (06-21)
- **Sofascore stealth** (`a5af86ecf`, security fix `d085b5815`): no-dep ukrycie
  `navigator.webdriver`/AutomationControlled vs 403. `--no-sandbox` usunięty po review MEDIUM
  (sandbox Chromium przy obcym JS) — stealth działa bez niego. NIE gwarantuje obejścia 403
  (AF /odds podstawą kursów); pomaga też form_scraper.
- **God-moduły rozbite (behavior-preserving):** `cli.py` 1112→773 (`210d9ec46`, spójne komendy/
  helpery → `cli_commands.py`); `analyzer.py` 930→793 (`6fa110177`, 4 czyste funkcje
  `_analizuj_forme`/`_wyciagnij_json`/`_deduplikuj_kupony`/`_wymusz_40pct` → `analyzer_helpers.py`).
- **daily_io — testy** (`3be80d1b9`): +10 testów `_zapisz_kupon_do_db` (mock DB, zero prod).
- Pre-existing bug udokumentowany (NIE naprawiony, poza scope): `cli.py::_analiza_kuponu` woła
  nieistniejące `_bzz_parse_prob` → `NameError` przy trafieniu w ev_ml.

### Weryfikacja unblocku (06-21, dry-run)
- Pipeline z AF fallback kursów → **System BY utworzył 15 kuponów** (przed fixami: 0) na realnych
  danych (USL/MŚ; kursy AF uzupełniły 7/18 brakujących; sygnał przywrócony bo kalibracja OFF).
  Cache AF pre-warmowany na run 08:00. Budżet AF 11/100.

### Suite
- **1177 passed / 4 skipped** (było 1076 na starcie serii commitów tej sesji).

## 2026-06-19

### Cel A — walk-forward offline, walidacja 10 lig
- Harness `scripts/run_walkforward_prod.py` (classic + Dixon-Coles + ensemble, devig kursów, no-lookahead, zapis `data/walkforward.db` — NIE Neon).
- Cache rozszerzony 5→**10 lig** (32 400 meczów): +ITA Serie A, +FRA Ligue 1, +AUT, +BEL, +SCO.
- **Werdykt 10 lig (out-of-sample, n=25 738):** dixoncoles **51.3%** > baseline 49.6% > poisson_only 48.1%. DC +1.7pp — generalizuje (NED było +1.9pp).
- Kalibracja **MONOTONICZNA** na wszystkich 10 ligach: 37.5→43.2→46.4→58.8% (pasmo 65%+ = strefa zakładów). Per liga (DC): NED 54.9, SCO 54.8, ENG 53.4, ITA 53.1, GER 51.5, ESP 51.2, BEL 50.4, FRA 49.8, AUT 47.8, POL 44.6.
- Fix kodów lig BEL/SCO: format sezonowy B1/SC0 zamiast `/new/` (404) — `c43e0bc3d`.

### Cel B — root cause live ≪ offline (częściowy)
- **bug 1 NAPRAWIONY** (`072ee9035`): `quick_picks` nie budował klucza `pred` → confidence leciało na Groq fallback (overconfident) zamiast prob modelu → inwersja kalibracji live. Fix: `wyniki` dostaje `pred` dict (p_wygrana/p_remis/p_przegrana/btts/over25/under25).
- bug 2 (otwarty, w TODO): `ai_tip` = selekcja Groq (44% remisy, 12.5% wyjazdy hit) zamiast argmax modelu.

### Cel C — Dixon-Coles w produkcji
- Wpięty za flagą `USE_DIXON_COLES` (default ON, env-toggle), `W_BAYESIAN=0.5`. 8 zadań TDD: `b42fd8043`, `ff0da87b5`, `b0e307e94`, `a15b616f5`, `f14255824`, `4e96110d5` (merge `b0a83d8fd`).
- `blend_dixon_coles` (poisson_bayesian): remap pa→pp, blend nad pw/pr/pp, bt/o25 nietknięte, graceful (DC None → classic). Wspólna funkcja z `wf_harness` (parytet prod↔harness).
- Smoke A/B NED: DC 55.2% > baseline 54.0%. Weryfikacja 10 lig po merge = identyczna z przed-merge (lewar nietknięty przez refactor).
- E2e test regresji wiringu (`4cd677820`, merge `e1b8f8809`) — łapie usunięcie wpięcia (dowiedzione RED).
- Code review: `footstats-reviewer` APPROVE z uwagami (0× P1/P2), `footstats-data-guard` SAFE. P3 #1 (luka testu wiringu) naprawiona e2e testem.
- Suita: **1078 pass** / 4 skip.

### Sprzątanie audytu + wpięcia (sesja 06-19 wieczór)
- **Bug 3 (mock leak) — potwierdzony naprawiony:** `coupons.py:_fallback_predictions` (24-31) — mock tylko `DEMO_MODE==1`, inaczej pusta lista; wszystkie 3 ścieżki fetch (brak klucza / pusty wynik / wyjątek) przez fallback. Realny user nie widzi już FAKE meczów (Legia/Lech/Ajax).
- **`waliduj_df_wyniki` — potwierdzony wpięty:** data-quality check przed predykcją (`quick_picks.py:73-74`).
- **`bezpieczny_budget_use` — WPIĘTY** (`25f6bc92a`): swap z `af_budget_use` w `api_football.py:_get`. Typed `BladBudzetu` zamiast `RuntimeError` + pełne logowanie budżetu. Ten sam plik/schema/progi (`cache/api_football/af_budget.json`, 100/5/20) → zero rozjechania liczników. Fallback do wygasłych danych cache zachowany. TDD + suita 1079 pass / 4 skip.
- Uwaga: `af_budget_use` (cache.py) jest teraz martwy w prod (callery tylko w testach) — kandydat do usunięcia osobnym taskiem.

### Zespół subagentów
- Dodany `footstats-scribe` (kronikarz: sesja → TODO/CHANGELOG/STATUS + commit, archiwizuje zamiast kasować).
