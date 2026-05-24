# FootStats — Project Status Report

**Last Updated:** 2026-05-24 (auto-scan #3)  
**Current Version:** v3.4-stable  
**Build Status:** ⚠️ 3 uszkodzone pliki w working copy (syntax/null bytes)  
**System State:** Production — wymaga napraw przed deployem

---

## KRYTYCZNE PROBLEMY (stan 2026-05-24)

| Problem | Severity | Plik |
|---------|----------|------|
| `response_cache.py` uciety — brak 3 funkcji eviction (916 bytes brakuje) | 🔴 KRYTYCZNY | `core/response_cache.py` (linia 255 urwana) |
| NULL bytes na koncu pliku | 🔴 KRYTYCZNY | `ai/analyzer.py` (31 null bytes), `core/async_utils.py` (90 null bytes) |
| `pyproject.toml` ma dead deps (psycopg2, sqlalchemy, alembic w main deps) | 🟠 Medium | `pyproject.toml` |
| `_RAM_CACHE` brak eviction/max size | 🟠 Medium | `utils/cache.py` |
| 209x `except Exception` (bare) | 🟠 Medium | top: sts.py(16), superbet.py(15), base_playwright.py(14) |
| `gui/node_modules/` = 3.1 GB w repo, brak w .gitignore | 🟠 Medium | `src/footstats/gui/node_modules/` |
| groq_lessons.json stale (last update: 2026-04-21, 33 dni!) | 🟡 Low | `data/groq_lessons.json` |
| root `__pycache__/` z starymi modolami (ai_client, scraper_kursy) | 🟡 Low | `__pycache__/` |
| `tests/scratch` — plik-smieci | 🟡 Low | `tests/scratch` |
| 41 uncommitted dirty files (39 modified + 2 untracked) | 🟡 Low | `git status` |

---

## RECENT MILESTONES

### Phase 4 Cleanup Sprint — PARTIALLY COMPLETE
- **P4.1** Version sync ✅
- **P4.2** SQLite context managers ✅
- **P4.3** Exception Handling 🔴 PENDING (209x bare except)
- **P4.4** Cache cleanup ✅
- **P4.5** Root cleanup ✅
- **P4.6** Partial imports cleanup ✅ (poisson.py, classifier.py, ensemble.py do zrobienia)
- **P4.7** Dead deps removed from requirements.txt ✅ (ale pyproject.toml niespojne!)
- **P4.8** Response cache eviction ✅ w git, ale ⚠️ WORKING COPY USZKODZONA
- **P4.9** Analyzer.py duplikat import ✅
- **P4.10** Async_utils.py deprecation fix ✅ w git, ale ⚠️ NULL BYTES w working copy

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Syntax** | ⚠️ 1 error | response_cache.py uciety, 2 pliki z null bytes |
| **Source Files** | ✅ | 108 .py modules |
| **Tests** | ✅ Solid | 49 test files |
| **AI Accuracy** | ✅ Stable | ~75% on 75%+ confidence |
| **Automation** | ✅ Full | Zero-touch daily loop |
| **API Cache** | ⚠️ Broken | response_cache eviction functions MISSING w working copy |
| **DB** | ✅ OK | Neon PG (prod) + SQLite (backtest) |
| **Disk** | ⚠️ Bloat | gui/node_modules 3.1GB, aider cache 768KB |
| **Git** | ⚠️ Dirty | 41 uncommitted changes |
| **RAG/Groq** | ⚠️ Stale | Lessons not updated 33 days |

---

## CURRENT FOCUS

**NATYCHMIAST (P0):**
1. Naprawic response_cache.py (`git checkout HEAD -- src/footstats/core/response_cache.py`)
2. Usunac null bytes z analyzer.py i async_utils.py (`git checkout HEAD --` obu plikow)
3. Commit dirty files lub git stash

**NASTEPNA SESJA (P1):**
1. Dodac `node_modules/` do .gitignore + `git rm -r --cached src/footstats/gui/node_modules/`
2. P4.3 Exception handling — top 5 plikow
3. Dodac eviction do `_RAM_CACHE` w cache.py
4. Poprawic pyproject.toml — psycopg2/sqlalchemy/alembic do [optional] cloud
5. Usunac root `__pycache__/`, `tests/scratch`, `.aider.tags.cache.v4/`

**PHASE 5 (P2):**
1. checkpoint.py → daily_agent
2. Prometheus metrics
3. SofaScore injury scraper
4. Uaktualnic groq_lessons.json (33 dni stale!)

---

## DEPLOYMENT LOGS
- **Daily Agent**: Task Scheduler, stable (last run 2026-04-18)
- **Dashboard**: Streamlit live
- **API**: 17 endpoints, response_cache na 5 (⚠️ eviction broken)
- **Pipeline**: run_daily.bat → backup → draft-wait-final → settlement
- **Operator**: python -m footstats.operator_agent
