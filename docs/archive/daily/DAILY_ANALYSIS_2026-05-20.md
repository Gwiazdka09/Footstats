# FootStats Daily Analysis — 2026-05-20

## Co wykryto

1. **VERSION mismatch (3 pliki)**: config.py="v3.2", CLAUDE.md="v3.3", STATUS.md="v3.4" — niespojne wersjonowanie
2. **216x `except Exception`** bez logowania — top offenders: sts.py(16), superbet.py(15), base_playwright.py(14), daily_agent.py(13), analyzer.py(13)
3. **SQLite connection leaks**: referee_db.py (3x raw conn), dashboard.py (1x) — brak context managera, potencjalny leak przy wyjatku
4. **682 plikow cache >30 dni** — 263MB do odzyskania, brak automatycznego czyszczenia
5. **10 plikow w root do przeniesienia**: 3x check_settlement*.py, PHASE3_SPEC.md, PHASE4_SPEC.md, PROJECT_STATE.md, 2x DAILY_ANALYSIS_*.md, maintenance_prompt.md, validation_errors.csv
6. **response_cache.py gotowy ale nie wpiety** w API routes — martwy kod czekajacy na integracje
7. **Lambda optimizer globalny cache** bez TTL — OK dla batch, ale przy dlugo dzialajacym API moze serwowac stale dane

## Co poprawiono/zaproponowano

1. **STATUS.md** — zaktualizowany na 2026-05-20 z pelnym audytem (nowe metryki: 99 modulow, 47 testow, szczegolowe lokalizacje problemow)
2. **TODO.md** — zaktualizowany z precyzyjnymi lokalizacjami (linie, pliki, liczba wystapien) zamiast ogolnych opisow
3. **Priorytety P4.3** — skorygowane na podstawie faktycznych danych (poprzedni priorytet wskazywal backtest_engine(6x) zamiast sts.py(16x))

## Co dziala dobrze

- Wszystkie 99 plikow .py parsuja sie bez bledow syntaktycznych
- Playwright browser_context() ma poprawne p.stop() w finally — brak memory leak
- Lambda optimizer integracja w poisson.py poprawna z graceful fallback
- Pipeline run_daily.bat: backup → draft-wait-final → settlement — kompletny
- Poisson matrix z lru_cache(512) — wydajne
- CircuitBreaker na Playwright (3 failures → 120s recovery)

## Zalecane testy

1. `test_referee_db_conn_cleanup.py` — sprawdz czy conn jest zamykany po bledzie w referee_db.py
2. `test_response_cache_integration.py` — test response_cache.py z mock FastAPI routes
3. `test_lambda_cache_invalidation.py` — sprawdz czy invalidate_cache() czysc globalny _cache
4. `test_dashboard_conn_leak.py` — symuluj blad SQL w _load_predictions, sprawdz close()
5. `test_cleanup_cache_script.py` — po stworzeniu scripts/cleanup_cache.py

## Claude Code Prompt (Caveman Ultra)

```
Tryb: caveman ultra. Bez wyjasnien, czyste zmiany.

Projekt: F:\bot (FootStats v3.4)

TASK 1 — Version sync:
- config.py:11 → VERSION = "v3.4-stable"  
- CLAUDE.md:1 → "# FootStats v3.4-stable"

TASK 2 — SQLite context managers:
referee_db.py — zamien 3x:
  conn = sqlite3.connect(path)
  try: ... finally: conn.close()
na:
  with sqlite3.connect(path) as conn: ...

dashboard.py:28 — zamien _conn() na context manager:
  @contextmanager
  def _conn(db): 
      conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
      try: yield conn
      finally: conn.close()
Uzyj `with _conn(BACKTEST_DB) as conn:` w _load_predictions, _load_wf_results, _load_pending.

TASK 3 — Cache cleanup script:
Stworz scripts/cleanup_cache.py:
  - argparse: --days 30 --dry-run
  - pathlib glob cache/**/* starsze niz N dni
  - raport: ile plikow, ile MB
  - dodaj do run_daily.bat po KROK 0 (backup)

TASK 4 — Root cleanup:
  mv check_settlement*.py scripts/
  mkdir -p docs/archive
  mv PHASE3_SPEC.md PHASE4_SPEC.md docs/archive/
  mv PROJECT_STATE.md DAILY_ANALYSIS_*.md maintenance_prompt.md docs/
  mv validation_errors.csv data/

Po kazdym TASK: git add -A && git commit -m "P4.X: <opis>"
```
