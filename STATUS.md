# FootStats — Project Status Report

**Last Updated:** 2026-06-10 (auto-audit)  
**Current Version:** v3.4-stable  
**Build Status:** ✅ OK — 0 SyntaxError (ast.parse), 0 null bytes  
**System State:** FUNCTIONAL

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Syntax** | ✅ OK | 0 SyntaxError w 194 .py (122 src + 72 tests) |
| **Source Files** | ✅ | 122 .py modules w src/footstats/ |
| **Tests** | ✅ | 70 test files |
| **AI Accuracy** | 🟡 | 26.7% live (15 kuponów Neon) — Faza 16 accuracy fixes |
| **Automation** | ✅ | daily_agent.py + evening_agent.py OK |
| **API** | ✅ | FastAPI + Sentry + SlowAPI rate limiting + CORS |
| **DB** | ✅ | Neon PG (prod) + SQLite (backtest), pool maxconn=10 |
| **Timeouts** | ✅ | Wszystkie requests.get/post mają timeout=15 |
| **Thread Safety** | 🟡 | Lock w CB, lambda_opt OK; response_cache sync_wrapper brak locka na odczycie |
| **Ollama** | ✅ | qwen2.5:7b lokalny + Groq fallback |
| **Security** | ✅ | Brak eval/pickle/os.system; Sentry DSN z env |
| **Cache** | ✅ | response_cache: MAX_ENTRIES=500, eviction + TTL cleanup OK |
| **Scrapers** | ✅ | Playwright context managers OK; circuit breaker na PW+Groq+Ollama |

---

## OTWARTE PROBLEMY

| # | Problem | Priorytet | Szczegóły |
|---|---------|-----------|-----------|
| 1 | **Accuracy 26.7% live** | 🔴 P1 | Poniżej M1 target (55%) — Faza 16 w toku, czekamy na 50 settled |
| 2 | **29 uncommitted changes** | 🔴 P1 | Ryzyko utraty pracy — PILNY COMMIT + PUSH |
| 3 | **response_cache sync_wrapper race** | 🟡 P2 | Odczyt cache bez `_CACHE_LOCK` w sync_wrapper (linia 171) |
| 4 | **base.py recursive retry bez limitu** | 🟡 P2 | `_http_get` na 429 wywołuje siebie rekurencyjnie — brak max depth |
| 5 | **Large files (>1000 LOC)** | 🟡 P3 | daily_agent(1345), superbet(1128), cli(1112) |
| 6 | **5x subprocess.Popen fire-and-forget** | ⚪ P4 | evening_agent, cli, daily_agent, backtest, post_match — OK dla notyfikacji |
| 7 | **cache/ 353MB** | ⚪ P4 | Rozważ eviction policy lub max age |

---

## DEPLOYMENT STATUS

- **Daily Agent**: ✅ OK
- **Evening Agent**: ✅ OK
- **Dashboard**: ✅ OK (Streamlit)
- **API**: ✅ OK (FastAPI + auth + Sentry + rate limiting)
- **Pipeline**: ✅ OK (wymaga commit)
- **Operator**: ✅ OK
- **DB**: ✅ SQLite (dev) + PostgreSQL Neon (prod)
- **Ollama**: ✅ qwen2.5:7b lokalny
- **GUI**: ✅ React/Vite (dist/ zbudowane)

---

## RESOLVED ISSUES (history)

| Problem | Status | Data |
|---------|--------|------|
| 26x file truncation + 4x null bytes | ✅ FIXED | 06-07 |
| .gitignore: footstats.log + validation_errors.csv | ✅ FIXED | 06-07 |
| 12x file truncation/null bytes | ✅ FIXED | 05-28 |
| 16x requests bez timeout | ✅ FIXED | 05-26 |
| 3x sqlite3 bez context manager | ✅ FIXED | 05-26 |
| Thread safety (response_cache, lambda_optimizer) | ✅ FIXED | 05-26 |
| Phase 9: DB consolidation + login fix | ✅ DONE | 05-27 |
| pyproject.toml version sync (3.0→3.4) | ✅ FIXED | 05-27 |
| sts.py broad except (3x) | ✅ FIXED | 05-27 |
| Cloud Run env vars | ✅ DONE | 05-28 |
| asyncio.get_event_loop() deprecated | ✅ FIXED | 05-29 |
| 7x file truncation (05-31) | ✅ FIXED | 05-31 |
| 4x file truncation (06-01) | ✅ FIXED | 06-01 |
| 160→78→67→25 broad except | ✅ Reduced | 06-07 |
| tests/scratch + data/.fuse_hidden | ✅ Cleaned | 06-03 |
| Timeout audit (all requests covered) | ✅ Verified | 06-06 |
| DB connections (all use context manager) | ✅ Verified | 06-06 |
| Cache eviction (MAX_ENTRIES + TTL) | ✅ Verified | 06-06 |
| smoke_api.py testpass → env var | ✅ FIXED | 06-08 |
| Syntax + null bytes audit (193/193 OK) | ✅ Verified | 06-08 |
| DB connections (context mgr) | ✅ Verified | 06-08 |
| Timeout audit (requests.get/post) | ✅ Verified | 06-08 |
| __init__.py version 2.7→3.4 | ✅ FIXED | 06-08 |
| Syntax audit (194/194 OK, 122 src + 72 tests) | ✅ Verified | 06-09 |
| Security audit (no eval/pickle/os.system/hardcoded secrets) | ✅ Verified | 06-09 |
| No TODO/FIXME/HACK in src/ | ✅ Verified | 06-09 |
| DB pool (context mgr + putconn) | ✅ Verified | 06-09 |
| Cache bounds (MAX_ENTRIES=500, TTL, eviction) | ✅ Verified | 06-09 |
| Circuit breaker (thread-safe, 3 states) | ✅ Verified | 06-09 |
| Playwright scrapers (context managers for browser+page) | ✅ Verified | 06-09 |
| .fuse_hidden + empty WAL cleaned | ✅ Cleaned | 06-10 |
| DAILY_REPORT_2026-06-09.md → archive | ✅ Moved | 06-10 |
| brain_graph.html → .gitignore | ✅ Added | 06-10 |
| docs/PROJECT_STATE.md updated to v3.4 | ✅ Verified | 06-10 |
| Timeout audit (all requests have timeout=15) | ✅ Verified | 06-10 |
| Security audit (no eval/pickle/os.system) | ✅ Verified | 06-10 |
| No TODO/FIXME/HACK in src/ | ✅ Verified | 06-10 |
