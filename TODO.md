# FootStats TODO — Updated 2026-05-24

## Completed Phases (Archive)

### Phase 1: STABILNOSC — COMPLETE ✅
### Phase 2: PERFORMANCE — COMPLETE ✅
### Phase 3: QUALITY — COMPLETE ✅
### Phase 3.5: v3.4 Lambda Optimizer — COMPLETE ✅

**99 source modules, 45 test files**

---

## P0: KRYTYCZNE NAPRAWY (NATYCHMIAST)

- [ ] **FIX** `core/response_cache.py` — plik uciety w linii 255, brak `_evict_oldest()`, `_cleanup_expired()`, `cleanup_stale_cache()`. Przywrocic z git: `git checkout HEAD -- src/footstats/core/response_cache.py`
- [ ] **FIX** `ai/analyzer.py` — 31 null bytes na koncu pliku. Obciac: `truncate` lub `git checkout HEAD -- src/footstats/ai/analyzer.py`
- [ ] **FIX** `core/async_utils.py` — 90 null bytes na koncu. Jak wyzej.
- [ ] **COMMIT** 39 dirty files w working copy. Review + commit lub stash.

---

## Phase 4: MAINTENANCE & HYGIENE (In Progress)

### P4.1–P4.2: ✅ Done
### P4.3: Exception Handling Audit 🔴 (209x bare except)
- [ ] Top priorytet (13-16x): sts.py, superbet.py, base_playwright.py, daily_agent.py
- [ ] Drugi priorytet (6-11x): cli.py, logging.py, results_updater.py, historical_loader.py, backtest_engine.py
- [ ] Dodac logging.warning/error tam gdzie brak

### P4.6: Unused Imports Cleanup 🟠
- [x] cli.py, data_fetcher.py, form.py
- [ ] poisson.py: 6 unused imports (math, PEWNIACZEK_PROG, BZZOIRO_MAX_ROZN, HeurystaZmeczeniaRotacji, KlasyfikatorMeczu, ImportanceIndex, _wagi_mecze, AnalizaDomWyjazd)
- [ ] classifier.py: 4 unused (FINAL_REMIS_BOOST, IMP2_PROG_FINAL, IMP2_BONUS_FINAL, IMP2_WAKACJE)
- [ ] ensemble.py: 1 unused (annotations)

### P4.11: pyproject.toml dependency fix 🟠 (NEW)
- [ ] Przeniesc psycopg2-binary, sqlalchemy, alembic z [dependencies] do [project.optional-dependencies.cloud]
- [ ] Sync z requirements.txt

### P4.12: Disk bloat cleanup 🟠 (NEW)
- [ ] Dodac `src/footstats/gui/node_modules/` do .gitignore (3.1 GB!)
- [ ] Usunac gui/node_modules z git tracking: `git rm -r --cached src/footstats/gui/node_modules/`
- [ ] Usunac `__pycache__/` directories (10 dirs)
- [ ] Usunac `.aider.tags.cache.v4/` (768KB)
- [ ] Usunac `scripts/__pycache__/`
- [ ] Rozwazyc czyszczenie starych PDF w pdf/ (12 plikow)

### P4.13: RAM cache eviction 🟠 (NEW)
- [ ] `utils/cache.py`: `_RAM_CACHE` nie ma MAX size ani eviction — dodac MAX_ENTRIES + LRU jak w response_cache

---

## Phase 5: PRODUCTION INTEGRATION

- [x] 5.1: response_cache.py — WPIETY (⚠️ ale working copy uszkodzona)
- [x] 5.5: Operator Agent + Kreator fix
- [ ] 5.2: Integrate checkpoint.py into daily_agent batch flow
- [ ] 5.3: Prometheus metrics export
- [ ] 5.4: SofaScore injury scraper dla lambda correction

---

## Phase 6: GROQ LEARNING & FEEDBACK LOOP

- [ ] Przeanalizowac lekcje z ostatnich kuponow (ostatni update 2026-04-21 — 33 dni!)
- [ ] Uaktualnic feedback w RAG knowledge base
- [ ] Sprawdzic accuracy Groq na ostatnich meczach (75%+ confidence)

---

## Proposed Tests

- [x] test_response_cache_eviction.py ✅
- [ ] test_referee_db_conn_cleanup.py — sqlite context manager
- [ ] test_daily_agent_prefilter.py — pre_filtruj_kursy edge cases
- [ ] test_coupon_settlement_edge.py — partial settlement, void handling
- [ ] test_powiadomienie_windows.py — PowerShell escape
- [ ] test_ram_cache_eviction.py — MAX_ENTRIES, TTL dla _RAM_CACHE (NEW)
- [ ] test_null_bytes_guard.py — file integrity check (NEW)

---

## Blockers
- **P0**: response_cache.py uciety = cache eviction nie dziala = potencjalny memory leak w produkcji
- P4.3 (bare except) to priorytet stabilnosci
