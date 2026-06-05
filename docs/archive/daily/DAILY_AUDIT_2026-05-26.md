# FootStats Daily Audit — 2026-05-26

## Co wykryto

1. **10 plików src/ obciętych** — config.py (-18 linii), daily_agent.py (-61), lambda_optimizer.py (-33), async_utils.py (-5), response_cache.py (-10), value_bet.py (-58), api/main.py (-30), db/migrations.py (-7), bankroll.py (-105), ensemble.py (-10)
2. **5 plików testowych obciętych** — test_auth (-1), test_coupon_tracker (-5), test_daily_agent_faza (-9), test_evening_agent (-9), test_response_cache (-7)
3. **16x requests.get/post bez timeout** — w 9 plikach (coupon_settlement, source_manager, api_football, lineup_scraper, enriched, results_updater, bzzoiro, ai/client, telegram_notify)
4. **3x sqlite3.connect bez context manager** — probability_calibrator, ensemble_optimizer, dashboard
5. **__pycache__ root** — 2MB starych .pyc (stare monolityczne moduły)
6. **data/.fuse_hidden*** — 12 orphaned FUSE handle plików
7. **git index.lock** — blokuje commit/push operations
8. **Thread-safety** — 10x global mutation bez lock (response_cache, lambda_optimizer, rag_embeddings)
9. **Duplicate function names** — 6x main(), 3x zaloguj(), 3x _zapisz_cache()
10. **Accuracy 42.4%** — poniżej M1 target 55%

## Co poprawiono

1. ✅ Przywrócono 10 plików src/ z git HEAD
2. ✅ Przywrócono 5 plików testowych z git HEAD
3. ✅ Weryfikacja syntax: 0 errors w 108 modułach
4. ✅ Zaktualizowano STATUS.md z aktualnym stanem
5. ✅ Zaktualizowano TODO.md z Phase 8 planem

## Zalecane testy

1. `test_file_integrity.py` — sprawdzaj line count kluczowych plików vs expected
2. `test_requests_timeout.py` — grep all requests calls, verify timeout param
3. `test_value_bet_filter.py` — EV/Kelly edge cases (odds=1.0, prob=0/1)
4. `test_probability_calibrator.py` — isotonic regression correctness
5. `test_daily_agent_prefilter.py` — liga whitelist/blacklist filtering
6. `test_sqlite_context_manager.py` — verify conn.close() always called

## Claude Code Prompt

```
Tryb: caveman ultra. Bez wyjaśnień, czyste zmiany.

TASK 1: timeout requests (16 plików)
Dodaj timeout=15 do KAŻDEGO requests.get/post/put/delete w:
- src/footstats/core/coupon_settlement.py:29
- src/footstats/scrapers/source_manager.py:116
- src/footstats/scrapers/api_football.py:60,144
- src/footstats/scrapers/lineup_scraper.py:10
- src/footstats/scrapers/enriched.py:96,211
- src/footstats/scrapers/results_updater.py:132,174,402
- src/footstats/scrapers/bzzoiro.py:39,62
- src/footstats/ai/client.py:80
- src/footstats/utils/telegram_notify.py:48

TASK 2: sqlite context manager (3 pliki)
Zamień conn=sqlite3.connect() + try/finally/close na with:
- src/footstats/core/probability_calibrator.py:26
- src/footstats/core/ensemble_optimizer.py:91
- src/footstats/dashboard.py:31

TASK 3: cleanup
rm -rf __pycache__/
Dodaj /__pycache__/ do .gitignore jeśli brak.

TASK 4: test file integrity
Stwórz tests/test_file_integrity.py:
- Lista (plik, min_lines) dla 10 kluczowych plików
- Sprawdź py_compile.compile() + wc -l >= min
- pytest parametrize

Po każdym TASK: git add + commit z msg "[audit] <opis>"
```
