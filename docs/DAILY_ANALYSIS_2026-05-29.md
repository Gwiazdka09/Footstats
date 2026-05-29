# Daily Analysis — 2026-05-29

## Co wykryto

1. **17x requests bez timeout** — coupon_settlement, source_manager, api_football(2x), lineup_scraper, bzzoiro(2x), enriched(2x), results_updater + inne. Mogą wisieć w nieskończoność.
2. **216x `except Exception`** — top: superbet(15), base_playwright(14), sts(13), analyzer(13), cli(10), logging(8), historical_loader(8), daily_agent(8). Maskują prawdziwe błędy.
3. **5x subprocess.Popen bez cleanup** — backtest.py, post_match_analyzer.py, cli.py, evening_agent.py, daily_agent.py. Potencjalny leak procesów zombie.
4. **36 uncommitted changes** — dużo zmodyfikowanych plików nie commitowanych do git.
5. **asyncio.get_event_loop() deprecated** — async_utils.py:56, powinno być asyncio.run().
6. **4 pliki >1000 LOC** — daily_agent(1414), analyzer(1393), superbet(1128), cli(1112). Trudne w utrzymaniu.

## Co jest OK (poprawa vs 05-28)

- ✅ **Wszystkie .py kompilują się** — 0 SyntaxError, 0 null bytes (było 12 broken)
- ✅ **node_modules w .gitignore** — nie jest trackowane w git
- ✅ **Stale files usunięte** — CLAUDE_CODE_PROMPT_PHASE9.md, validation_errors.csv, .aider.tags.cache.v4, .coverage
- ✅ **DB access OK** — context managers, Neon PG + SQLite
- ✅ **67 test files** w tests/

## Zalecane testy

1. `test_request_timeouts.py` — grep wszystkie requests.get/post, assert timeout jest ustawiony
2. `test_subprocess_zombie.py` — uruchom Popen, verify proces się kończy po parent exit
3. `test_broad_except_regression.py` — count except Exception, fail jeśli > 216 (regresja)
4. `test_import_all_modules.py` — importuj każdy moduł, sprawdź brak circular imports

## Claude Code Prompt

```
# CAVEMAN ULTRA MODE

Projekt: F:\bot (FootStats v3.4)

## ZADANIE 1: timeout (P1)
Dodaj timeout=15 do KAŻDEGO requests.get/post bez timeout:
- src/footstats/core/coupon_settlement.py:29
- src/footstats/scrapers/source_manager.py:116
- src/footstats/scrapers/api_football.py:60,144
- src/footstats/scrapers/lineup_scraper.py:10
- src/footstats/scrapers/bzzoiro.py:39,62
- src/footstats/scrapers/enriched.py:96,211
- src/footstats/scrapers/results_updater.py:132
Grep resztę: `grep -rn "requests\.\(get\|post\)" src/ | grep -v timeout`

## ZADANIE 2: commit (P2)
```bash
git add -A && git commit -m "fix: timeout audit + cleanup (Phase 10.6)"
```

## ZADANIE 3: except narrowing (P2, top 5 plików)
W superbet.py(15), base_playwright.py(14), analyzer.py(13):
- Zamień `except Exception` na konkretne: `except (ValueError, KeyError, requests.RequestException)`
- Tam gdzie to orchestration (log-and-continue) — dodaj komentarz `# noqa: broad-except`

## ZADANIE 4: async_utils.py fix (P3)
Linia 56: zamień `asyncio.get_event_loop()` na:
```python
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
```

Nie ruszaj nic innego. Commit po każdym zadaniu.
```
