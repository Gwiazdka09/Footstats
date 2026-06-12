# FootStats — Project Status Report

**Last Updated:** 2026-06-12 (auto-audit)  
**Current Version:** v3.4-stable  
**Build Status:** ✅ STABLE — 0 SyntaxError, git clean  
**System State:** FUNCTIONAL

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Syntax** | ✅ OK | 0 SyntaxError w 126 .py src + 73 test files |
| **Source Files** | ✅ | 126 .py modules w src/footstats/ |
| **Tests** | ✅ | 73 test files, 813 test functions |
| **AI Accuracy** | 🟡 | 33% live (12/35 settled, Neon) — Faza 16 accuracy fixes |
| **Automation** | ✅ | daily_agent.py + evening_agent.py OK |
| **API** | ✅ | FastAPI + Sentry + SlowAPI rate limiting + CORS + TimeoutMiddleware |
| **DB** | ✅ | Neon PG (prod) + SQLite (backtest), pool maxconn=10, context managers OK |
| **Timeouts** | ✅ | Wszystkie requests.get/post mają timeout (verified) |
| **Thread Safety** | ✅ | Lock w CB, lambda_opt, response_cache — RLock |
| **Ollama** | ✅ | qwen2.5:7b lokalny + Groq fallback |
| **Security** | ✅ | Brak eval/pickle/os.system; Sentry DSN z env |
| **Cache** | ✅ | response_cache: MAX_ENTRIES=500, eviction + TTL cleanup OK |
| **Scrapers** | ✅ | Playwright context managers OK; circuit breaker na PW+Groq+Ollama |
| **Version Sync** | ✅ | __init__.py=3.4, pyproject.toml=3.4 |

---

## OTWARTE PROBLEMY

| # | Problem | Priorytet | Szczegóły |
|---|---------|-----------|-----------|
| 1 | **Accuracy 33% live** | 🔴 P1 | Poniżej M1 target (55%) — Faza 16 w toku, 35/50 settled |
| 2 | **Draw bias w kuponach** | 🔴 P1 | Kupony 06-11: 4x single-leg draw @1.92 z identycznym reasoning — model faworyzuje remisy |
| 3 | **Large files (>1000 LOC)** | ⚪ P4 | daily_agent(~1430), superbet(1128), cli(1112) |
| 4 | **orphan files** | ⚪ P4 | .fuse_hidden*, data/footstats.db-wal (0 bytes) |

---

## DEPLOYMENT STATUS

- **Daily Agent**: ✅ OK (ostatni kupon: 2026-06-11 23:23)
- **Evening Agent**: ✅ OK
- **Dashboard**: ✅ OK (Streamlit)
- **API**: ✅ OK (FastAPI + auth + Sentry + rate limiting + timeout 10s)
- **Pipeline**: ✅ OK (run_daily.bat z backup+syntax+eviction)
- **Operator**: ✅ OK
- **DB**: ✅ SQLite (dev) + PostgreSQL Neon (prod)
- **Ollama**: ✅ qwen2.5:7b lokalny
- **GUI**: ✅ React/Vite (dist/ zbudowane)

---

## RESOLVED ISSUES (history)

| Problem | Status | Data |
|---------|--------|------|
| zawodtyper_referees.py — off-by-one kolumn (avg_yellow/avg_red z K/Z.K. zamiast Z.K./CZ.K.) | ✅ FIXED | 06-12 |
| FAZA 16.3 draw bias — p_remis>50% dla niskich lambd (FINAL_REMIS_BOOST overshoot) | ✅ FIXED — sufit 40% w poisson.py | 06-12 |
| LICENSE — MIT → All Rights Reserved (portfolio/CV) | ✅ ZMIENIONE | 06-12 |
| settle_active_coupons — testowe kupony (match_date 2099) sprawdzane co run (TD23) | ✅ FIXED — `WHERE match_date_first <= today` | 06-12 |
| coupon_settlement — stale FlashScore cache + zła kolejność źródeł wyniku | ✅ FIXED | 06-12 |
| results_updater — fixtures po dacie (Źródło 0, wszystkie ligi) + timeline zdarzeń (gole/kartki) w match_stats | ✅ DODANE | 06-12 |
| cache/ eviction — 1150 plików >7d usunięte (TD25) | ✅ FIXED — 7.6MB zwolnione | 06-12 |
| Strefa Inspiracji (15.7) + BetBuilder homepage (15.8) — wpięte do daily_agent (`--bb`) | ✅ DODANE | 06-12 |
| 27 uncommitted changes | ✅ Committed+pushed (TD24) | 06-12 |
| Daily pipeline stał 5 dni (06-06→06-11) | ✅ FIXED — 21 śmieciowych kuponów usunięte + 3 bugi | 06-11 |
| ai_feedback FK violation | ✅ FIXED — per-leg lookup po match_date+drużyny | 06-11 |
| system_coupons.py — psycopg2 LIKE escaping bug | ✅ FIXED | 06-11 |
| rag.py — row[0] zamiast row["col"] (RealDictCursor) | ✅ FIXED | 06-11 |
| xg_lambda.py — martwy kod | ✅ Usunięty | 06-11 |
| 5x file truncation (response_cache, base, coupons, daily_agent, evening_agent) | ✅ RESTORED | 06-11 |
| cache/ eviction policy (evict_cache.py w run_daily.bat) | ✅ FIXED | 06-11 |
| 45 uncommitted changes + .git/index.lock | ✅ Committed+pushed | 06-11 |
| 26x file truncation + 4x null bytes | ✅ FIXED | 06-07 |
| 160→25 broad except | ✅ Reduced | 06-07 |
| Timeout audit (all requests covered) | ✅ Verified | 06-10 |
| Security audit (no eval/pickle/os.system) | ✅ Verified | 06-10 |
