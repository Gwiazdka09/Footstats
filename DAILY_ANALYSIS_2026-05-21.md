# FootStats Daily Analysis — 2026-05-21

## Co wykryto

1. **VERSION mismatch** — config.py ma "v3.2", CLAUDE.md ma "v3.3", powinno byc "v3.4-stable". Nie wplywana na dzialanie ale myli userow.
2. **216x `except Exception`** — szerokie lapanie bledow, czesto bez logowania. Top 5: sts.py(16), superbet.py(15), base_playwright.py(14), daily_agent.py(13), analyzer.py(13).
3. **75x unused imports** — martwy kod w 30+ plikach. Np. `datetime` w fatigue.py, classifier.py, form.py; `Panel`/`VERSION` w data_fetcher.py.
4. **SQLite try/finally** — referee_db.py(3x) i dashboard.py(1x) uzywaja try/finally zamiast `with`. Dziala, ale nieidomatyczne.
5. **checkpoint.py nie wpiety** — modul gotowy, ale daily_agent.py go nie importuje.
6. **Dead dependencies** — psycopg2-binary, sqlalchemy, alembic w requirements.txt ale Postgres nigdzie nieuzywany.
7. **Root clutter** — 10+ plikow .md/.py/.csv w root ktore powinny byc w scripts/, docs/, data/.
8. **response_cache.py** — JEST juz wpiety (5 endpointow). STATUS.md i TODO.md mylnie mowily ze nie.

## Co poprawiono (Cursor audit)

1. **STATUS.md** — zaktualizowany na 2026-05-21, poprawione metryki (45 test files nie 47, cache 6.3MB nie 263MB, response_cache wired).
2. **TODO.md** — zaktualizowany: P4.4 Cache marked RESOLVED, P5.1 response_cache marked DONE, dodano P4.6 (unused imports) i P4.7 (dead deps).

## Postęp Claude Code (sesja 2026-05-21)

| TASK | Opis | Status | Commit |
|------|------|--------|--------|
| 1 | Version sync (config.py, CLAUDE.md) | ✅ Done | `0e681773` |
| 2 | SQLite `with` (referee_db, dashboard) | ✅ Done | `b8892025` |
| 3 | Unused imports (cli, data_fetcher, form) | ⚠️ Częściowo | `59dd2c45` — fatigue.py, classifier.py bez zmian |
| 4 | Dead deps (requirements.txt) | ✅ W pliku | commit w tym PR — sesja zatrzymana na limicie usage (~16:00 Warsaw) |
| 5 | Root cleanup (mv do scripts/docs/data) | ❌ Nie ruszone | — |

**Blokada:** Claude Code — "out of extra usage", reset 16:00 Europe/Warsaw. Kolejny krok: commit TASK 4 + docs, potem TASK 5.

## Zalecane testy

1. `test_version_consistency.py` — sprawdz ze config.VERSION == CLAUDE.md == STATUS.md.
2. `test_referee_db_conn_cleanup.py` — sprawdz ze conn jest zamykany nawet przy exception.
3. `test_unused_imports_lint.py` — flake8 --select=F401 na calym src/.
4. `test_checkpoint_integration.py` — test ze daily_agent poprawnie checkpointuje miedzy krokami.

## Claude Code Prompt (pozostale)

```
Tryb: caveman ultra. Bez pytan, czyste zmiany.

TASK 3b — Unused imports (pozostale z top 5):
- src/footstats/core/fatigue.py: usun datetime jesli nieuzywane
- src/footstats/core/classifier.py: usun datetime, timedelta jesli nieuzywane
Weryfikuj grepem przed usunieciem!

TASK 5 — Root cleanup:
- mv check_settlement*.py scripts/
- mkdir -p docs/archive
- mv PHASE3_SPEC.md PHASE4_SPEC.md docs/archive/
- mv PROJECT_STATE.md DAILY_ANALYSIS_*.md maintenance_prompt.md docs/
- mv validation_errors.csv data/
- mv BETA_LAUNCH.md docs/

Po kazdym TASK: git add + commit z opisem.
```
