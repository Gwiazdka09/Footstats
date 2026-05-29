# FootStats — Project Status Report

**Last Updated:** 2026-05-29 (auto-audit)  
**Current Version:** v3.4-stable  
**Build Status:** ✅ OK — wszystkie .py kompilują się, brak null bytes  
**System State:** FUNCTIONAL (po restore z git 05-28)

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Syntax** | ✅ OK | 0 SyntaxError, 0 null bytes |
| **Source Files** | ✅ | ~80 .py modules w src/footstats/ |
| **Tests** | ✅ | 67 test files w tests/ |
| **AI Accuracy** | 🟡 | ~42.4% win rate — poniżej M1 target 55% |
| **Automation** | ✅ | daily_agent.py kompiluje się |
| **API** | ✅ | dashboard.py + analyzer.py OK |
| **DB** | ✅ | Neon PG (prod) + SQLite (backtest) |
| **Cache** | ✅ | 283MB on disk |
| **Disk Bloat** | 🟡 | gui/node_modules 200MB (w .gitignore, nie w git) |

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

---

## OTWARTE PROBLEMY

| # | Problem | Priorytet | Szczegóły |
|---|---------|-----------|-----------|
| 1 | **17x requests.get/post bez timeout** | 🔴 P1 | coupon_settlement, source_manager, api_football, lineup_scraper, bzzoiro, enriched, results_updater |
| 2 | **216x `except Exception`** | 🟡 P2 | Top: superbet(15), base_playwright(14), sts(13), analyzer(13), cli(10) |
| 3 | **5x subprocess.Popen bez cleanup** | 🟡 P2 | backtest, post_match_analyzer, cli, evening_agent, daily_agent |
| 4 | **Accuracy 42.4%** | 🟡 P2 | Poniżej M1 target (55%) |
| 5 | **Large files (>1000 LOC)** | 🟡 P3 | daily_agent(1414), analyzer(1393), superbet(1128), cli(1112) |
| 6 | **36 uncommitted changes** | 🟡 P2 | Wiele zmodyfikowanych plików nie commitowanych |
| 7 | **asyncio.get_event_loop() deprecated** | 🟡 P3 | async_utils.py:56 |

---

## DEPLOYMENT STATUS

- **Daily Agent**: ✅ OK
- **Dashboard**: ✅ OK
- **API**: ✅ OK
- **Pipeline**: ✅ OK (wymaga commit)
- **Operator**: ✅ OK
- **DB**: ✅ SQLite (dev) + PostgreSQL Neon (prod)
