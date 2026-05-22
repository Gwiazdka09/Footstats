# FootStats TODO — Updated 2026-05-22

## Completed Phases (Archive)

### Phase 1: STABILNOSC — COMPLETE ✅
### Phase 2: PERFORMANCE — COMPLETE ✅
### Phase 3: QUALITY — COMPLETE ✅
### Phase 3.5: v3.4 Lambda Optimizer — COMPLETE ✅

**99 source modules, 45 test files**

---

## Phase 4: MAINTENANCE & HYGIENE (Current)

### P4.1: Version Sync ✅
- [x] config.py:11 → VERSION = "v3.4-stable"
- [x] CLAUDE.md:1 → "FootStats v3.4-stable"

### P4.2: SQLite Context Manager Refactor ✅
- [x] referee_db.py: 3x try/finally → `with sqlite3.connect() as conn:`
- [x] dashboard.py: `_conn()` → context manager
- [ ] Dodac test: test_referee_db_conn_cleanup.py

### P4.3: Exception Handling Audit 🔴 (223x bare except)
- [ ] Top priorytet (13-16x): sts.py, superbet.py, base_playwright.py, daily_agent.py, analyzer.py
- [ ] Drugi priorytet (6-11x): cli.py, logging.py, results_updater.py, historical_loader.py, backtest_engine.py
- [ ] Dodac logging.warning/error tam gdzie brak

### P4.4: Cache Cleanup ✅ (RESOLVED)
- [x] Cache dir: tylko 2 pliki, 6.3MB

### P4.5: Root Directory Cleanup ✅
- [x] Usunieto brain_graph.html, validation_errors.csv, tests/scratch
- [x] Usunieto data/lf_sig.txt, lf_ver.txt, data/env_wzor.txt
- [x] Usunieto gui scaffolding: counter.ts, typescript.svg, vite.svg

### P4.6: Unused Imports Cleanup 🟠
- [x] cli.py, data_fetcher.py, form.py
- [ ] fatigue.py, classifier.py (+ pozostale z ~70 kandydatow)

### P4.7: Dead Dependencies ✅
- [x] Usunieto z requirements.txt: psycopg2-binary, sqlalchemy, alembic

### P4.8: Response Cache Memory Leak ✅
- [x] _RESPONSE_CACHE: MAX_ENTRIES=500 + LRU eviction
- [x] _evict_oldest() i _cleanup_expired() zaimplementowane
- [x] test_response_cache_eviction.py dodane

### P4.9: Duplikat import Langfuse ✅
- [x] analyzer.py: usunięty duplikat `from langfuse import Langfuse` linia 25

### P4.10: Deprecated asyncio API ✅
- [x] async_utils.py: `asyncio.get_event_loop()` → safe pattern

---

## Phase 5: PRODUCTION INTEGRATION (Next)

- [x] 5.1: response_cache.py — JUZ WPIETY
- [x] 5.5: Operator Agent + Kreator fix
- [ ] 5.2: Integrate checkpoint.py into daily_agent batch flow
- [ ] 5.3: Prometheus metrics export (logging_config stubs → real endpoints)
- [ ] 5.4: SofaScore injury scraper dla lambda correction

---

## Phase 6: GROQ LEARNING & FEEDBACK LOOP

- [ ] Przeanalizowac lekcje z ostatnich kuponów
- [ ] Uaktualnić feedback w RAG knowledge base
- [ ] Sprawdzić accuracy Groq na ostatnich meczach (75%+ confidence)

---

## Proposed Tests (from audit 2026-05-22)

- [x] test_response_cache_eviction.py — max entries, TTL expiry, memory cap ✅
- [ ] test_referee_db_conn_cleanup.py — sqlite context manager
- [ ] test_daily_agent_prefilter.py — pre_filtruj_kursy, pre_filtruj_tokenow edge cases
- [ ] test_coupon_settlement_edge.py — partial settlement, void handling
- [ ] test_powiadomienie_windows.py — PowerShell escape (single quote injection)

---

## Blockers
- Brak krytycznych blockerów. P4.3 to priorytet stabilności.
