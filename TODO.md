# FootStats TODO — Updated 2026-05-24 (auto-scan #3)

## Completed Phases (Archive)

### Phase 1: STABILNOSC — COMPLETE ✅
### Phase 2: PERFORMANCE — COMPLETE ✅
### Phase 3: QUALITY — COMPLETE ✅
### Phase 3.5: v3.4 Lambda Optimizer — COMPLETE ✅

**108 source modules, 49 test files**

---

## P0: KRYTYCZNE NAPRAWY (NATYCHMIAST)

- [ ] **FIX** `core/response_cache.py` — plik uciety w linii 255, brak `_evict_oldest()`, `_cleanup_expired()`, `cleanup_stale_cache()` (916 bytes brakuje). Komenda: `git checkout HEAD -- src/footstats/core/response_cache.py`
- [ ] **FIX** `ai/analyzer.py` — 31 null bytes na koncu. Komenda: `git checkout HEAD -- src/footstats/ai/analyzer.py`
- [ ] **FIX** `core/async_utils.py` — 90 null bytes na koncu. Komenda: `git checkout HEAD -- src/footstats/core/async_utils.py`
- [ ] **COMMIT** 41 dirty files w working copy (39 modified + 2 untracked). Review + commit lub stash.
- [ ] **DAILY AGENT MARTWY** — ostatni run: 2026-04-18 (36 dni temu!). Brak nowych predictions od 2026-04-23. Task Scheduler prawdopodobnie wyłączony lub broken. Sprawdzić Windows Task Scheduler → uruchomić `python -m footstats.daily_agent` ręcznie, zweryfikować logi.
- [ ] **MIGRACJE PG-ONLY** — `db/migrations.py` używa składni PostgreSQL (`SERIAL`, `setval`, `DROP CONSTRAINT IF EXISTS`, `ALTER COLUMN`). Tabele SQLite **nie mają kolumny `user_id`** (coupons, bankroll_state, bankroll_history). API filtruje po `user_id` → endpointy `/coupons/active`, `/coupon/place`, `/coupons` rzucą **500 error** przy SQLite. Naprawić: napisać SQLite-kompatybilne migracje lub dual-dialect wrapper.
- [ ] **BANKROLL PRAWIE PUSTY** — 8.00 PLN po serii 3x LOSE + 4x VOID (na 8 kuponów). Kupon #12 ACTIVE od 2026-04-19 — prawdopodobnie stale/nierozliczony. Rozliczyć lub VOID-ować kupon #12, rozważyć reset bankrollu.
- [ ] **GROQ/RAG STALE 33 DNI** — `groq_lessons.json` last update 2026-04-21. RAG daje nieaktualne rady. Uruchomić `Phase 6` learning loop po naprawie daily_agent.

---

## Phase 4: MAINTENANCE & HYGIENE (In Progress)

### P4.1–P4.2: ✅ Done
### P4.3: Exception Handling Audit 🔴 (209x bare except)
- [ ] Top priorytet (13-16x): sts.py, superbet.py, base_playwright.py, daily_agent.py, analyzer.py
- [ ] Drugi priorytet (6-11x): cli.py, logging.py, results_updater.py, historical_loader.py, backtest_engine.py, cache.py, form_scraper.py, enriched.py
- [ ] Dodac logging.warning/error tam gdzie brak

### P4.6: Unused Imports Cleanup 🟠
- [x] cli.py, data_fetcher.py, form.py
- [ ] poisson.py: 6 unused imports
- [ ] classifier.py: 4 unused
- [ ] ensemble.py: 1 unused (annotations)

### P4.11: pyproject.toml dependency fix 🟠
- [ ] Przeniesc psycopg2-binary, sqlalchemy, alembic z [dependencies] do [project.optional-dependencies.cloud]
- [ ] Sync z requirements.txt

### P4.12: Disk bloat cleanup 🟠
- [ ] Dodac `node_modules/` do .gitignore (3.1 GB!)
- [ ] `git rm -r --cached src/footstats/gui/node_modules/`
- [ ] Usunac root `__pycache__/` (stale: ai_client, scraper_kursy, footstats, ai_analyzer)
- [ ] Usunac `.aider.tags.cache.v4/` (768KB)
- [ ] Usunac `tests/scratch`
- [ ] Usunac `data/.fuse_hidden*` (orphaned FUSE files)
- [ ] Rozwazyc czyszczenie starych PDF w pdf/ (12 plikow)

### P4.13: RAM cache eviction 🟠
- [ ] `utils/cache.py`: `_RAM_CACHE` nie ma MAX size ani eviction — dodac MAX_ENTRIES + LRU

---

## Phase 5: PRODUCTION INTEGRATION

- [x] 5.1: response_cache.py — WPIETY (⚠️ ale working copy uszkodzona)
- [x] 5.5: Operator Agent + Kreator fix
- [ ] 5.2: Integrate checkpoint.py into daily_agent batch flow
- [ ] 5.3: Prometheus metrics export
- [ ] 5.4: SofaScore injury scraper dla lambda correction

---

## Phase 6: GROQ LEARNING & FEEDBACK LOOP

- [ ] Przeanalizowac lekcje z ostatnich kuponow (last update 2026-04-21 — **33 dni stale!**)
- [ ] Uaktualnic feedback w RAG knowledge base
- [ ] Sprawdzic accuracy Groq na ostatnich meczach (75%+ confidence)

---

## Proposed Tests

- [x] test_response_cache_eviction.py ✅
- [ ] test_referee_db_conn_cleanup.py — sqlite context manager
- [ ] test_daily_agent_prefilter.py — pre_filtruj_kursy edge cases
- [ ] test_coupon_settlement_edge.py — partial settlement, void handling
- [ ] test_powiadomienie_windows.py — PowerShell escape
- [ ] test_ram_cache_eviction.py — MAX_ENTRIES, TTL dla _RAM_CACHE
- [ ] test_null_bytes_guard.py — file integrity check

---

## Stale Docs (do cleanup)

- [ ] `docs/archive/` vs `docs/archives/` — zduplikowane foldery archiwalne
- [ ] `docs/BETA_FIX_PROMPT.md` — prawdopodobnie nieaktualny
- [ ] `docs/session_2026-05-07.md` — notatki sesyjne, do archiwum
- [ ] `docs/SecondBrain_Log_2026-04-17.md` — stary log

---

## Blockers
- **P0**: response_cache.py uciety = cache eviction nie dziala = potencjalny memory leak w produkcji
- P4.3 (bare except) to priorytet stabilnosci
- groq_lessons stale 33 dni — RAG moze dawac nieaktualne rady
