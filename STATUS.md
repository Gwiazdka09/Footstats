# FootStats — Project Status Report

**Last Updated:** 2026-05-30 (auto-audit)  
**Current Version:** v3.4-stable  
**Build Status:** ✅ OK — wszystkie .py kompilują się, brak null bytes  
**System State:** FUNCTIONAL

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Syntax** | ✅ OK | 0 SyntaxError, 0 null bytes |
| **Source Files** | ✅ | ~80 .py modules w src/footstats/ |
| **Tests** | ✅ | 67 test files w tests/ |
| **AI Accuracy** | 🟡 | ~42.4% win rate — poniżej M1 target 55% |
| **Automation** | ✅ | daily_agent.py OK |
| **API** | ✅ | dashboard.py + analyzer.py OK |
| **DB** | ✅ | Neon PG (prod) + SQLite (backtest, 1.1MB) |
| **Cache** | 🟡 | 283MB on disk, 817 plików >30 dni |
| **Timeouts** | ✅ | Wszystkie requests.get/post mają timeout |
| **Thread Safety** | ✅ | Lock w circuit_breaker, response_cache, lambda_optimizer |
| **Disk Bloat** | 🟡 | gui/node_modules 200MB (w .gitignore) |

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
| Stale files cleanup | ✅ DONE | 05-28 |
| Timeout audit (0 remaining) | ✅ DONE | 05-29 |
| asyncio.get_event_loop() deprecated | ✅ FIXED | 05-29 |
| Subprocess audit (fire-and-forget OK) | ✅ DONE | 05-29 |

---

## OTWARTE PROBLEMY

| # | Problem | Priorytet | Szczegóły |
|---|---------|-----------|-----------|
| 1 | **172x `except Exception`** | 🟡 P2 | Zmniejszone z 216, nadal dużo — top: superbet, base_playwright, sts, analyzer |
| 2 | **Accuracy 42.4%** | 🟡 P2 | Poniżej M1 target (55%) — wymaga pracy nad kalibracją |
| 3 | **Large files (>1000 LOC)** | 🟡 P3 | daily_agent(1414), analyzer(1396), superbet(1128), cli(1112) |
| 4 | **38 uncommitted changes** | 🟡 P2 | Wiele zmodyfikowanych plików nie commitowanych |
| 5 | **Cache bloat** | 🟡 P3 | 817 plików cache >30 dni (283MB) — rozważyć auto-eviction |
| 6 | **23 stare pliki logów** | ⚪ P4 | logs/ — stare kupony i raporty |
| 7 | **Zbędne skrypty** | ⚪ P4 | add_logging.py, fix_logging_fstrings.py (jednorazowe) |

---

## DEPLOYMENT STATUS

- **Daily Agent**: ✅ OK
- **Dashboard**: ✅ OK
- **API**: ✅ OK
- **Pipeline**: ✅ OK (wymaga commit)
- **Operator**: ✅ OK
- **DB**: ✅ SQLite (dev) + PostgreSQL Neon (prod)
