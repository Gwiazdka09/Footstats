# Analiza Dzienna — 2026-06-03

## Co wykryto

1. **38 uncommitted changes** (P1) — ciągle niescommitowane, ryzyko utraty pracy
2. **160x `except Exception`** — broad except, top: base_playwright(14), analyzer(8), daily_agent(8)
3. **4 duże pliki >1000 LOC** — analyzer(1454), daily_agent(1441), superbet(1128), cli(1112)
4. **11x `conn.close()` bez context manager** — bankroll.py(6), json_export.py(2) — potencjalny wyciek połączeń przy wyjątkach
5. **Duplikat `validation_errors.csv`** — w root i data/
6. **`tests/scratch`** — debug plik w repo
7. **3x `data/.fuse_hidden*`** — orphan pliki FUSE (32KB każdy)
8. **12 DAILY_ANALYSIS docs** — niezarchiwizowane
9. **Empty WAL files** — `footstats.db-wal` i `footstats_backtest.db-wal` (0 bytes) — nieszkodliwe

## Co poprawiono/zaproponowano

1. ✅ Zaktualizowano `STATUS.md` — nowe metryki (160 broad except, 38 uncommitted, 22.5k LOC)
2. ✅ Zaktualizowano `TODO.md` — dodano sekcję Cleanup (P4) z 5 konkretnymi taskami
3. ✅ Brak SyntaxError (0/80+ plików)
4. ✅ Brak `eval()`, `pickle.load()`, `os.system()`, `subprocess.call()` — bezpieczeństwo OK
5. ✅ Brak `asyncio.get_event_loop()` (deprecated) — naprawione wcześniej
6. ✅ Wszystkie `requests.get/post` mają timeout
7. ✅ GUI dist/ zbudowane, React/Vite OK

## Zalecane testy

1. `test_conn_context_manager` — sprawdzić że bankroll.py/json_export.py używają `with` zamiast manual close
2. `test_broad_except_count` — assert count < 150 (regresja)
3. `test_large_file_loc` — assert analyzer.py < 1200 LOC po refactorze
4. `test_stale_files` — sprawdzić brak `.fuse_hidden`, `tests/scratch`, duplikat `validation_errors.csv`

## Claude Code Prompt

```
Tryb: caveman ultra. Projekt: F:\bot

TASK 1 — COMMIT (P1):
git add -A && git commit -m "v3.4: audit 06-03 — status+todo update, cleanup queue"

TASK 2 — CLEANUP (P4):
rm validation_errors.csv tests/scratch data/.fuse_hidden*
mkdir -p docs/archive/daily && mv docs/DAILY_ANALYSIS_*.md docs/archive/daily/

TASK 3 — CONN CONTEXT MANAGER (P3):
W bankroll.py, json_export.py, coupon_tracker.py — zamień:
  conn = sqlite3.connect(...)
  ...
  conn.close()
na:
  with sqlite3.connect(...) as conn:
      ...
Dotyczy 11 miejsc. Testuj: pytest tests/test_betting_utils.py tests/test_coupon_tracker.py -v

TASK 4 — BROAD EXCEPT TOP-5 (P2):
W base_playwright.py(14x), analyzer.py(8x), daily_agent.py(8x):
zamień `except Exception` na konkretne typy:
- playwright: `except (TimeoutError, Error) as e:`
- requests: `except (RequestException, Timeout) as e:`
- json: `except (json.JSONDecodeError, KeyError) as e:`
- sqlite: `except sqlite3.Error as e:`
- generic IO: `except (OSError, IOError) as e:`
Zachowaj istniejące logowanie. Nie zmieniaj logiki. Target: <130 broad except.

TASK 5 — git add -A && git commit -m "cleanup: context managers, specific exceptions" && git push
```
