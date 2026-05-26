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

### 7.1: Systematyczny Backtest & Pomiar Accuracy (PRIORYTET #1) ✅
- [x] `scripts/accuracy_report.py` — hit-rate per liga/typ/confidence/kupon-type + P&L (2026-05-26)
- [ ] Automatyczny raport tygodniowy (weekly_report.py rozszerzenie)
- [ ] Dashboard tab "Accuracy" w Streamlit z wykresami hit-rate

### 7.2: Filtr Lig — Stawiaj TYLKO Gdzie Masz Edge (PRIORYTET #2) ✅
- [x] `LIGI_WHITELIST` / `LIGI_BLACKLIST` / `LIGA_FILTER_ENABLED` → config.py (2026-05-26)
- [x] `_pre_filtruj_ligi()` w daily_agent — odrzuca blacklist przed Groq (2026-05-26)

### 7.3: Kalibracja Prawdopodobieństw (PRIORYTET #3) ✅
- [x] `core/probability_calibrator.py` — Isotonic Regression (sklearn), fit/load/apply (2026-05-26)
- [x] Integracja z daily_agent: `_dodaj_kelly` używa `calibrate_confidence()` zamiast raw % (2026-05-26)
- [x] `data/calibration.json` generowany z 351 historycznych predykcji

### 7.4: Poisson Bayesian Update (PRIORYTET #4) ✅
- [x] `core/poisson_bayesian.py` — Dixon-Coles att/def + Bayesian prior shrinkage (2026-05-26)
- [x] Recency: ostatnie 5 meczów 3x waga; `blend_with_classic()` do A/B testów
- [ ] A/B test na backtest.db — do wykonania osobno

### 7.5: Ensemble Weights Optimization (PRIORYTET #5) ✅
- [x] `core/ensemble_optimizer.py` — log-loss grid search per liga (2026-05-26)
- [x] `ensemble.py`: `get_weights_for_league()` + `liga` param w `ensemble_probs()` (2026-05-26)
- [x] Integracja z `_oblicz_roznica_modeli()` w daily_agent.py

### 7.6: Value Bet Filter (PRIORYTET #6) ✅
- [x] `core/value_bet.py`: `calculate_ev()`, `is_value_bet()`, `filter_value_bets()` (2026-05-26)
- [x] `_pre_filtruj_value_bet()` w daily_agent: EV>3% + Kelly>1% (2026-05-26)
- [ ] CLV tracking (scrape kursy przy kickoff) — do zrobienia przy dodatkowej infrastrukturze
- [ ] Dashboard: wykres EV vs P&L

### 7.7: Feature Engineering (PRIORYTET #7)
- [ ] xG z FBref/Understat (wymaga zewnętrznego scrapera)
- [ ] Forma domowa vs wyjazdowa — częściowo w DomWyjazd class (form.py)
- [ ] Odpoczynek (dni od ostatniego meczu), pogoda — do dodania

### 7.8: Stop-Loss & Bankroll Protection ✅
- [x] `bankroll.py`: `check_daily_stop_loss` (10%), `get_loss_streak`, `get_stake_multiplier` (50% po 3L) (2026-05-26)
- [x] `check_weekly_alert` — drawdown >20% w tygodniu (2026-05-26)
- [x] Integracja z daily_agent: stop-loss exit, streak → reduce stawki, weekly alert

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
