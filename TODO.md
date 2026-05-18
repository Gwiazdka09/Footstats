# FootStats TODO — Updated 2026-05-18

## Completed Phases (Archive)

### Phase 1: STABILNOŚĆ — COMPLETE ✅
### Phase 2: PERFORMANCE — COMPLETE ✅
### Phase 3: QUALITY — COMPLETE ✅
### Phase 3.5: v3.4 Lambda Optimizer — COMPLETE ✅

**Total Test Suite: 105+ tests across 49 test files**

---

## Phase 4: MAINTENANCE & HYGIENE (Current)

### P4.1: Version Sync 🟡
- [ ] Ujednolicić VERSION w config.py, CLAUDE.md, STATUS.md do "v3.4-stable"

### P4.2: SQLite Context Manager Refactor 🟠
- [ ] referee_db.py: 3x `conn = sqlite3.connect()` → zamienić na `with`
- [ ] dashboard.py: `_conn()` → zwracać context manager zamiast raw connection
- [ ] Dodać test: test_referee_db_conn_cleanup.py

### P4.3: Exception Handling Audit 🟠
- [ ] Przejrzeć 216x `except Exception` — dodać logging.warning/error tam gdzie brak
- [ ] Priorytet: backtest_engine.py (6x), coupon_settlement.py (4x), calibration.py (3x)

### P4.4: Cache Cleanup 🟡
- [ ] Usunąć 614 plików cache starszych niż 30 dni (263MB w cache/form/)
- [ ] Dodać skrypt/cron: `scripts/cleanup_cache.py --days 30`

### P4.5: Root Directory Cleanup 🟡
- [ ] Przenieść check_settlement*.py do scripts/
- [ ] Przenieść PHASE3_SPEC.md, PHASE4_SPEC.md do docs/archive/
- [ ] Przenieść PROJECT_STATE.md, DAILY_ANALYSIS_*.md do docs/
- [ ] Przenieść maintenance_prompt.md do docs/

---

## Phase 5: PRODUCTION INTEGRATION (On Demand)

- [ ] Task 4.1: Wire response caching into live API routes
- [ ] Task 4.2: Integrate checkpointing into daily_agent batch flow
- [ ] Task 4.3: Prometheus metrics export (logging_config stubs → real endpoints)
- [ ] Task 4.4: SofaScore injury scraper for lambda correction

---

## Blockers
None — all core modules working.
