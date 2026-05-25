# FootStats TODO — Updated 2026-05-25

## Completed Phases (Archive)

### Phase 1: STABILNOSC — COMPLETE ✅
### Phase 2: PERFORMANCE — COMPLETE ✅
### Phase 3: QUALITY — COMPLETE ✅
### Phase 3.5: v3.4 Lambda Optimizer — COMPLETE ✅

**108 source modules, 49 test files**

---

## P0: KRYTYCZNE NAPRAWY (COMPLETE 2026-05-24)

- [x] **FIX** `core/response_cache.py` — restored from HEAD (916 bytes, 3 eviction functions) ✅
- [x] **FIX** `ai/analyzer.py` — null bytes removed ✅
- [x] **FIX** `core/async_utils.py` — null bytes removed, safe event loop pattern ✅
- [x] **COMMIT** All dirty files committed as `2c62f8dfc` ✅
- [x] **DAILY AGENT** — restarted, operational (0 candidates in 72h window) ✅
- [x] **MIGRACJE DUAL-DIALECT** — SQLite + PostgreSQL support added to migrations.py ✅
- [x] **BANKROLL** — Coupon #12 ACTIVE since 2026-04-19, daily_agent handles settlement ✅
- [x] **GROQ/RAG REFRESHED** — `groq_lessons.json` updated 2026-05-25, trainer.py UTF-8 fix applied ✅

---

## Phase 4: MAINTENANCE & HYGIENE (In Progress)

### P4.1–P4.2: ✅ Done
### P4.3: Exception Handling Audit ✅ COMPLETE
- [x] Top priorytet (0/5): sts.py, superbet.py, base_playwright.py, daily_agent.py, analyzer.py ✅
- [x] All bare excepts removed ✅
- [x] Logging integrated ✅

### P4.6: Unused Imports Cleanup ✅ COMPLETE
- [x] cli.py, data_fetcher.py, form.py
- [x] poisson.py: 7 unused removed ✅
- [x] classifier.py: 4 unused removed ✅
- [x] ensemble.py: annotations removed ✅

### P4.11: pyproject.toml dependency fix ✅ COMPLETE
- [x] psycopg2-binary, sqlalchemy, alembic → [project.optional-dependencies.cloud] ✅

### P4.12: Disk bloat cleanup ✅ COMPLETE
- [x] `node_modules/` → .gitignore ✅
- [x] root `__pycache__/` cleaned ✅
- [x] `.aider.tags.cache.v4/` removed ✅
- [x] `tests/scratch` removed ✅
- [x] `data/.fuse_hidden*` cleaned ✅

### P4.13: RAM cache eviction ✅ COMPLETE
- [x] `utils/cache.py`: MAX_RAM_ENTRIES=200, eviction logic added ✅
- [x] test_ram_cache_eviction.py created ✅

---

## Phase 5: PRODUCTION INTEGRATION (In Progress)

- [x] 5.1: response_cache.py — restored + working ✅
- [x] 5.5: Operator Agent + Kreator fix ✅
- [x] 5.2: Checkpoint integration (save/recovery/cleanup) ✅
- [x] 5.3: Prometheus metrics middleware + /metrics endpoint ✅
- [x] 5.4: Injury lambda correction via injury_correction() ✅

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
- [x] test_ram_cache_eviction.py — MAX_ENTRIES, TTL dla _RAM_CACHE ✅
- [x] test_null_bytes_guard.py — file integrity check ✅

---

## Stale Docs (COMPLETE) ✅

- [x] `docs/archive/` vs `docs/archives/` — consolidated to archive/ ✅
- [x] `docs/BETA_FIX_PROMPT.md` — archived ✅
- [x] `docs/session_2026-05-07.md` — archived ✅
- [x] `docs/SecondBrain_Log_2026-04-17.md` — archived ✅

---

## Blockers
- **P0**: response_cache.py uciety = cache eviction nie dziala = potencjalny memory leak w produkcji
- P4.3 (bare except) to priorytet stabilnosci
- groq_lessons stale 33 dni — RAG moze dawac nieaktualne rady
