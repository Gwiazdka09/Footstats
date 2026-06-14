# FootStats — Project Status Report

**Last Updated:** 2026-06-14 (auto-audit)  
**Current Version:** v3.4-stable  
**Build Status:** ✅ 0 SyntaxError w 126 .py src + 73 test files  
**System State:** FUNCTIONAL

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Syntax** | ✅ OK | 0 SyntaxError w 126 .py src + 73 test files |
| **Source Files** | ✅ | 126 .py modules w src/footstats/ |
| **Tests** | ✅ | 73 test files, ~813 test functions |
| **AI Accuracy** | 🟡 | 33% live (12/35 settled, Neon) — Faza 16 accuracy fixes |
| **Automation** | ✅ | daily_agent.py + evening_agent.py OK |
| **API** | ✅ | FastAPI + Sentry + SlowAPI rate limiting + CORS + TimeoutMiddleware |
| **DB** | ✅ | Neon PG (prod) + SQLite (backtest), pool maxconn=10, context managers OK |
| **Timeouts** | ✅ | Wszystkie requests.get/post mają timeout (verified) |
| **Thread Safety** | ✅ | Lock w CB, lambda_opt, response_cache — RLock |
| **Ollama** | ✅ | qwen2.5:7b lokalny + Groq fallback |
| **Security** | ✅ | Brak eval/pickle/os.system; Sentry DSN z env; SQL parametryzowane |
| **Cache** | ✅ | response_cache: MAX_ENTRIES=500, eviction + TTL cleanup OK |
| **RAM Cache** | ✅ | MAX_RAM_ENTRIES=200 z eviction najstarszego wpisu |
| **Scrapers** | ✅ | Playwright context managers OK; circuit breaker na PW+Groq+Ollama |
| **Version Sync** | ✅ | __init__.py=3.4, pyproject.toml=3.4 |

---

## OTWARTE PROBLEMY

| # | Problem | Priorytet | Szczegóły |
|---|---------|-----------|-----------|
| 1 | **Accuracy 33% live** | 🔴 P1 | Poniżej M1 target (55%) — Faza 16 w toku, 35/50 settled |
| 2 | **31 uncommitted changes** | 🔴 P1 | `git status` → 31 modified files niescommitowanych + .git/index.lock (0B) |
| 3 | **cache/form/ = 69MB (274 pliki)** | 🟡 P2 | 70 plików >7 dni — brak automatycznej eviction form cache |
| 4 | **20 core modules bez testów** | 🟡 P4 | TD-31 priorytetowe (bankroll/coupon_settlement/kelly/value_bet/quick_picks) DONE; reszta: bet_builder, classifier, confidence, daily_filters, daily_io, form, fortress, h2h, importance, lambda_optimizer, weekly_picks + inne |
| 5 | **%SystemDrive% — garbage dir** | ⚪ P4 | Folder `%SystemDrive%/ProgramData/Microsoft/Windows/Caches/` (3 pliki) — artefakt Windows FUSE mount |
| 6 | **.fuse_hidden000002b400000001** | ⚪ P4 | Orphan FUSE plik w katalogu głównym |
| 7 | **Langfuse unconditional init** | ⚪ P4 | `analyzer.py:29` — Langfuse() inicjalizowane przy każdym imporcie, nawet bez kluczy API |

---

## DEPLOYMENT STATUS

- **Daily Agent**: ✅ OK (ostatni kupon: 2026-06-13 09:07)
- **Evening Agent**: ✅ OK
- **Dashboard**: ✅ OK (Streamlit)
- **API**: ✅ OK (FastAPI + auth + Sentry + rate limiting + timeout 10s)
- **Pipeline**: ✅ OK (run_daily.bat z backup+syntax+eviction)
- **Operator**: ✅ OK
- **DB**: ✅ SQLite (dev) + PostgreSQL Neon (prod)
- **Ollama**: ✅ qwen2.5:7b lokalny
- **GUI**: ✅ React/Vite (dist/ zbudowane, node_modules 3.1GB)

