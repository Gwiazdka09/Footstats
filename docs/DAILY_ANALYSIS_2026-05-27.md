# FootStats Daily Analysis — 2026-05-27

## Co wykryto

1. **1x requests.post bez timeout** — `utils/telegram_notify.py:48` — może zablokować pipeline na wysyłce Telegram
2. **Version mismatch** — `pyproject.toml` version="3.0" vs `config.py` VERSION="v3.4-stable"
3. **236x `except Exception`** — maskowanie prawdziwych błędów; top: sts.py(16), superbet.py(15), base_playwright.py(14), daily_agent.py(14), analyzer.py(13)
4. **5x subprocess.Popen fire-and-forget** — backtest.py, post_match_analyzer.py, evening_agent.py, cli.py, daily_agent.py — brak .wait()/.communicate(), potencjalne zombie procesy
5. **10x `__pycache__/` dirs (~13MB)** — odrosły od ostatniego czyszczenia
6. **`data/footstats.db` (262KB)** — w .gitignore ale nadal istnieje na dysku
7. **3x `data/.fuse_hidden*`** — orphaned FUSE handles (system-level, nie blokują)
8. **12 plików >500 LOC** — daily_agent(1396), analyzer(1393), superbet(1128), cli(1112) — kandydaci do refaktoryzacji
9. **Accuracy 42.4%** — wciąż poniżej M1 target (55%)
10. **Cloud Run env vars BLOCKER** — login fix (Phase 9.1) wymaga ręcznej konfiguracji

## Co poprawiono/zaktualizowano

1. ✅ **STATUS.md** — zaktualizowany do 2026-05-27, nowe metryki (63 testy, 236 broad except, cache 283MB)
2. ✅ **TODO.md** — dodany Phase 10 (Code Quality & Accuracy), archiwizacja Phase 8-9, nowe proposed tests
3. ✅ Potwierdzono: 0 syntax errors, SQLite context managers OK, thread safety locks OK
4. ✅ Potwierdzono: results_updater.py — wszystkie 3 requesty MAJĄ timeout=15 (fałszywy alarm wcześniej)
5. ✅ Potwierdzono: response_cache.py — eviction działa (MAX_ENTRIES=500, _evict_oldest)
6. ✅ Potwierdzono: lambda_optimizer.py — double-checked locking z threading.Lock

## Zalecane testy

1. `test_telegram_timeout.py` — verify timeout on telegram requests.post
2. `test_subprocess_cleanup.py` — verify Popen processes get cleaned up
3. `test_version_consistency.py` — pyproject.toml vs config.py VERSION match
4. `test_broad_except_audit.py` — flag new bare/broad except additions via AST

## Claude Code Prompt (caveman ultra)

```
Tryb: caveman ultra. Bez wyjaśnień, tylko kod i commity.

TASK 1 — telegram timeout:
- src/footstats/utils/telegram_notify.py: dodaj timeout=15 do requests.post() call (~linia 48)

TASK 2 — version sync:
- pyproject.toml: version = "3.0" → version = "3.4"

TASK 3 — cleanup:
- Usuń wszystkie __pycache__/ dirs: find . -name __pycache__ -type d -exec rm -rf {} +
- Usuń data/footstats.db (już w .gitignore)

TASK 4 — top 3 broad except (sts.py):
- src/footstats/scrapers/sts.py: zamień except Exception na except (TimeoutError, ValueError, requests.RequestException) gdzie to dotyczy HTTP/parsing. Zostaw except Exception tylko tam gdzie naprawdę nie wiadomo co poleci. Loguj e.__class__.__name__ w każdym catchu.

TASK 5 — subprocess safety (daily_agent.py linia 484):
- Zamień subprocess.Popen na subprocess.run z timeout=30, capture_output=True. Jeśli to background task (nie czekamy na wynik) — dodaj komentarz # fire-and-forget: OK, Windows notification.

Commituj każdy task osobno. Polskie komentarze.
```
