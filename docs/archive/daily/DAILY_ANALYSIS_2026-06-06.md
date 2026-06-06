# FootStats Daily Analysis — 2026-06-06

## Co wykryto

1. **67x `except Exception`** — spadek z 78 (06-05). Top offenders: superbet(5), superbet_bb(4), flashscore_match(4), bzzoiro(4), backtest_engine(4), analyzer(4).
2. **48 uncommitted changes** — wzrost z ~40. Ryzyko utraty pracy.
3. **Duplicate validation_errors.csv** — root (305B, 06-05) + data/ (305B, 05-18). Root nowszy.
4. **footstats.log w root** — nie w .gitignore.
5. **smoke_api.py:60** — hardcoded `password = "testpass"` jako fallback.
6. **11x __pycache__** w src/ — do wyczyszczenia.
7. **5x subprocess.Popen fire-and-forget** — brak monitoringu procesów potomnych (backtest, post_match_analyzer, daily_agent, evening_agent, cli).
8. **Large files** — daily_agent(1474), analyzer(1175), superbet(1128), cli(1112) LOC.

## Co zweryfikowano (OK)

- **Syntax**: 0 SyntaxError we wszystkich .py (pliki na dysku Windows OK, mount sandbox miał stale kopie — nie wpływa na produkcję).
- **Timeouts**: Wszystkie `requests.get/post` mają `timeout` — potwierdzone multiline regex.
- **DB connections**: Wszystkie użycia `connect()` z `with` context manager — brak wycieków.
- **Cache**: `response_cache.py` ma `MAX_ENTRIES=500`, `_evict_oldest()`, `_cleanup_expired()` — brak memory leak.
- **Thread safety**: `RLock` w response_cache, circuit_breaker, lambda_optimizer.
- **Security**: Brak `eval()`/`exec()`/`pickle`/`os.system`. `_exec` w coupon_tracker to bezpieczny DB wrapper.
- **Async**: `async_utils.py` ma timeout, retry z backoff, cleanup_event_loop. Poprawne.
- **Pipeline**: `run_daily.bat` ma backup + syntax check gate + error handling.

## Co poprawiono

- Zaktualizowano `STATUS.md` (nowe metryki, nowe problemy #7-#9, resolved issues).
- Zaktualizowano `TODO.md` (TD7 smoke_api password, TD8 __pycache__, aktualne liczby).

## Zalecane testy

1. **test_timeout_coverage** — test sprawdzający że żaden `requests.get/post` nie istnieje bez `timeout` (regression guard).
2. **test_popen_cleanup** — test że subprocess.Popen procesy mają jakiś monitoring/cleanup.
3. **test_cache_eviction** — test że cache nie rośnie ponad MAX_ENTRIES pod obciążeniem.
4. **test_smoke_api_no_hardcoded** — test że smoke_api nie używa hardcoded credentials.

## Claude Code Prompt

```
Tryb: caveman ultra. Bez wyjaśnień, sam kod.

Kolejność priorytetów:
1. `git add -A && git commit -m "v3.4-stable: 48 zmian, daily sync 2026-06-06"`
2. Dodaj do .gitignore: `footstats.log` i `validation_errors.csv` (root)
3. `rm validation_errors.csv` (root, kopia w data/)
4. `find src/ -name __pycache__ -exec rm -rf {} +`
5. W `src/footstats/operator/smoke_api.py` L60: usuń `password = "testpass"` fallback. Zamień na:
   ```python
   password = os.getenv("FOOTSTATS_PASSWORD")
   if not password:
       raise RuntimeError("FOOTSTATS_PASSWORD env var not set")
   ```
6. Redukcja broad except — TOP 5 plików (superbet.py, superbet_bb.py, flashscore_match.py, bzzoiro.py, analyzer.py):
   - Zamień `except Exception as e` na specyficzne: `except (requests.RequestException, ValueError, KeyError, TimeoutError) as e`
   - W scraperach Playwright: `except (PlaywrightError, TimeoutError, ValueError) as e`
7. Po commitcie: `pytest tests/ -x -q` i napraw failing testy.
```