---

## RESOLVED ISSUES (history)

| Problem | Status | Data |
|---------|--------|------|
| TD-31 — bankroll.py bez testów (24 core modules bez testów) — dodano tests/test_bankroll.py (8 testów, sqlite fixture); coupon_settlement/kelly/value_bet/quick_picks już pokryte (60 testów) | ✅ FIXED | 06-14 |
| Panel administratora — przycisk "Sprawdź wyniki meczów" (POST /coupons/settle) w Settings, widoczny tylko dla admina (JWT `adm` claim) | ✅ DODANE | 06-14 |
| Przypadkowy zapis śmieciowych wierszy (id 118-129) do prod Neon coupons (bug w tests/test_bankroll.py — niezałatany import `_connect`) — wiersze usunięte, test naprawiony (`br._connect()`) | ✅ FIXED | 06-14 |
| daily_agent — kupony z halucynowanymi kursami Groq (np. 52.58/EV+799% identyczne na 5 meczach) gdy Bzzoiro nie ma kursu dla danego typu — leg teraz USUWANY jeśli kurs niezweryfikowany (TD-38) | ✅ FIXED | 06-14 |
| bzzoiro.py — `waliduj()` bez retry, 1x timeout=15s → pipeline exit=1, brak kuponów na dzień (TD-38 root cause) — dodano retry z backoff (3x) | ✅ FIXED | 06-14 |
| coupon_settlement — kupony ACTIVE ze starymi legami (friendly/niskie ligi bez wyniku z API) wisiały na zawsze, blokowały "50 settled" (TD-37) — po 10d bez wyniku → status VOID | ✅ FIXED | 06-14 |
| kupony #113-115 (06-13) — DRAFT bez stake (final phase padła), nigdy promowane → oznaczone VOID (TD-39) | ✅ FIXED | 06-14 |
| 5x file truncation (daily_agent, poisson, coupon_settlement, results_updater, zawodtyper_referees) | ✅ RESTORED z git | 06-13 |
| orphan files (.fuse_hidden, db-wal 0B) + stary cache/logi | ✅ WYCZYSZCZONE | 06-13 |
| zawodtyper_referees.py — off-by-one kolumn (avg_yellow/avg_red z K/Z.K. zamiast Z.K./CZ.K.) | ✅ FIXED | 06-12 |
| FAZA 16.3 draw bias — p_remis>50% dla niskich lambd (FINAL_REMIS_BOOST overshoot) | ✅ FIXED — sufit 40% w poisson.py | 06-12 |
| LICENSE — MIT → All Rights Reserved (portfolio/CV) | ✅ ZMIENIONE | 06-12 |
| settle_active_coupons — testowe kupony (match_date 2099) sprawdzane co run (TD23) | ✅ FIXED | 06-12 |
| coupon_settlement — stale FlashScore cache + zła kolejność źródeł wyniku | ✅ FIXED | 06-12 |
| results_updater — fixtures po dacie + timeline zdarzeń (gole/kartki) w match_stats | ✅ DODANE | 06-12 |
| cache/ eviction — 1150 plików >7d usunięte (TD25) | ✅ FIXED — 7.6MB zwolnione | 06-12 |
| Strefa Inspiracji (15.7) + BetBuilder homepage (15.8) — wpięte do daily_agent (`--bb`) | ✅ DODANE | 06-12 |
| 27 uncommitted changes | ✅ Committed+pushed (TD24) | 06-12 |
| Daily pipeline stał 5 dni (06-06→06-11) | ✅ FIXED | 06-11 |
| ai_feedback FK violation | ✅ FIXED | 06-11 |
| 5x file truncation (response_cache, base, coupons, daily_agent, evening_agent) | ✅ RESTORED | 06-11 |
| 26x file truncation + 4x null bytes | ✅ FIXED | 06-07 |
| 160→25 broad except | ✅ Reduced | 06-07 |
