# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-18
**Wersja:** v3.4-stable
**Accuracy:** 31.7% live (41 settled) — pipeline + λ naprawione, **czeka na świeże dane**
**Cel:** M1 = 55% win rate

> Ukończone: `git log`. Fazy DONE: 16-20, GUI/UX, SEO, RODO, multi-user (15.6),
> audyt core (A1-A3), λ: kontuzje + xG+obrona. Suite: 1037 testów pass.

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

### 🔴 Bug 3: Mock matches leak do realnych userów
- `coupons.py:_fetch_predictions` zwraca `_mock_predictions()` (Legia/Lech/Ajax — FAKE)
  gdy brak BZZOIRO_KEY / Bzzoiro down / off-season. Realny user w GUI widzi nieistniejące
  mecze jako realne, może budować kupony. **Fix: gate DEMO_MODE, inaczej pusta lista.**

### ✅ Dead code — wyczyszczone (06-18)
- Usunięto: `json_export.py` (cały martwy moduł, 246 linii), `_generate_lesson`
  (dup post_match), `analizuj_liste_meczow` (stary CLI flow), `fetch_match_xg`
  (nieużywany wrapper), `send_trening_raport` (nieużywany notif). 112 testów pass.
- [ ] **Do WPIĘCIA (nie usuwać — użyteczne):** `waliduj_df_wyniki` (walidacja df_mecze —
  data-quality check którego brakuje przed predykcją!) + `bezpieczny_budget_use` (guard budżetu API).
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

## ✅ WALK-FORWARD OFFLINE (Cel A — 2026-06-18, ZROBIONE)

> Harness `scripts/run_walkforward_prod.py` (classic+Dixon-Coles+ensemble, devig kursów,
> no-lookahead, zapis `data/walkforward.db`, NIE Neon). Branch `feat/walkforward-harness`.
> Suite: 1061 pass.

- **Werdykt NED n=1842 (out-of-sample, kalibracja OFF):** dixoncoles 54.1% > baseline 52.2% >
  poisson_only 50.5%. Kalibracja **MONOTONICZNA** (37→42→49→70% per pasmo) — NIE odwrócona.
- **Walidacja 10 lig (2026-06-19, out-of-sample, n=25738):** dixoncoles **51.3%** > baseline 49.6%
  > poisson_only 48.1%. DC +1.7pp nad baseline — **generalizuje** (NED było +1.9pp). Kalibracja
  MONOTONICZNA (37.5→43.2→46.4→58.8%) na wszystkich 10 ligach. Per liga (DC): NED 54.9, SCO 54.8,
  ENG 53.4, ITA 53.1, GER 51.5, ESP 51.2, BEL 50.4, FRA 49.8, AUT 47.8, POL 44.6. Pasmo 65%+ = 58.8%.
  Cache: `data/hist_cache/full_dataset.parquet` (32400 meczów, 10 lig, xgabora OFF).
- **Kluczowy wniosek:** model statystyczny zdrowy i kalibracja monotoniczna na 10 ligach. Live
  31.7%/odwrócenie NIE z modelu → Cel B.
- [x] **Cel B root cause ZNALEZIONY (06-19):** bug 1 = quick_picks nie budował `pred` → confidence
  z Groq fallback (overconfident) zamiast modelu → inwersja. **Naprawione + w main** (072ee9035).
  bug 2 = `ai_tip` = selekcja Groq (44% remisy, 12.5% wyjazdy) zamiast argmax modelu — czeka na
  ≥15 System settled (decyzja a/b/c po danych).
- [ ] **Dixon-Coles do wpięcia w prod** (+1.7pp na 10 ligach potwierdzone) — osobny spec.
- [ ] Fast-follow perf: pętla O(n²), 10 lig ~3-5h — optymalizacja (searchsorted/kursor).

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

- [ ] Rynki: dokładny wynik / multigoal (rozliczalne, dużo opcji)
- [ ] Kartki/rożne — wymaga feedu zdarzeń (API-Football statistics) + settlement
- [ ] BetBuilder: Bzzoiro odds dla compound + settlement combo "1 & Over 1.5"
  (teraz kurs = fair 1/szansa; złożone typy nie przechodzą weryfikacji Bzzoiro)

---

## 📋 Następne kroki

1. **Pasywne (priorytet):** monitor co kilka dni, czekaj na ~20 świeżych settled → walidacja
2. **Po walidacji:** Dixon-Coles (jeśli accuracy nadal poniżej celu)
3. **Wymaga Ciebie:** Email (Resend key) → JDG + prawnik → płatności
