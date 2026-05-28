# FootStats — Project Status Report

**Last Updated:** 2026-05-28 (auto-audit)  
**Current Version:** v3.4-stable  
**Build Status:** 🔴 BROKEN — 12 plików z SyntaxError/null bytes (truncation)  
**System State:** NON-FUNCTIONAL (wymaga restore z git)

---

## CRITICAL ISSUES STATUS (2026-05-28)

| Problem | Status | Resolution |
|---------|--------|------------|
| **12x FILE TRUNCATION/NULL BYTES** | 🔴 CRITICAL | Pliki obcięte na dysku, git HEAD OK — wymaga `git checkout HEAD -- <pliki>` |
| File truncation (rekurencyjny) | 🔴 REGRESJA (05-28) | Ponowne obcięcie 12 plików! Pre-commit hook nie zapobiega |
| 16x requests bez timeout | ✅ FIXED (05-26) | timeout=15 |
| 3x sqlite3 bez context manager | ✅ FIXED (05-26) | with statement |
| Thread safety (8.4) | ✅ FIXED (05-26) | response_cache + lambda_optimizer |
| Phase 9: DB consolidation + login fix | ✅ DONE (05-27) | seed_admin, cache consolidation, timeout 60s |
| `pyproject.toml` version sync | ✅ FIXED | 3.0 → 3.4 |
| sts.py broad except | ✅ FIXED | 3x zamienione |
| `CLAUDE_CODE_PROMPT_PHASE9.md` — stale | 🟡 CLEANUP | Phase 9 zakończona, plik niepotrzebny |
| `validation_errors.csv` — stale | 🟡 CLEANUP | Plik testowy, do usunięcia |
| `.aider.tags.cache.v4` — 768K orphan | 🟡 CLEANUP | Cache Aidera, nieużywany |
| `gui/node_modules/` — 3.1GB! | 🟡 BLOAT | Nie w .gitignore, ogromny rozmiar |
| 233x `except Exception` (remaining) | 🟡 TECH DEBT | Top: sts(13), cli(10), logging(8) |

---

## BROKEN FILES (2026-05-28)

### Truncated (obcięte — mniej linii niż git HEAD):
| Plik | Disk | Git HEAD | Typ błędu |
|------|------|----------|-----------|
| daily_agent.py | 1381 | 1414 | unterminated string |
| analyzer.py | 1377 | 1393 | unterminated triple-quote |
| poisson.py | 241 | 267 | unclosed `{` |
| backtest.py | 583 | 589 | unterminated string |
| superbet.py | 1115 | 1128 | unterminated f-string |
| base_playwright.py | 307 | 317 | unclosed `(` |
| superbet_bb.py | 290 | 292 | unclosed `[` |
| scrapers/__init__.py | 18 | ? | unterminated string |

### Null byte corruption:
| Plik | Null bytes |
|------|-----------|
| dashboard.py | 466 |
| ensemble_optimizer.py | 119 |
| probability_calibrator.py | 99 |
| post_match_analyzer.py | 2 |

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Syntax** | 🔴 BROKEN | 12 SyntaxError (truncation + null bytes) |
| **Source Files** | ✅ | ~80 .py modules w src/footstats/ |
| **Tests** | ✅ | 63 test files w tests/ |
| **AI Accuracy** | 🟡 | ~42.4% win rate — poniżej M1 target 55% |
| **Automation** | 🔴 | BROKEN — daily_agent.py nie kompiluje się |
| **API** | 🔴 | BROKEN — dashboard.py + analyzer.py nie kompilują się |
| **DB** | ✅ | Neon PG (prod) + SQLite (backtest), context managers OK |
| **Cache** | ✅ | 283MB on disk |
| **Disk Bloat** | 🟡 | gui/node_modules 3.1GB, cache 283MB |

---

## CURRENT FOCUS

**PRIORYTET #1: RESTORE 12 PLIKÓW Z GIT HEAD**

```bash
git checkout HEAD -- \
  src/footstats/daily_agent.py \
  src/footstats/ai/analyzer.py \
  src/footstats/ai/post_match_analyzer.py \
  src/footstats/core/poisson.py \
  src/footstats/core/backtest.py \
  src/footstats/core/probability_calibrator.py \
  src/footstats/core/ensemble_optimizer.py \
  src/footstats/scrapers/superbet.py \
  src/footstats/scrapers/base_playwright.py \
  src/footstats/scrapers/superbet_bb.py \
  src/footstats/scrapers/__init__.py \
  src/footstats/dashboard.py
```

**OTWARTE PROBLEMY:**
1. 🔴 **12 broken files** — CRITICAL, system non-functional
2. 🔴 **Accuracy 42.4%** — poniżej M1 target (55%)
3. 🟡 **gui/node_modules 3.1GB** — dodać do .gitignore
4. 🟡 **Broad except ~233x** — tech debt
5. 🟡 **Stale files** — CLAUDE_CODE_PROMPT_PHASE9.md, validation_errors.csv, .aider.tags.cache.v4

---

## DEPLOYMENT STATUS

- **Daily Agent**: 🔴 BROKEN (daily_agent.py truncated)
- **Dashboard**: 🔴 BROKEN (dashboard.py null bytes)
- **API**: 🟡 Partially broken (analyzer.py, poisson.py)
- **Pipeline**: 🔴 BROKEN
- **Operator**: ✅ operator_agent.py OK
- **DB**: ✅ SQLite (dev) + PostgreSQL Neon (prod)
- **Cache**: ✅ 283MB on disk
