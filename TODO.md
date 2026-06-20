# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-19
**Wersja:** v3.4-stable
**Accuracy:** model offline 51.3% 10 lig (DC, NED 54.9%, kalibracja monotoniczna) | live 31.7% (stare, sprzed fixów Cel B — czeka na świeże)
**Cel:** M1 = 55% win rate

> Ukończone: `git log`. Fazy DONE: 16-20, GUI/UX, SEO, RODO, multi-user (15.6),
> audyt core (A1-A3), λ: kontuzje + xG+obrona, Cel A (walk-forward), Cel B bug 1,
> Cel C (Dixon-Coles w prod). Suite: 1079 testów pass.

---

## 🔍 AUDYT SETTLEMENT (06-18) — główna funkcja, sprawdzone na wszystkie sposoby

> Werdykt: **settlement dobrze wpięty**. Ścieżki: `daily_agent.py:1256` (co run pipeline)
> + `/coupons/settle` (admin) + `/cron/settle` (x_cron_secret) + `__main__` + evening_agent
> `update_pending` (predykcje 23:00). `settle_active_coupons` bez filtra user → wszyscy + System.

### ✅ Bug A: 2 rynki BetBuilder niesettlowalne (Handicap)
- `Handicap -1 Gospodarz` / `Handicap +1 Gość` → `oblicz_tip_correct` zwracał None →
  combo "BB: ..." z nimi NIGDY się nie rozliczał. Dodano obsługę (1:1 z betbuilder_rules).

### ✅ Bug B: "Gospodarz/Gość Over X.5" liczyło TOTAL gole zamiast drużynowych
- Łapało się na generyczny Over/Under (suma goli) → fałszywe trafienia (np. 0-1 dla
  "Gospodarz Over 0.5" = WON, źle). Dodano regex drużynowy PRZED generycznym. Latentny
  (brak w prod settled), fix prewencyjny. **Pełna zgodność WSZYSTKICH rynków z _PREDYKATY (0 niezgodności).**

### ✅ Bug C: stale-DRAFT nigdy nie czyszczone
- DRAFT z przeszłą datą nigdy nie awansowany do ACTIVE → nie settluje, nie VOID, rośnie
  w nieskończoność (prod: 9 takich). Dodano cleanup w `settle_active_coupons`: DRAFT +
  data < dziś-VOID_AFTER_DAYS → VOID. 3 stare (05-30) pójdą do VOID przy następnym runie.

### 🟡 Kosmetyka (zamknięte kupony, NIE naprawiam)
- Kupon #154 LOST: leg "BB: 1 + Under 3.5" @ 3-0 ma `leg_won=False` (źle, dom wygrał+Under),
  ale combo i tak LOST (drugi leg przegrał) → status końcowy poprawny. Tylko display legu.

---

## 🔍 AUDYT GŁĘBOKI (06-18) — bugi side-effect / cruft

> Wzorzec: kod tworzony wcześnie z efektami ubocznymi na PRODUKCJI lub martwy.

### ✅ Bug 1: Testy Telegram wysyłały realnie (5e77b517c)
- "Arsenal-Chelsea 3:2" na prawdziwy Telegram przy każdym pytest z kluczami. Zmockowane.

### ✅ Bug 2: Testy auth tworzyły userów w PROD Neon (598063e02)
- `test_delete_account_flow` + `test_create_and_deactivate_user` → 30 z 41 userów w prod
  to test garbage (22 testuser_ + 8 deleted_user_). Gate DATABASE_URL→FOOTSTATS_TEST_DB.
- [x] **Wyczyszczono 30 test-userów z prod** (06-18): backup + FK-aware DELETE
  (30 bankroll_state + users). Prod: 41→11 userów, 0 śmieci. Zostali realni + System.

### ✅ Bug 3: Mock matches leak do realnych userów (06-19)
- `coupons.py:_fetch_predictions` zwracał `_mock_predictions()` (Legia/Lech/Ajax — FAKE)
  gdy brak BZZOIRO_KEY / Bzzoiro down / off-season → realny user widział nieistniejące mecze.
- Fix: `_fallback_predictions()` (`coupons.py:24-31`) — mock TYLKO przy `DEMO_MODE==1`,
  inaczej pusta lista. Wszystkie 3 ścieżki fetch (brak klucza / pusty wynik / wyjątek) idą przez fallback.

### ✅ Dead code — wyczyszczone (06-18)
- Usunięto: `json_export.py` (cały martwy moduł, 246 linii), `_generate_lesson`
  (dup post_match), `analizuj_liste_meczow` (stary CLI flow), `fetch_match_xg`
  (nieużywany wrapper), `send_trening_raport` (nieużywany notif). 112 testów pass.
