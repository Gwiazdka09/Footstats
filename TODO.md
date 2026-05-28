# FootStats TODO — Updated 2026-05-28

## Completed Phases (Archive)

### Phase 1–9: ALL COMPLETE ✅

---

## Phase 10: CODE QUALITY & ACCURACY (aktywna)

### 10.0: FILE RESTORE — COMPLETE ✅ (2026-05-28)
- [x] **Restore 12 truncated/corrupted files z git HEAD** ✅
- [x] Zbadać przyczynę rekurencyjnej truncation — **PRZYCZYNA**: Write tool na dużych plikach (>800 LOC) przy wysokim kontekście → truncacja. Mitygacja: pre-commit hook + test_file_integrity_v2. Używać Edit zamiast Write. ✅
- [x] Wzmocnić pre-commit hook: py_compile + null-byte check na KAŻDYM .py ✅

### 10.1: Quick Fixes — COMPLETE ✅ (2026-05-27)
- [x] `pyproject.toml` — 3.0 → 3.4
- [x] `__pycache__/` + `data/footstats.db` usunięte

### 10.2: Broad Except Cleanup (P2) — PARTIAL
- [x] sts.py — 3x zamienione ✅
- [x] superbet.py — już czysty ✅
- [x] daily_agent.py — 5x zawężone (13→8)
- [ ] daily_agent.py — 8x pozostałe (orchestration log-and-continue, P3)
- NOTE: ~233 remaining w całym projekcie (top: sts 13, cli 10, logging 8)

### 10.3: subprocess.Popen Audit — COMPLETE ✅

### 10.4: Large File Refactoring (P3)
- [ ] daily_agent.py (1396 LOC) — wydzielić: parsowanie CLI, enrichment, walidacja
- [ ] analyzer.py (1393 LOC) — wydzielić: prompts, scoring, output formatting
- [ ] superbet.py (1128 LOC) — wydzielić: auth, scraping, parsing

### 10.5: Cleanup stale files (P2)
- [x] Usunąć `CLAUDE_CODE_PROMPT_PHASE9.md` ✅
- [x] Usunąć `validation_errors.csv` ✅
- [x] Usunąć `.aider.tags.cache.v4/` ✅
- [x] Usunąć `.coverage` ✅
- [x] Dodać `src/footstats/gui/node_modules/` do .gitignore ✅

---

## Phase 9 (otwarte)

### 9.1 Cloud Run env vars — DONE ✅ (2026-05-28)
- [x] FOOTSTATS_USER, FOOTSTATS_PASSWORD_HASH, JWT_SECRET — ustawione, zgodne z .env

### 9.5: Konsolidacja DB access (P3)
- [ ] referee_db.py → utils/db.py (DEFERRED — wymaga przepisania testów)

---

## Proposed New Tests

- [x] test_file_integrity_v2.py — py_compile + null-byte check ALL .py files (regression gate) ✅
- [x] test_subprocess_cleanup.py — verify Popen processes are cleaned up ✅
- [x] test_version_consistency.py ✅
- [x] test_broad_except_audit.py ✅

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
- ~~12 broken files~~ — FIXED (restore z git HEAD)
- ~~Cloud Run env vars~~ — DONE (zgodne z .env)
- **Accuracy 42%** — poniżej M1 target
