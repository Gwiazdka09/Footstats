# FootStats TODO — Updated 2026-05-25

## Completed Phases (Archive)

### Phase 1–5: ALL COMPLETE ✅
**108 source modules, 53 test files**

---

## P0: KRYTYCZNE NAPRAWY (2026-05-25) ✅

- [x] **FIX** `daily_agent.py` — ucięty na linii 1286 → przywrócono z git ✅
- [x] **FIX** `core/lambda_optimizer.py` — ucięty na linii 275 → przywrócono ✅
- [x] **FIX** `api/main.py` — ucięty na linii 307 → przywrócono ✅ **← TO BLOKOWAŁO LOGOWANIE Admin_JG!**

**UWAGA:** `api/main.py` ucięty = SyntaxError = API nie startuje = logowanie niemożliwe.
Plik naprawiony — wymaga `git commit + redeploy` aby przywrócić logowanie na produkcji.

---

## Phase 6: HARDENING & RELIABILITY

### P6.1: Brakujące timeout w requests — COMPLETE ✅
Wszystkie pliki miały już timeout (weryfikacja + test_requests_timeout.py PASS 2026-05-25)

### P6.2: Groq/RAG Feedback Refresh — COMPLETE ✅
- [x] groq_lessons.json zaktualizowany 2026-05-25 (n=14,634 meczów) ✅
- [x] RAG knowledge base aktywna (pobierz_rag_wzorce via SQLite ai_feedback) ✅
- [x] Accuracy check: 42.4% win rate (14W/19L z 33 rozliczonych kuponów) — M0 baseline ✅
- NOTE: Statusy kuponów niespójne (WIN/WON, LOSE/LOST) → do normalizacji w Phase 7

### P6.3: Monitoring plików (zapobieganie obcinaniu) — COMPLETE ✅
- [x] Dodać pre-commit hook sprawdzający syntax `py_compile` ✅ `.git/hooks/pre-commit`
- [x] Integrity check w run_daily.bat ✅ KROK 0b — blokuje pipeline na SyntaxError
- [x] FIX: `api/main.py` — usunięty duplikat ogona (linie 339–360) powodujący SyntaxError ✅

---

## Phase 7: ROADMAPA DO 55-70% ACCURACY 🎯

### Cel: Z obecnych ~50% overall → 55-60% overall, 70%+ na wyselekcjonowanych meczach

### 7.1: Systematyczny Backtest & Pomiar Accuracy (PRIORYTET #1)
**Bez pomiaru nie wiesz co poprawiać.**
- [ ] Skrypt `scripts/accuracy_report.py` — raport hit-rate z backtest.db:
  - Per liga (Ekstraklasa, Premier League, Serie A...)
  - Per typ zakładu (1, 2, X, Over 2.5, BTTS...)  
  - Per confidence band (50-60%, 60-70%, 70-80%, 80%+)
  - Per source (Bzzoiro ML vs API-Football vs Poisson)
  - Wykres kalibracji: predicted prob vs actual hit-rate
- [ ] Automatyczny raport tygodniowy (weekly_report.py rozszerzenie)
- [ ] Dashboard tab "Accuracy" w Streamlit z wykresami hit-rate

### 7.2: Filtr Lig — Stawiaj TYLKO Gdzie Masz Edge (PRIORYTET #2)
**Nie wszystkie ligi są przewidywalne jednakowo.**
- [ ] Na podstawie accuracy_report → zidentyfikuj ligi gdzie hit-rate > 55%
- [ ] Dodaj `LIGI_WHITELIST` do config.py (ligi z udowodnioną edge)
- [ ] Dodaj `LIGI_BLACKLIST` do config.py (ligi z hit-rate < 45%)
- [ ] Pre-filtr w daily_agent: odrzucaj mecze z blacklist PRZED Groq
- [ ] Cel: mniej kuponów, ale wyższy hit-rate per kupon

### 7.3: Kalibracja Prawdopodobieństw (PRIORYTET #3)
**Model mówi 70% a trafia 55% = źle skalibrowany.**
- [ ] Platt Scaling / Isotonic Regression na historycznych predykcjach
- [ ] Moduł `core/probability_calibrator.py`:
  - fit() na historii (predicted_prob, actual_outcome)
  - transform() koryguje pewnosc_pct przed Kelly
- [ ] Integracja z daily_agent po Groq, przed Kelly
- [ ] Test: porównaj Kelly P&L ze i bez kalibracji na backteście