- [x] **WPIĘTE (06-19):** `waliduj_df_wyniki` — data-quality check przed predykcją
  (`quick_picks.py:73-74`). `bezpieczny_budget_use` — guard budżetu API z typed `BladBudzetu`
  + logowaniem, swap z `af_budget_use` w `api_football.py:_get` (commit `25f6bc92a`).
- [ ] **Martwy kod (osobny task):** `af_budget_use` w `cache.py` po wpięciu `bezpieczny_budget_use`
  ma callery już tylko w testach (`test_cache.py`) — kandydat do usunięcia, NIE teraz.
- Reszta (lineup_confidence_penalty, batch_record_closing_odds, cache cleanup, dozwolone_dodatki/test) —
  niski priorytet, featury działają przez inne ścieżki.

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M1** | 55% win rate | 🔴 W toku | świeże settled + walidacja A/B |
| **M2** | 60% win rate | ⏸️ | Po M1 — tuning |
| **M3** | 65% selected | ⏸️ | Po M2 |
| **BETA** | Testerzy | ⏸️ | Po M1 |

---

## 🎯 MODEL — następne kroki (Cel A/B/C ZROBIONE → `CHANGELOG.md` 2026-06-19)

> Zrobione: walk-forward 10 lig (DC 51.3%, kalibracja monotoniczna), Cel B bug 1 fix,
> Dixon-Coles w prod (flaga `USE_DIXON_COLES` ON). Szczegóły + hashe → `CHANGELOG.md`.

- [ ] **Mierz efekt DC live** — `calibration_monitor.py` co kilka dni; po ≥15-20 settled porównaj z baseline.
- [ ] **Bug 2 decyzja** — po ≥15 System settled: czy Groq selekcja szkodzi (a: ogranicz / b: argmax modelu / c: tnij conf).
- [~] Perf walk-forward (3-5h): zbadane 06-19. Harness sfaktoryzowany (searchsorted prefix,
  historia raz — `09c517a9e`, bit-parytet) ale **zysk wall-clock ~0**. Wąskie gardło NIE w
  filtrowaniu df, tylko w `predict_match`/`blend_dixon_coles` (skan rosnącej historii per mecz,
  `.tail(OSTATNIE_N)`). Prawdziwy lewar = trim okna historii, ale Dixon-Coles fituje att/def po
  całej historii → zmiana semantyki modelu, wymaga model-analyst + walidacji trafności. ODŁOŻONE
  (pętla offline, odpalana rzadko). NIE goń jako "darmowy perf".

## 🔴 PRIORYTET — WALIDACJA (czekaj i mierz, NIE dokładaj zmian λ)

> **Decyzja 06-18:** wpięto 6 zmian λ (kontuzje, xG+obrona, heurystyka, klasyfikacja,
> wagi 70/30, renorm 1X2) — wszystkie NIEzwalidowane na danych. Dalsze zmiany psują
> atrybucję (nie wiadomo co pomogło). STOP na nowe λ aż zbierzemy dane.

- [ ] Co kilka dni: `python scripts/calibration_monitor.py` (Neon, read-only)
  - czy kalibracja przestała być **odwrócona** (była: 90%+ pewność → 11% trafność)
  - System (bez Groq) vs Pipeline (Groq) — werdykt bottlenecku LLM (potrzeba ≥15 System settled)
  - czy accuracy ruszyła z 31.7%
- [ ] Po ~20 świeżych settled z naprawionego pipeline → A/B, ocena które λ-zmiany pomogły
- [x] **FIX (06-18): rozliczanie predykcji było zepsute** — standalone predykcje (Groq +
  System) nigdy nie settlowały auto (results_updater poza Task Scheduler; evening tylko
  nogi kuponów). Wpięte `update_pending` w evening_agent (23:00). Backlog 41→58 settled.
  **Bez tego plan walidacji był zagłodzony** — teraz predykcje rosną codziennie.
- **Zbieranie:** System paper-trading autonomiczne (Task Scheduler 08:00) + settle 23:00. ~1-2 tyg.
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

## 💰 MONETYZACJA / LAUNCH (wymaga Ciebie)

### Prawne
- [ ] Konsultacja z prawnikiem (ToS bukmacherów) przed komercją
- [ ] Rejestracja JDG (CEIDG, 1 dzień) — przed pierwszym płatnym userem

### Email transakcyjny
- [ ] Resend.com — załóż konto, podaj `RESEND_API_KEY` + FROM adres
- [ ] Potwierdzenie rejestracji, reset hasła, faktura

### Płatności (Lemon Squeezy / Paddle — zdecydowane, po JDG)
- [ ] Cennik przed checkout + warunki auto-renewal
- [ ] Webhooks: subscription.updated/cancelled/payment_failed
- [ ] Email: potwierdzenie, faktura, retry, ostrzeżenie przed odnowieniem
- [ ] Upgrade/downgrade + proration

