# FootStats TODO — Updated 2026-05-20

## Completed Phases (Archive)

### Phase 1: STABILNOSC — COMPLETE ✅
### Phase 2: PERFORMANCE — COMPLETE ✅
### Phase 3: QUALITY — COMPLETE ✅
### Phase 3.5: v3.4 Lambda Optimizer — COMPLETE ✅

**Total Test Suite: 105+ tests across 47 test files, 99 source modules**

---

## Phase 4: MAINTENANCE & HYGIENE (Current)

### P4.1: Version Sync 🟠
- [ ] config.py:11 → VERSION = "v3.4-stable"
- [ ] CLAUDE.md:1 → "FootStats v3.4-stable"

### P4.2: SQLite Context Manager Refactor 🟠
- [ ] referee_db.py: 3x `conn = sqlite3.connect()` → `with sqlite3.connect() as conn:`
- [ ] dashboard.py: `_conn()` → context manager zamiast raw connection
- [ ] Dodac test: test_referee_db_conn_cleanup.py

### P4.3: Exception Handling Audit 🟠
- [ ] Top priorytet (13-16x except Exception): sts.py, superbet.py, base_playwright.py, daily_agent.py, analyzer.py
- [ ] Drugi priorytet (6-11x): cli.py, logging.py, results_updater.py, historical_loader.py, backtest_engine.py
- [ ] Dodac logging.warning/error tam gdzie brak

### P4.4: Cache Cleanup 🟡
- [ ] Usunac 682 plikow cache >30 dni (263MB)
- [ ] Stworzyc `scripts/cleanup_cache.py --days 30`
- [ ] Dodac do run_daily.bat jako KROK 0.5

### P4.5: Root Directory Cleanup 🟡
- [ ] Przeniesc check_settlement*.py (3 pliki) do scripts/
- [ ] Przeniesc PHASE3_SPEC.md, PHASE4_SPEC.md do docs/archive/
- [ ] Przeniesc PROJECT_STATE.md, DAILY_ANALYSIS_*.md do docs/
- [ ] Przeniesc maintenance_prompt.md do docs/
- [ ] Usunac lub przeniesc validation_errors.csv do data/

---

## Phase 5: PRODUCTION INTEGRATION (Next)

- [ ] 5.1: Wire response_cache.py into live API routes (modul gotowy, nie wpiety)
- [ ] 5.2: Integrate checkpointing into daily_agent batch flow
- [ ] 5.3: Prometheus metrics export (logging_config stubs → real endpoints)
- [ ] 5.4: SofaScore injury scraper dla lambda correction

---

## Blockers
None — all core modules working, pipeline stable.
