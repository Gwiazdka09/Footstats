# FootStats TODO — Updated 2026-05-26

## Completed Phases (Archive)

### Phase 1–5: ALL COMPLETE ✅
### Phase 6: HARDENING — COMPLETE ✅
### Phase 7.1–7.6, 7.8: COMPLETE ✅

---

## P0: RECURRING — File Truncation Fix (2026-05-26) ✅

- [x] 10x src/ pliki przywrócone z git HEAD (config, daily_agent, lambda_optimizer, async_utils, response_cache, value_bet, api/main, db/migrations, bankroll, ensemble)
- [x] 5x test files przywrócone (test_auth, test_coupon_tracker, test_daily_agent_faza, test_evening_agent, test_response_cache)
- [x] Syntax verification: 0 errors across 108 modules

**ROOT CAUSE:** Pliki regularnie się obcinają — pre-commit hook istnieje ale nie zapobiega obcinaniu przez zewnętrzne narzędzia. Potrzebny jest monitoring integralności plików.

---

## Phase 8: RELIABILITY & PERFORMANCE

### 8.1: Requests Timeout — COMPLETE ✅ (commit 401d25063)
- [x] timeout=15 dodany do 10 plików (2 już miały, skip)
- NOTE: ai/client.py zmieniony 120→15 — rozważyć przywrócenie 120 dla Ollama

### 8.2: SQLite Context Manager — COMPLETE ✅ (commit c5e8a22d5)
- [x] probability_calibrator.py, ensemble_optimizer.py, dashboard.py → with statement

### 8.3: Cleanup — COMPLETE ✅
- [x] 11 dirs __pycache__ usunięte
- [x] `data/.fuse_hidden*` — nie istnieją (Windows, FUSE nie dotyczy)
- [x] `.git/index.lock` — nie istnieje

### 8.4: Thread Safety Audit — COMPLETE ✅ (commit a3f6eff64)
- [x] response_cache: async_wrapper + response_cache_info() wrapped in _CACHE_LOCK
- [x] lambda_optimizer: duplikat __main__ block usunięty
- NOTE: lambda_optimizer._cache double-checked locking OK (GIL gwarantuje atomowość)

---

## Phase 7 (continued): ACCURACY IMPROVEMENT

### 7.7: Feature Engineering (P2)
- [ ] xG z FBref/Understat (wymaga scrapera)
- [ ] Forma domowa vs wyjazdowa oddzielnie
- [ ] Odpoczynek (dni od ostatniego meczu)

### 7.x: Accuracy Dashboard
- [ ] Dashboard tab "Accuracy" w Streamlit
- [ ] Automatyczny raport tygodniowy (weekly_report.py rozszerzenie)
- [ ] A/B test Bayesian Poisson vs Classic na backtest.db
- [ ] CLV tracking (scrape kursy przy kickoff)
- [ ] EV vs P&L wykres w dashboard

---

## Proposed Tests

- [x] test_file_integrity.py — 10/10 pass (commit 24b3fc1eb) ✅
- [x] test_requests_timeout.py — verify all requests have timeout ✅ (już istniał)
- [x] test_accuracy_report.py — hit-rate calculation correctness ✅ (7 tests)
- [x] test_probability_calibrator.py — Platt scaling correctness ✅ (10 tests)
- [x] test_value_bet_filter.py — EV and Kelly calculations ✅ (13 tests)
- [x] test_daily_agent_prefilter.py — pre_filtruj edge cases ✅ (13 tests)
- [x] test_coupon_settlement_edge.py — oblicz_tip_correct edge cases ✅ (24 tests)
- [ ] test_poisson_bayesian.py — Bayesian update vs vanilla
- [ ] test_ensemble_optimizer.py — grid search convergence

---

## Milestones

| Milestone | Accuracy | Status |
|-----------|----------|--------|
| **M0** | ~42% overall | ✅ Current (baseline measured) |
| **M1** | 55% overall | 🔄 In progress — calibration + filters active |
| **M2** | 60% overall | Bayesian Poisson + ensemble weights + value filter |
| **M3** | 65% selected | xG + feature engineering + stop-loss |
| **M4** | 70% selected | Full optimization + CLV + 3mo track record |

---

## Blockers
- **git index.lock** — wymaga ręcznego `del F:\bot\.git\index.lock` na Windows
- **File truncation** — rekurencyjny problem, pre-commit hook nie wystarczy
- **Accuracy 42%** — poniżej M1 target, wymaga dalszej kalibracji
