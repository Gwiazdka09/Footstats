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

- [ ] **#5 Kalibracja w Kelly/value-bet** — `calibrate_confidence` wciąż czynny w
  `daily_agent.py:816,824` (Kelly) + `daily_filters.py:52` (value-bet). cc(<66)=0.286 zaniża
  stawki / odrzuca value (ten sam zdegenerowany root co Cel B). Fix: identity/bypass aż do
  re-fit na czystych danych. SZYBKI, kończy temat kalibracji. **← START**
- [ ] **#1 Refactor `App.jsx` (2144 linie, monolit)** — 🔴 największy dług frontu. Rozbić na
  komponenty (MatchCard, WizardStep, Dashboard, Settings, History; MarketsPanel/CookieConsent już są).
  Łamie regułę CLAUDE.md (max 800). Po zmianie: weryfikacja Playwright (desktop+mobile).
- [ ] **#2 Odporność scraperów + single-source** — Playwright kruchy (superbet 1128, sts 604;
  psują się przy zmianie HTML), całość wisi na Bzzoiro bez fallbacku. Dodać health-check +
  alert Telegram gdy źródło zwraca 0/zmienia strukturę; rozważyć 2. źródło.
- [ ] **#3 Rozbić `daily_agent.py` (1546 linii, god-module)** — wydzielić fazy
  (fetch/enrich/groq/persist) do testowalnych funkcji. Tam chowały się bugi Cel B.
- [ ] **#4 Podwójny backtest** — `backtest_engine.py` (644, AI-driven, anti-pattern z zapisem
  do prod Neon, obs 3596) vs walk-forward. Usunąć/oznaczyć engine, zostawić walk-forward jako jedyny.
- [ ] **Inne god-moduły** (po #1/#3): `cli.py` 1112, `analyzer.py` 930 — dekompozycja niższy priorytet.

---

## 📋 Następne kroki

1. **Praca teraz:** dług techniczny #5 → #1 → #2 → #3 → #4 (sekcja wyżej).
2. **Pasywne (równolegle):** monitor co kilka dni, czekaj na ~20 świeżych settled → walidacja.
3. **Po walidacji:** ocena λ / Dixon-Coles efekt live; decyzja Cel B bug 2 (Groq selekcja).
4. **Wymaga Ciebie:** Email (Resend key) → JDG + prawnik → płatności.

## Moje uwagi
- [x] **Kreator 1X kurs 0.93 (niemożliwy)** — NAPRAWIONE (06-20, `30ac7c66b`). `dc_odds` liczyło
  `1/(1/a+1/b)` na kursach z marżą → double-count overround → <1.0 dla faworyta. Devig (zdejmij
  marżę z trójki 1X2 nim policzysz joint prob) → kurs double-chance zawsze >1.0. +2 testy.
