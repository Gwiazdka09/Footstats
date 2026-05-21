# FootStats TODO — Updated 2026-05-21

## Completed Phases (Archive)

### Phase 1: STABILNOSC — COMPLETE ✅
### Phase 2: PERFORMANCE — COMPLETE ✅
### Phase 3: QUALITY — COMPLETE ✅
### Phase 3.5: v3.4 Lambda Optimizer — COMPLETE ✅

**99 source modules, 45 test files**

---

## Phase 4: MAINTENANCE & HYGIENE (Current)

### P4.1: Version Sync ✅
- [x] config.py:11 → VERSION = "v3.4-stable" (`0e681773`)
- [x] CLAUDE.md:1 → "FootStats v3.4-stable"

### P4.2: SQLite Context Manager Refactor ✅
- [x] referee_db.py: 3x try/finally → `with sqlite3.connect() as conn:` (`b8892025`)
- [x] dashboard.py: `_conn()` → context manager
- [ ] Dodac test: test_referee_db_conn_cleanup.py

### P4.3: Exception Handling Audit 🟠
- [ ] Top priorytet (13-16x): sts.py, superbet.py, base_playwright.py, daily_agent.py, analyzer.py
- [ ] Drugi priorytet (6-11x): cli.py, logging.py, results_updater.py, historical_loader.py, backtest_engine.py
- [ ] Dodac logging.warning/error tam gdzie brak

### P4.4: Cache Cleanup ✅ (RESOLVED)
- [x] Cache dir: tylko 2 pliki, 6.3MB — problem z 682 plikami/263MB juz nie istnieje

### P4.5: Root Directory Cleanup 🟡
- [ ] Przeniesc check_settlement*.py (3 pliki) do scripts/
- [ ] Przeniesc PHASE3_SPEC.md, PHASE4_SPEC.md do docs/archive/
- [ ] Przeniesc PROJECT_STATE.md, DAILY_ANALYSIS_*.md do docs/
- [ ] Przeniesc maintenance_prompt.md do docs/
- [ ] Przeniesc validation_errors.csv do data/
- [ ] BETA_LAUNCH.md → docs/

### P4.6: Unused Imports Cleanup 🟠
- [x] cli.py, data_fetcher.py, form.py (`59dd2c45`)
- [ ] fatigue.py, classifier.py (+ pozostale z ~75 kandydatow)

### P4.7: Dead Dependencies ✅
- [x] Usunieto z requirements.txt: psycopg2-binary, sqlalchemy, alembic (grep src/ — brak uzycia)
- [ ] Opcjonalnie: `pip install -e .` aby odswiezyc egg-info

---

## Phase 5: PRODUCTION INTEGRATION (Next)

- [x] 5.1: response_cache.py — JUZ WPIETY (settings, coupons/active, coupons, coupon-summary, matches/today)
- [x] 5.5: Operator Agent + Kreator fix (`operator_agent`, `preview.html`, `Admin_JG` user_id)
- [ ] 5.2: Integrate checkpoint.py into daily_agent batch flow (częściowo: `data/operator_state/latest.json`)
- [ ] 5.3: Prometheus metrics export (logging_config stubs → real endpoints)
- [ ] 5.4: SofaScore injury scraper dla lambda correction

---

## Blockers
- **Claude Code usage limit** (reset ~16:00 Warsaw) — TASK 5 i P4.6 reszta czekaja na wznowienie sesji.
