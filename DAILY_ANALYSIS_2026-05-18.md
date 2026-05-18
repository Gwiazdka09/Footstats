# FootStats — Raport Analizy 2026-05-18

## Co wykryto

1. **VERSION mismatch** — config.py mówi "v3.2", CLAUDE.md "v3.3", STATUS.md "v3.4". Niespójność wersji utrudnia tracking.
2. **216x `except Exception`** — wiele bez logowania (silent failures). Najgorzej: backtest_engine.py (6x), coupon_settlement.py (4x), calibration.py (3x).
3. **SQLite connection leaks** — referee_db.py (3 miejsca) i dashboard.py (4 miejsca) używają `conn = sqlite3.connect()` bez context managera. Jeśli wyjątek przed `conn.close()` → leak.
4. **263MB starych plików cache** — 614 plików >30 dni w cache/form/. Zajmują miejsce bez wartości.
5. **4 skrypty w root** — check_settlement*.py i manage.py zaśmiecają katalog główny (powinny być w scripts/).
6. **5 plików .md do archiwizacji** — PHASE3_SPEC.md, PHASE4_SPEC.md, PROJECT_STATE.md, maintenance_prompt.md, DAILY_ANALYSIS_2026-05-13.md — zakończone fazy, do docs/.
7. **Poisson LRU cache maxsize=512** — OK dla normalnego użycia, ale przy masowym backtecie może być za mały. Monitorować cache_info().
8. **async_utils.py i logging_config.py** — moduły utworzone ale nie zintegrowane z scraperami (Phase 2 partially wired).

## Co jest OK

- **0 bare excepts** — wszystkie mają typ.
- **0 syntax errors** — cały codebase parsuje się poprawnie.
- **0 TODO/FIXME/HACK** w kodzie — czysto.
- **Playwright context managers** — base_playwright.py ma prawidłowe CM z cleanup.
- **Circuit Breaker** — thread-safe, poprawna implementacja stanów.
- **Kelly Criterion** — czysta logika, proper edge case handling (odds<=1.01, p<=0).
- **Data validation** — Pydantic GameRecord z walidatorami dat i drużyn.
- **DB structure** — 1966 predictions, 174 coupons, 219 AI feedbacks, zdrowe proporcje.

## Zaproponowane zmiany

1. **Sync VERSION** → "v3.4-stable" wszędzie
2. **SQLite `with` pattern** w referee_db.py i dashboard.py
3. **Dodać logging do top-10 najgorszych `except Exception: pass`**
4. **Cache cleanup script** + cron/scheduled task
5. **Przenieść pliki root** do scripts/ i docs/

## Zalecane testy

1. `test_referee_db_conn_cleanup.py` — sprawdź że conn jest zamykany nawet przy wyjątku
2. `test_version_consistency.py` — parsuj config.py, CLAUDE.md, STATUS.md i assercja że wersje się zgadzają
3. `test_cache_cleanup.py` — test skryptu czyszczenia cache (mock filesystem)
4. `test_exception_logging.py` — sprawdź że kluczowe except bloki logują (monkeypatch logger)

## Claude Code Prompt

```
Tryb: caveman ultra. Bez wyjaśnień, tylko kod.

1. config.py:11 → VERSION = "v3.4-stable"
2. CLAUDE.md:1 → # FootStats v3.4-stable

3. referee_db.py — zamień 3 funkcje na context manager pattern:
   def init_referee_table(db_path=None):
       path = _db(db_path)
       path.parent.mkdir(parents=True, exist_ok=True)
       with sqlite3.connect(path) as conn:
           conn.execute(_DDL)
   (analogicznie upsert_referee i get_referee)

4. dashboard.py — zmień _conn() na context manager:
   @contextmanager
   def _conn(db):
       if not db.exists():
           yield None
           return
       conn = sqlite3.connect(db)
       conn.row_factory = sqlite3.Row
       try:
           yield conn
       finally:
           conn.close()
   Potem użyj: with _conn(BACKTEST_DB) as conn: ...

5. Nowy plik scripts/cleanup_cache.py:
   import argparse, os, time
   from pathlib import Path
   def clean(cache_dir="cache", days=30):
       cutoff = time.time() - days*86400
       removed = 0
       for p in Path(cache_dir).rglob("*"):
           if p.is_file() and p.stat().st_mtime < cutoff:
               p.unlink()
               removed += 1
       print(f"Usunięto {removed} plików")
   if __name__=="__main__":
       ap = argparse.ArgumentParser()
       ap.add_argument("--days", type=int, default=30)
       clean(days=ap.parse_args().days)

6. Przenieś pliki:
   mv check_settlement*.py scripts/
   mkdir -p docs/archive
   mv PHASE3_SPEC.md PHASE4_SPEC.md PROJECT_STATE.md maintenance_prompt.md docs/archive/
   mv DAILY_ANALYSIS_2026-05-13.md docs/archive/

7. backtest_engine.py — w 6 blokach except Exception dodaj:
   logger.warning("Backtest error: %s", e) (gdzie jest `as e`)
   logger.warning("Backtest silent error") (gdzie brak `as e`)

Testy: pytest tests/ -v po zmianach.
```
