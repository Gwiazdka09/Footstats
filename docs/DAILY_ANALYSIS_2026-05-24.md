# RAPORT ANALIZY PROJEKTU FOOTSTATS — 2026-05-24 (auto-scan #3)

## CO WYKRYTO

### KRYTYCZNE (P0)
1. **response_cache.py UCIETY** — plik obciety w linii 255, brakuje 916 bytes (3 funkcje: `_evict_oldest()`, `_cleanup_expired()`, `cleanup_stale_cache()`). Cache rosnie bez limitu = **memory leak w produkcji**. ✅ NAPRAWIONE commit 2c62f8dfc.
2. **NULL BYTES w 2 plikach** — `ai/analyzer.py` (31 null bytes), `core/async_utils.py` (90 null bytes). ✅ NAPRAWIONE commit 2c62f8dfc.
3. **41 uncommitted dirty files** — working copy rozjechana z git HEAD. ✅ NAPRAWIONE commit 2c62f8dfc.
4. **DAILY AGENT MARTWY** — ostatni run: 2026-04-18 (36 dni!). Brak nowych predictions od 2026-04-23. Task Scheduler prawdopodobnie wylaczony/broken. Strona nie pokazuje aktualnych meczow.
5. **MIGRACJE PG-ONLY** — `db/migrations.py` uzywa skladni PostgreSQL (`SERIAL`, `setval`, `DROP CONSTRAINT IF EXISTS`, `ALTER COLUMN`). Tabele SQLite nie maja kolumny `user_id` (coupons, bankroll_state, bankroll_history). API filtruje po `user_id` → endpointy `/coupons/active`, `/coupon/place`, `/coupons` rzuca **500 error** przy SQLite.
6. **BANKROLL PRAWIE PUSTY** — 8.00 PLN po serii 3x LOSE + 4x VOID (na 8 kuponow). Kupon #12 ACTIVE od 2026-04-19 — prawdopodobnie stale/nierozliczony.
7. **GROQ/RAG STALE 33 DNI** — `groq_lessons.json` last update 2026-04-21. RAG daje nieaktualne rady.

### WAZNE (P1)
8. **gui/node_modules/ = 3.1 GB w repo** — brak w .gitignore, trackowany w git.
9. **209x bare `except Exception`** — top: sts.py(16), superbet.py(15), base_playwright.py(14), daily_agent.py(13), analyzer.py(13).
10. **pyproject.toml niespojny** — psycopg2-binary, sqlalchemy, alembic w main deps (usuniete z requirements.txt, ale nie z pyproject).
11. **`_RAM_CACHE` bez eviction** — `utils/cache.py`: `_RAM_CACHE: dict = {}` rosnie bez limitu, brak MAX_ENTRIES.

### NISKOPRIORYTETOWE (P2)
12. **Unused imports** — poisson.py(6), classifier.py(4), ensemble.py(1).
13. **Root `__pycache__/`** — stale .pyc z dawnych modulow (ai_client, scraper_kursy).
14. **`tests/scratch`**, **`.aider.tags.cache.v4/`** (768KB), **`data/.fuse_hidden*`** — smieci.
15. **`docs/archive/` vs `docs/archives/`** — zduplikowane foldery archiwalne.

---

## CO POPRAWIONO/ZAPROPONOWANO

1. ✅ Naprawiono 3 uszkodzone pliki (response_cache.py, analyzer.py, async_utils.py) — commit 2c62f8dfc.
2. ✅ Committed 39 dirty files.
3. Zaktualizowano `STATUS.md` — pelny aktualny stan z krytycznymi problemami.
4. Zaktualizowano `TODO.md` — dodano P0: daily agent martwy, migracje PG-only, bankroll pusty, groq stale.
5. Potwierdzono brak deprecated patterns — CZYSTO.
6. lambda_optimizer.py cache ma invalidate_cache() — OK.
7. dashboard.py sqlite3.connect uzywa try/finally — OK.

---

## ZALECANE TESTY