### 7.4: Poisson Bayesian Update (PRIORYTET #4)
**Poisson z jedną lambdą jest zbyt prosty.**
- [ ] Uwzględnij siłę ataku vs siłę obrony (nie jedną średnią)
- [ ] Bayesian prior z historii ligi (średnia goli w lidze jako prior)
- [ ] Weighting: ostatnie 5 meczów > ostatnie 20 meczów
- [ ] Moduł `core/poisson_bayesian.py` — rozszerza obecny poisson.py
- [ ] A/B test: stary Poisson vs Bayesian na 100 meczach z backtest.db

### 7.5: Ensemble Weights Optimization (PRIORYTET #5)
**Obecnie ensemble = 50/50 Poisson + Bzzoiro. Wagi powinny być dynamiczne.**
- [ ] Dla każdej ligi oblicz optimal weight (Poisson vs Bzzoiro vs API-Football)
- [ ] Moduł `core/ensemble_optimizer.py`:
  - grid search na historii: w_poisson * P_poisson + w_bzzoiro * P_bzzoiro
  - minimize log-loss na validation set
- [ ] Zapisuj optymalne wagi per liga w data/ensemble_weights.json
- [ ] Integracja z _oblicz_roznica_modeli() w daily_agent.py

### 7.6: Value Bet Filter (PRIORYTET #6)
**Nie stawiaj na mecze bez value — nawet jeśli masz 70% pewności.**
- [ ] Rozbuduj `core/value_bet.py`:
  - Closing Line Value (CLV) — porównaj swój kurs z kursem zamykającym
  - Expected Value > 3% minimalny próg
  - Kelly fraction > 1% minimum
- [ ] Tracking CLV: scrape kursy w momencie kickoff i porównaj z draft
- [ ] Dashboard: wykres EV vs actual P&L per tydzień

### 7.7: Feature Engineering (PRIORYTET #7)
**Dodaj dane które model jeszcze nie widzi.**
- [ ] xG (Expected Goals) z FBref/Understat — lepsze niż surowe gole
- [ ] Forma domowa vs wyjazdowa osobno (nie łączona)
- [ ] Motywacja: degradacja/awans/puchar — wpływa na wynik
- [ ] Odpoczynek: dni od ostatniego meczu (zmęczenie)
- [ ] Pogoda: deszcz/wiatr wpływa na Under/Over

### 7.8: Stop-Loss & Bankroll Protection
**Nawet 60% accuracy = bankrut jeśli stawki źle dobrane.**
- [ ] Dzienny stop-loss: max 3 kupony/dzień, max 10% bankroll/dzień
- [ ] Streak detection: po 3 przegranych z rzędu → obniż stawki 50%
- [ ] Rozbuduj calibration.py o rolling window (ostatnie 20 kuponów ważniejsze)
- [ ] Dashboard: alert gdy bankroll spadnie > 20% w tygodniu

---

## Proposed Tests

- [x] test_response_cache_eviction.py ✅
- [x] test_ram_cache_eviction.py ✅
- [x] test_null_bytes_guard.py ✅
- [ ] test_requests_timeout.py — grep requests bez timeout
- [ ] test_accuracy_report.py — poprawność obliczeń hit-rate
- [ ] test_probability_calibrator.py — Platt scaling correctness
- [ ] test_poisson_bayesian.py — Bayesian update vs vanilla Poisson
- [ ] test_ensemble_optimizer.py — grid search convergence
- [ ] test_value_bet_filter.py — CLV i EV calculations
- [ ] test_daily_agent_prefilter.py — pre_filtruj_kursy edge cases
- [ ] test_coupon_settlement_edge.py — partial settlement

---

## Kamienie Milowe (Milestones)

| Milestone | Accuracy | Opis |
|-----------|----------|------|
| **M0 (current)** | ~50% overall | Działający pipeline, brak systematycznego pomiaru |
| **M1** | 55% overall | Pomiar accuracy + filtr lig + kalibracja prob |
| **M2** | 60% overall | Bayesian Poisson + ensemble weights + value filter |
| **M3** | 65% selected | xG + feature engineering + stop-loss |
| **M4** | 70% selected | Pełna optymalizacja + CLV tracking + 3 mies. track record |

**Realistyczny timeline:** M1 za ~2-3 tygodnie, M2 za ~6 tygodni, M3 za ~3 miesiące, M4 za ~6 miesięcy.

---

## Blockers
- **KRYTYCZNY**: `api/main.py` naprawiony ale nie zcommitowany — Admin_JG nie może się zalogować dopóki nie deploy
- **P6.1**: 15x requests bez timeout = ryzyko hang
- **P6.2**: RAG lessons stale 33 dni
- **P6.3**: Pliki regularnie się obcinają — potrzebny integrity check