### Hosting
- [ ] Custom domain (opcjonalne)

---

## 🟡 TECHNICZNE / SECURITY

- [ ] 15.7: weryfikacja własności czatu Telegram (nonce /start przez webhook) —
  przed realnymi userami (security MEDIUM). Teraz: walidacja formatu numerycznego.
- [ ] daily_io — testy (czysta integracja DB, glue nad już-testowanym; niska wartość). Opcjonalne.

---

## 💡 OPCJONALNE rozszerzenia

- [x] **Rynki: dokładny wynik / multigoal** (06-20, `549caa782`) — `markets.py` grupy
  "Dokładny wynik" (top-10 z macierzy Poissona) + "Multigoal" (0-1..4-6); settlement
  w `oblicz_tip_correct` ("Wynik h:a", "Multigoal lo-hi"). GUI renderuje generycznie. +9 testów.
- [ ] **Kartki/rożne** — ZABLOKOWANE: brak danych. Wymaga feedu zdarzeń (API-Football
  statistics) + osobnego modelu (Poisson jest dla goli) + budżet API. Nie do zbudowania bez feedu.
- [x] **BetBuilder compound** — settlement combo "BB: 1 + Over 1.5" działa (`oblicz_tip_correct`),
  a kursy są correlation-aware fair (`szansa_combo` liczy joint prob z macierzy, NIE naiwny iloczyn).
  Pozostała luka (realne kursy bukmacherskie dla compound) ZABLOKOWANA — feed Bzzoiro ich nie dostarcza.

---

## 🏗 DŁUG TECHNICZNY / ARCHITEKTURA (audyt całościowy 06-20)

> Ocena warstw: core A-, testy A, API B+, AI B-, GUI C, scrapers C+, daily_agent C.
> Rdzeń + testy = poziom zawodowy. Długi ciągnące w dół ↓ (kolejność = priorytet pracy).

- [x] **#5 Kalibracja w Kelly/value-bet** (06-20, `9faa72067`) — gate `CALIBRATION_ENABLED`
  (domyślnie OFF → identity); mechanizm krzywej zachowany jako `_calibrate_raw` do re-fit.
  Domyka temat zdegenerowanej calibration.json (Kelly + value-bet już nie zaniżają). → re-fit: patrz **D2**.
