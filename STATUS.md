# FootStats — Project Status Report

**Last Updated:** 2026-06-03 (auto-audit)  
**Current Version:** v3.4-stable  
**Build Status:** ✅ OK — 0 SyntaxError, 0 null bytes  
**System State:** FUNCTIONAL

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Syntax** | ✅ OK | 0 SyntaxError w 80+ .py |
| **Source Files** | ✅ | ~80 .py modules w src/footstats/ (22.5k LOC) |
| **Tests** | ✅ | 67 test files w tests/ |
| **AI Accuracy** | 🟡 | ~42.4% win rate — poniżej M1 target 55% |
| **Automation** | ✅ | daily_agent.py OK |
| **API** | ✅ | FastAPI + dashboard OK |
| **DB** | ✅ | Neon PG (prod) + SQLite (backtest) |
| **Timeouts** | ✅ | Wszystkie requests.get/post mają timeout |
| **Thread Safety** | ✅ | Lock w circuit_breaker, response_cache, lambda_optimizer |
| **Ollama** | ✅ | qwen2.5:7b lokalny + Groq fallback |
| **Security** | ✅ | Brak eval/pickle/os.system |

---

## OTWARTE PROBLEMY

| # | Problem | Priorytet | Szczegóły |
|---|---------|-----------|-----------|
| 1 | **160x `except Exception`** | 🟡 P2 | Top: base_playwright(14), analyzer(8), daily_agent(8), logging(7) |
| 2 | **Accuracy 42.4%** | 🟡 P2 | Poniżej M1 target (55%) — wymaga pracy nad kalibracją |
| 3 | **Large files (>1000 LOC)** | 🟡 P3 | daily_agent(1441), analyzer(1454), superbet(1128), cli(1112) |
| 4 | **38 uncommitted changes** | 🔴 P1 | Ryzyko utraty pracy — PILNY COMMIT |
| 5 | **12 DAILY_ANALYSIS docs** | ⚪ P4 | docs/ — archiwizacja zalecana |
| 6 | **Duplicate: validation_errors.csv** | ⚪ P4 | Duplikat w root i data/ — usunąć root |
| 7 | **tests/scratch** | ⚪ P4 | Debug plik — do usunięcia |
| 8 | **data/.fuse_hidden*** | ⚪ P4 | 3 orphan pliki FUSE — do usunięcia |
| 9 | **11x conn.close() bez context manager** | 🟡 P3 | bankroll.py(6), json_export.py(2), coupon_tracker.py(1) |

---

## DEPLOYMENT STATUS

- **Daily Agent**: ✅ OK (logi z 2026-05-25 — ostatni kupon wysłany)
- **Dashboard**: ✅ OK
- **API**: ✅ OK (auth + bankroll przywrócone)
- **Pipeline**: ✅ OK (wymaga commit)
- **Operator**: ✅ OK
- **DB**: ✅ SQLite (dev) + PostgreSQL Neon (prod)
- **Ollama**: ✅ qwen2.5:7b lokalny
- **GUI**: ✅ React/Vite (dist/ zbudowane)

---

## RESOLVED ISSUES (history)

| Problem | Status | Data |
|---------|--------|------|
| 12x file truncation/null bytes | ✅ FIXED | 05-28 |
| 16x requests bez timeout | ✅ FIXED | 05-26 |
| 3x sqlite3 bez context manager | ✅ FIXED | 05-26 |
| Thread safety (response_cache, lambda_optimizer) | ✅ FIXED | 05-26 |
| Phase 9: DB consolidation + login fix | ✅ DONE | 05-27 |
| pyproject.toml version sync (3.0→3.4) | ✅ FIXED | 05-27 |
| sts.py broad except (3x) | ✅ FIXED | 05-27 |
| Cloud Run env vars | ✅ DONE | 05-28 |
| File restore (12 plików) | ✅ DONE | 05-28 |
| asyncio.get_event_loop() deprecated | ✅ FIXED | 05-29 |
| 7x file truncation (05-31) | ✅ FIXED | 05-31 |
| 4x file truncation (06-01) | ✅ FIXED | 06-01 |
