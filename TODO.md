# FootStats TODO — Updated 2026-05-27

## Completed Phases (Archive)

### Phase 1–5: ALL COMPLETE ✅
### Phase 6: HARDENING — COMPLETE ✅
### Phase 7.1–7.6, 7.8: COMPLETE ✅
### Phase 8: RELIABILITY & PERFORMANCE — COMPLETE ✅
### Phase 9: DB CONSOLIDATION & LOGIN FIX — COMPLETE ✅

---

## Phase 10: CODE QUALITY & ACCURACY (aktywna)

### 10.1: Quick Fixes — COMPLETE ✅ (2026-05-27)
- [x] `telegram_notify.py` — już miał timeout=15 (skip)
- [x] `pyproject.toml` — 3.0 → 3.4 (commit 812cc66)
- [x] `__pycache__/` + `data/footstats.db` usunięte (commit 241a0f2)

### 10.2: Broad Except Cleanup (P2) — IN PROGRESS
- [x] sts.py — 3x zamienione na (PWTimeout, ValueError, KeyError) (commit 241a0f2) ✅
- [x] superbet.py — już czysty ✅
- [x] analyzer.py — już czysty ✅
- [x] base_playwright.py — 1x justified (generic retry wrapper) ✅
- [x] daily_agent.py — 5x zawężone (13→8): OSError/ValueError/KeyError/AttributeError/TypeError
- [ ] daily_agent.py — 8x pozostałe (orchestration log-and-continue, P3)
- NOTE: ~220 remaining w całym projekcie

### 10.3: subprocess.Popen Audit — COMPLETE ✅
- [x] daily_agent.py — except Exception → except OSError + komentarz fire-and-forget
- [x] backtest.py, post_match_analyzer.py, evening_agent.py, cli.py — już miały OSError

### 10.4: Large File Refactoring (P3)
- [ ] daily_agent.py (1396 LOC) — wydzielić: parsowanie CLI, enrichment, walidacja
- [ ] analyzer.py (1393 LOC) — wydzielić: prompts, scoring, output formatting
- [ ] superbet.py (1128 LOC) — wydzielić: auth, scraping, parsing

---

## Phase 7 (continued): ACCURACY IMPROVEMENT

### 7.7: Feature Engineering (P2)
- [x] xG z Understat — scraper + blend 20% w poisson.py ✅ (cache-only, prefetch w daily_agent)
- [x] Forma domowa vs wyjazdowa — core/form.py ✅
- [x] Odpoczynek — core/fatigue.py ✅

### 7.x: Accuracy Tracking
- [x] Dashboard A/B tab ✅
- [x] Weekly report per liga ✅
- [x] CLV tracking — auto-capture z API-Football /odds w evening_agent ✅

---

## Phase 9 (otwarte)

### 9.1 BLOCKER: Cloud Run env vars
- [ ] Sprawdzić FOOTSTATS_USER, FOOTSTATS_PASSWORD_HASH, JWT_SECRET w Cloud Run Console

### 9.5: Konsolidacja DB access (P3, opcjonalne) — PARTIAL ✅
- [x] probability_calibrator.py → utils/db.py ✅
- [x] ensemble_optimizer.py → utils/db.py ✅
- [ ] referee_db.py → utils/db.py (DEFERRED — testy używają tmp_path SQLite, wymaga przepisania testów)
- [x] dashboard.py → utils/db.py ✅

---

## Proposed New Tests

- [x] test_telegram_timeout.py — OK, już miał timeout (skip)
- [ ] test_subprocess_cleanup.py — verify Popen processes are cleaned up
- [x] test_version_consistency.py — pyproject.toml vs config.py VERSION match ✅
- [x] test_broad_except_audit.py — flag new bare/broad except additions ✅ (regression gate, 63 tests)

---

## Milestones

| Milestone | Accuracy | Status |
|-----------|----------|--------|
| **M0** | ~42% overall | ✅ Current (baseline) |
| **M1** | 55% overall | 🔄 In progress — calibration + filters |
| **M2** | 60% overall | Bayesian Poisson + ensemble + value filter |
| **M3** | 65% selected | xG + feature engineering + stop-loss |
| **M4** | 70% selected | Full optimization + CLV + 3mo track record |

---

## Blockers
- **Cloud Run env vars** — login fix wymaga ustawienia w Cloud Run Console
- **Accuracy 42%** — poniżej M1 target, wymaga kalibracji + feature engineering
