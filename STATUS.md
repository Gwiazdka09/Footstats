# FootStats — Project Status Report

**Last Updated:** 2026-05-26 (auto-audit)  
**Current Version:** v3.4-stable  
**Build Status:** ⚠️ 10 plików było obciętych — przywrócono z git HEAD  
**System State:** Production-ready po naprawach

---

## CRITICAL ISSUES STATUS (2026-05-26)

| Problem | Status | Resolution |
|---------|--------|------------|
| 8x src/ pliki obcięte (config, daily_agent, lambda_optimizer, async_utils, response_cache, value_bet, api/main, db/migrations) | ✅ FIXED | Przywrócono z git HEAD (audit 2026-05-26) |
| 2x dodatkowe obcięcia (bankroll, ensemble) | ✅ FIXED | Przywrócono z git HEAD |
| 5x test files obcięte (test_auth, test_coupon_tracker, test_daily_agent_faza, test_evening_agent, test_response_cache) | ✅ FIXED | Przywrócono z git HEAD |
| 16x requests.get/post bez timeout | ✅ FIXED | Dodano timeout=15 do 10 plików (commit 401d25063) |
| 3x sqlite3.connect bez context manager | ✅ FIXED | Zamieniono na with (commit c5e8a22d5) |
| `__pycache__/` w root (2MB, stare .pyc) | ✅ FIXED | 11 dirs usunięte |
| test_file_integrity.py | ✅ NEW | 10/10 pass — sprawdza syntax + min_lines (commit 24b3fc1eb) |
| `data/.fuse_hidden*` pliki (x12) | 🟡 CLEANUP | Orphaned FUSE handles |
| groq_lessons.json | ✅ OK | Zaktualizowany 2026-05-25 |
| git index.lock | 🟡 BLOCKED | Nie można commitować — wymaga ręcznego usunięcia |

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Syntax** | ✅ OK | 0 SyntaxError po przywróceniu (108 modułów) |
| **Source Files** | ✅ | ~108 .py modules w src/footstats/ |
| **Tests** | ✅ | 53 test files w tests/ |
| **Scripts** | ✅ | 13 utility scripts w scripts/ |
| **AI Accuracy** | 🟡 | ~42.4% win rate (14W/19L z 33 kuponów) — poniżej M1 target 55% |
| **Automation** | ✅ | Daily agent + evening agent operational |
| **API** | ✅ | FastAPI 17 endpoints |
| **DB** | ✅ | Neon PG (prod) + SQLite (backtest) |
| **HTTP Timeouts** | ✅ Fixed | timeout=15 dodany do wszystkich requests (commit 401d25063) |
| **SQLite** | ✅ Fixed | context manager w 3 plikach (commit c5e8a22d5) |
| **Thread Safety** | 🟡 | 10x global mutation w production code |
| **Duplicate Functions** | 🟡 | 6x `main`, 3x `zaloguj`, 3x `_zapisz_cache` |

---

## CURRENT FOCUS

**NAPRAWIONE 2026-05-26 (auto-audit):**
1. ✅ 10 plików .py przywróconych z git HEAD (obcięte ogony)
2. ✅ 5 plików testowych przywróconych
3. ✅ Pełna weryfikacja syntax — 0 błędów

**OTWARTE PROBLEMY:**
1. 🟡 **Thread safety** — 10x global mutation bez lock
2. 🟡 **Accuracy 42.4%** — poniżej M1 target (55%)
3. 🟡 **ai/client.py timeout** — zmieniony 120→15, może być za krótki dla wolnych LLM
4. 🟡 **File truncation** — rekurencyjny problem, potrzebny root cause analysis
5. 🟡 **Accuracy 42.4%** — poniżej M1 target (55%)

---

## DEPLOYMENT STATUS

- **Daily Agent**: ✅ Operational (syntax fixed)
- **Dashboard**: ✅ Streamlit live
- **API**: ✅ 17 endpoints (api/main.py fixed)
- **Pipeline**: ✅ run_daily.bat → backup → draft-wait-final → settlement
- **Operator**: ✅ python -m footstats.operator_agent
- **Lambda Optimizer**: ✅ CLI restored
- **DB**: ✅ SQLite (dev) + PostgreSQL Neon (prod)
- **Cache**: ✅ HTTP + RAM with TTL + LRU eviction (MAX_ENTRIES=500)
- **Pre-commit hook**: ✅ py_compile check active