- [x] **#1 Refactor `App.jsx`** (06-20, `2e112dc2c`) — 2144→**267** linii. Wydzielone
  components/ (LoginView, DashboardHome, History, Leaderboard, Settings, AdminPanel, ui,
  Wizard/*) + lib/ (api, leagues, tips). Behavior-preserving, build PASS, Playwright OK.
  (CouponWizard 411 — świadomie, spójny stan kreatora; dalszy podział obniżyłby czytelność.)
- [x] **#2 Odporność scraperów** (06-20, `f3366933e`) — `check_and_alert_source_down`: alert
  Telegram + log WARNING gdy Bzzoiro zwróci 0/`_valid=False`; graceful (nie crash), 1 alert/run.
  Wpięte w `_pobierz_kandydatow`. (2. źródło = dalej otwarte, niższy priorytet.)
- [x] **#3 Rozbić `daily_agent.py`** (06-20, `391e7b1b9`) — 1553→**1046**; 9 spójnych faz
  do `core/daily_phases.py` (injury/forma/betbuilder/kelly/groq-walidacja/ensemble/final-enrich).
  Behavior-preserving (zero zmian asercji), smoke parytet OK. Splątane bloki zostawione świadomie.
- [x] **#4 Podwójny backtest** (06-20, `366b495d2`) — `backtest_engine.py` izolowany od prod
  (guard test-DB, rzuca gdy prod Neon bez opt-in) + DEPRECATED na rzecz walk-forward. NIE usunięty.
  → decyzja usera: USUNĄĆ jak nieprzydatny, patrz **D4**.
- [ ] **Inne god-moduły** (niższy priorytet): `cli.py` 1112, `analyzer.py` 930 — dekompozycja kiedyś.

---

## 🚀 DECYZJE 06-20 → DO REALIZACJI (następna sesja, większy model)

> Użytkownik zatwierdził kierunki. Wykorzystaj subagentów. Kolejność = priorytet.

- [x] **D1a — Whitelist +MŚ** (06-21, commit w sesji) — "World Cup 2026"/"World Cup"/"Mundial"
  w `LIGI_WHITELIST`; kwalifikacje MŚ NADAL odrzucane (blacklist). +2 testy.
- [x] **D1b/D6 — Kursy z 2. źródła = ROZWIĄZANE** (06-21). Fallback chain kursów:
  **Bzzoiro → API-Football `/odds` → Sofascore**. Wpięte w `_wzbogac_o_kursy_fallback` (daily_phases).
  - **AF `/odds`** (`131abc1bf`, `api_football.kursy_fixture`/`znajdz_fixture_id`/`fetch_odds_af`) =
    PODSTAWOWY fallback. Reuse `APISPORTS_KEY`+budżet, **zero anti-bot**. LIVE smoke potwierdził
    (Ecuador-Curaçao: home 1.17/draw 7.4/away 13.0/over25 1.6/btts 2.55). Koszt ~1 req/mecz/dzień (/fixtures cache'owane).
  - **Sofascore** (`6b3b2bfd1`, `sofascore_odds.py`) = 2. fallback. ⚠️ obecnie 403 anti-bot
    (dotyczy też form_scraper) — działa tylko gdy AF nie ma danego meczu I 403 ustąpi. Niski priorytet.
  - +42 testy (AF parsing/fixture-match + Sofascore + fallback order). Budżet AF mockowany w testach.
- [x] **D2 — Auto-refit kalibracji co +30 settled** (06-21, sesja) — `maybe_refit_calibration()`
  w evening_agent po `update_pending`; gdy settled - n_train ≥ 30 → `fit_calibrator()` +
  ostrzeżenie gdy krzywa płaska. Gate `CALIBRATION_ENABLED` ZOSTAJE u usera (refit nie włącza).
  Stan 06-20: 58 settled, n_train=41 (delta 17 < 30 → następny refit ~88 settled). +5 testów.
- [ ] **D3 — Cel B bug 2 (Groq selekcja).** Bez zmian — czeka na ≥15 ŚWIEŻYCH System settled.
  Potem decyzja: ogranicz Groq / argmax modelu / tnij conf. (User: nic do douszczegółowienia.)
- [x] **D4 — backtest_engine USUNIĘTY** (06-21, `a7e845470`) — moduł + `run_backtest.py` +
  2 testy + baseline broad-except. Walk-forward zastępuje. `core/backtest.py` (save_prediction) nietknięty.
- [x] **D5 — Scal taski 08:00** (06-21) — `--faza draft` zapisuje predykcje (`_auto_zapisz_backtest`
  bezwarunkowo) + kupony + system_paper + propozycje → no-faza `FootStats-DailyAgent` redundantny
  (robił ściśle mniej, bez enrichu). **WYŁĄCZONY** (Disabled). 08:00 = tylko Draft, 11:00 Final, 23:00 Evening.
- [x] **D7 — 15.7 weryfikacja czatu Telegram (nonce)** (06-21, `4cbd01d58`) — `POST /telegram/link/start`
  generuje nonce (TTL 15min), webhook `/start <nonce>` wiąże zweryfikowany chat_id (przed gate'em admina),
  jednorazowy. Migracja kolumn + 9 testów. `set_telegram_chat_id` deprecated (fallback).
- [ ] **D8 — JDG / prawnik — WSTRZYMANE (sam koniec).** User waha się: konsekwencje JDG jak
  się nie uda; prawnik za drogi. Bez akcji. Wrócić po walidacji modelu.

---

## 📋 Następne kroki

> Dług techniczny #1-#5 ZROBIONY (06-20). DECYZJE D1-D8: D1a/D1b/D2/D4/D5/D6/D7 ✓,
> D3/D8 czekają. Suite 1167 pass / 4 skip. Kursy odblokowane (AF /odds, live OK).

1. **Zweryfikuj live (jutro po 08:00):** czy System tworzy kupony — teraz ma kursy (AF fallback)
   + sygnał (kalibracja OFF). Sprawdź `calibration_monitor.py` + liczbę nowych ACTIVE/settled.
2. **Pasywne:** zbieraj świeże settled (wolne tempo OK, mecze nie co godzinę). Pilnuj budżetu AF (100/dzień).
3. **Po walidacji (~+30 settled → ~88):** D2 auto-refit odpali sam; gdy krzywa zdrowa →
   włącz `CALIBRATION_ENABLED=1`; D3 decyzja Cel B bug 2 (Groq selekcja).
4. **Opcjonalnie:** Sofascore 403 stealth (tylko jeśli AF coverage za cienki na egzotyki).
5. **Sam koniec (D8):** JDG/prawnik — wstrzymane (koszt/ryzyko). Email/płatności po walidacji.

## Moje uwagi
- [x] **Kreator 1X kurs 0.93 (niemożliwy)** — NAPRAWIONE (06-20, `30ac7c66b`). `dc_odds` liczyło
  `1/(1/a+1/b)` na kursach z marżą → double-count overround → <1.0 dla faworyta. Devig (zdejmij
  marżę z trójki 1X2 nim policzysz joint prob) → kurs double-chance zawsze >1.0. +2 testy.
