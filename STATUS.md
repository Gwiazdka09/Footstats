# FootStats — Project Status Report

**Last Updated:** 2026-05-31 (auto-audit)  
**Current Version:** v3.4-stable  
**Build Status:** ✅ OK — 7 truncated plików przywrócone, 0 SyntaxError  
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
| **DB** | ✅ | Neon PG (prod) + SQLite (backtest) |
| **Timeouts** | ✅ | Wszystkie requests.get/post mają timeout |
| **Thread Safety** | ✅ | Lock w circuit_breaker, response_cache, lambda_optimizer |
| **Ollama** | ✅ | qwen2.5:7b lokalny + Groq fallback |

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
| **7x file truncation (quick_picks, response_cache, bankroll, coupons, auth, main, migrations)** | ✅ FIXED | 05-31 |

---

## OTWARTE PROBLEMY

| # | Problem | Priorytet | Szczegóły |
|---|---------|-----------|-----------|
| 1 | **174x `except Exception`** | 🟡 P2 | Top: base_playwright(14), sts(13), daily_agent(8), logging(7), historical_loader(7) |
| 2 | **Accuracy 42.4%** | 🟡 P2 | Poniżej M1 target (55%) — wymaga pracy nad kalibracją |
| 3 | **Large files (>1000 LOC)** | 🟡 P3 | daily_agent(1414), analyzer(1396), superbet(1128), cli(1112) |
| 4 | **50 uncommitted changes** | 🔴 P1 | Wzrost z 38→50 — ryzyko utraty pracy |
| 5 | **25 starych logów** | ⚪ P4 | logs/ — stare kupony i raporty |
| 6 | **Zbędne skrypty** | ⚪ P4 | add_logging.py, fix_logging_fstrings.py (jednorazowe) |
| 7 | **10 DAILY_ANALYSIS docs** | ⚪ P4 | docs/ — rozważyć archiwizację |

---

## DEPLOYMENT STATUS

- **Daily Agent**: ✅ OK
- **Dashboard**: ✅ OK
- **API**: ✅ OK (auth.py + bankroll.py przywrócone)
- **Pipeline**: ✅ OK (wymaga commit)
- **Operator**: ✅ OK
- **DB**: ✅ SQLite (dev) + PostgreSQL Neon (prod)
- **Ollama**: ✅ qwen2.5:7b lokalny
