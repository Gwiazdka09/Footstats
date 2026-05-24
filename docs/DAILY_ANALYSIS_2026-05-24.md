# RAPORT ANALIZY PROJEKTU FOOTSTATS — 2026-05-24

## CO WYKRYTO

### KRYTYCZNE (P0)
1. **response_cache.py UCIETY** — plik obciety w linii 255, brakuje 3 funkcji: `_evict_oldest()`, `_cleanup_expired()`, `cleanup_stale_cache()`. Cache rosnie bez limitu = **memory leak w produkcji**. Git HEAD ma kompletna wersje.
2. **NULL BYTES w 2 plikach** — `ai/analyzer.py` (31 null bytes na koncu), `core/async_utils.py` (90 null bytes). Pliki sa binarne zamiast tekstowych, grep/parsery je pomijaja.
3. **39 uncommitted dirty files** — working copy rozjechana z git HEAD.

### WAZNE (P1)
4. **gui/node_modules/ = 3.1 GB** — w git tracking, gigantyczny bloat. Brak w .gitignore.
5. **209x bare `except Exception`** — top: sts.py(16), superbet.py(15), base_playwright.py(14), daily_agent.py(13). Polykaja bledy bez logowania.
6. **pyproject.toml niespojny z requirements.txt** — psycopg2-binary, sqlalchemy, alembic w main deps zamiast optional (usuniety z requirements.txt, ale nie z pyproject).
7. **`_RAM_CACHE` w cache.py bez eviction** — rosnie bez limitu, brak MAX_ENTRIES.

### NISKOPRIORYTETOWE (P2)
8. **Unused imports** — poisson.py (6 symbolow), classifier.py (4), ensemble.py (1).
9. **Stale docs** — 5x DAILY_ANALYSIS w docs/, archive/archives duplication.
10. **12 starych PDF** w pdf/ (od lutego do marca).

## CO ZAPROPONOWANO

| Zmiana | Priorytet | Estymacja |
|--------|-----------|-----------|
| git checkout 3 uszkodzonych plikow | P0 | 1 min |
| git commit dirty files | P0 | 5 min |
| gui/node_modules → .gitignore + git rm --cached | P1 | 2 min |
| _RAM_CACHE: dodac MAX_ENTRIES=200 + LRU | P1 | 15 min |
| pyproject.toml: deps → optional[cloud] | P1 | 5 min |
| P4.3 bare except: top 5 plikow | P1 | 45 min |
| Unused imports cleanup (poisson, classifier, ensemble) | P2 | 10 min |

## ZALECANE TESTY

| Test | Co pokrywa |
|------|-----------|
| `test_ram_cache_eviction.py` | MAX_ENTRIES, TTL, LRU eviction dla _RAM_CACHE |
| `test_null_bytes_guard.py` | CI check: zadne .py nie zawiera null bytes |
| `test_daily_agent_prefilter.py` | Edge cases pre_filtruj_kursy |
| `test_coupon_settlement_edge.py` | Partial settlement, void handling |
| `test_referee_db_conn_cleanup.py` | SQLite context manager |

## CLAUDE CODE PROMPT (caveman ultra)

```
Tryb: caveman ultra. Zero gadania, sam kod.

P0 FIXES (zrob TERAZ):

1. git checkout HEAD -- src/footstats/core/response_cache.py src/footstats/ai/analyzer.py src/footstats/core/async_utils.py

2. Verify: python -c "import ast; [ast.parse(open(f).read()) for f in ['src/footstats/core/response_cache.py','src/footstats/ai/analyzer.py','src/footstats/core/async_utils.py']]"

3. utils/cache.py — dodaj eviction do _RAM_CACHE:
   - MAX_RAM_ENTRIES = 200
   - W _cache_set(): if len(_RAM_CACHE) >= MAX_RAM_ENTRIES: usun najstarszy po "ts"
   - Dodaj _ram_cache_cleanup(ttl_minutes=60) analogicznie do response_cache

4. pyproject.toml — przeniesc z [dependencies] do [project.optional-dependencies] nowa sekcja:
   cloud = ["psycopg2-binary>=2.9", "sqlalchemy>=2.0", "alembic>=1.13"]
   Usun te 3 z main dependencies.

5. .gitignore — dodaj:
   src/footstats/gui/node_modules/
   __pycache__/
   .aider.tags.cache.v4/
   Potem: git rm -r --cached src/footstats/gui/node_modules/ __pycache__ .aider.tags.cache.v4/ scripts/__pycache__/

6. Unused imports — usun:
   poisson.py: math, PEWNIACZEK_PROG, BZZOIRO_MAX_ROZN, HeurystaZmeczeniaRotacji, KlasyfikatorMeczu, ImportanceIndex, _wagi_mecze, AnalizaDomWyjazd
   classifier.py: FINAL_REMIS_BOOST, IMP2_PROG_FINAL, IMP2_BONUS_FINAL, IMP2_WAKACJE
   ensemble.py: annotations

7. test_ram_cache_eviction.py:
   - test MAX_ENTRIES overflow → oldest evicted
   - test TTL expiry
   - test cache_get miss po expiry

8. git add -A && git commit -m "fix: P0 file corruption + cache eviction + cleanup bloat"

KONIEC. Nie ruszaj nic innego.
```