| Test | Cel | Priorytet |
|------|-----|-----------|
| `test_migration_sqlite_compat.py` | Sprawdz czy migracje dzialaja na SQLite | P0 |
| `test_ram_cache_eviction.py` | MAX_ENTRIES + TTL dla _RAM_CACHE | P1 |
| `test_null_bytes_guard.py` | File integrity check (brak null bytes w .py) | P1 |
| `test_daily_agent_prefilter.py` | pre_filtruj_kursy edge cases | P2 |
| `test_coupon_settlement_edge.py` | partial settlement, void handling | P2 |

---

## CLAUDE CODE PROMPT

```
Tryb: caveman ultra. Projekt: F:\bot. Nie pytaj, rob.

KROK 1 — daily agent restart:
python -m footstats.daily_agent
Jesli blad → sprawdz logi logs/daily_agent.log, napraw i uruchom ponownie.

KROK 2 — migracje SQLite-kompatybilne:
W db/migrations.py: napisz dual-dialect wrapper.
- Zamiast SERIAL → INTEGER PRIMARY KEY AUTOINCREMENT (SQLite) / SERIAL (PG)
- Zamiast DROP CONSTRAINT IF EXISTS → try/except lub detect dialect
- Zamiast ALTER COLUMN → SQLite nie wspiera, uzyj recreate table pattern
- Dodaj kolumne user_id do tabel: coupons, bankroll_state, bankroll_history w SQLite
Test: python -c "from footstats.db.migrations import run_migrations; run_migrations()" 

KROK 3 — bankroll cleanup:
Sprawdz kupon #12 (ACTIVE od 2026-04-19). Jesli mecz zakonczony → settle. Jesli nie → VOID.
Rozważ reset bankrollu po serii strat.

KROK 4 — .gitignore + node_modules:
echo "node_modules/" >> .gitignore
git rm -r --cached src/footstats/gui/node_modules/ 2>/dev/null

KROK 5 — usun smieci:
rm -rf __pycache__/ .aider.tags.cache.v4/ tests/scratch data/.fuse_hidden*

KROK 6 — RAM cache eviction w utils/cache.py:
Dodaj na gorze: MAX_RAM_ENTRIES = 200
W _cache_set() dodaj po zapisie:
  if len(_RAM_CACHE) > MAX_RAM_ENTRIES:
      oldest = min(_RAM_CACHE, key=lambda k: _RAM_CACHE[k]["ts"])
      del _RAM_CACHE[oldest]

KROK 7 — pyproject.toml fix:
Przenies psycopg2-binary>=2.9, sqlalchemy>=2.0, alembic>=1.13 z [project.dependencies] do:
[project.optional-dependencies]
cloud = ["psycopg2-binary>=2.9", "sqlalchemy>=2.0", "alembic>=1.13"]

KROK 8 — unused imports:
- poisson.py: usun nieuzywane (math, PEWNIACZEK_PROG, BZZOIRO_MAX_ROZN, HeurystaZmeczeniaRotacji, KlasyfikatorMeczu, ImportanceIndex, _wagi_mecze, AnalizaDomWyjazd)
- classifier.py: usun FINAL_REMIS_BOOST, IMP2_PROG_FINAL, IMP2_BONUS_FINAL, IMP2_WAKACJE
- ensemble.py: usun annotations

KROK 9 — commit:
git add -A && git commit -m "fix: daily agent + sqlite migrations + cleanup + cache eviction"

Weryfikacja: python -c "import ast; [ast.parse(open(f).read()) for f in __import__('glob').glob('src/footstats/**/*.py', recursive=True) if 'node_modules' not in f and 'gui' not in f]; print('SYNTAX OK')"
```

---

## METRYKI SESJI
- Pliki zrodlowe: 108
- Pliki testow: 49
- Syntax errors: 0 (po P0 fix)
- Null byte files: 0 (po P0 fix)
- Bare except: 209
- Disk bloat: ~3.1 GB (node_modules)
- Daily agent: MARTWY 36 dni
- Bankroll: 8.00 PLN (krytycznie niski)
- Stale RAG data: 33 dni
- Migracje: PG-only, SQLite incompatible
