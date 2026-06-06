# FootStats — Daily Analysis Report 2026-06-05

## Co wykryto

1. **0 SyntaxError** — ast.parse OK na wszystkich 110+ modułach .py
2. **78x `except Exception`** (spadek z 160x) — top offenders: cli(6), superbet(5), form_scraper(5), superbet_bb(4), flashscore_match(4), bzzoiro(4), backtest_engine(4), analyzer(4)
3. **~40 uncommitted changes** — ryzyko utraty pracy (P1)
4. **4 duże pliki >1000 LOC**: daily_agent(1474), analyzer(1175), superbet(1128), cli(1112)
5. **2 failing testy** (pre-existing): test_blend_50_50_applied + test_send_kupon_test_data
6. **Duplikat** validation_errors.csv w root (kopia w data/)
7. **footstats.log** w root — powinien być w .gitignore
8. **Accuracy 26.7% live** (15 kuponów) — daleko od M1=55%, Faza 13 kalibracja pasywna w toku
9. **Browser.close() w scraperach** — większość używa try/finally (OK), ale pattern niespójny (niektóre mają context manager z base_playwright, inne ręczne close)

## Co poprawiono/Zaproponowano

1. **STATUS.md** zaktualizowany (data, metryki, liczba broad except, test count)
2. **TODO.md** zaktualizowany — dodano sekcję TECH DEBT z 6 zadaniami
3. **Żadne pliki nie zostały usunięte** — brak zbędnych plików poza duplikatem CSV i logiem (wymaga commit na maszynie lokalnej)

## Pozytywne obserwacje

- Core testy stabilne: **244+ passed** (poisson, kelly, ensemble, helpers, normalize, circuit_breaker, decision_score, betting_utils, cache, async_utils)
- Architektura solidna: Poisson+xG blend, ensemble weights, checkpoint system, circuit breaker, RAG feedback loop
- Langfuse tracing zintegrowane w analyzer.py
- Evening agent dodany (nowy od ostatniego audytu)
- async_utils.py dobrze napisany: gather_with_timeout, retry z backoff, cleanup

## Zalecane testy do wdrożenia

1. **test_daily_agent_full_pipeline** — end-to-end: mock Bzzoiro → forma → Groq → kupon (integracja daily_agent)
2. **test_ensemble_per_league_weights** — czy ensemble_optimizer poprawnie loaduje wagi per-liga
3. **test_superbet_api_fallback** — czy API→DOM fallback działa w superbet.py
4. **test_poisson_xg_blend** — czy xG blend (20%) poprawnie modyfikuje lambdy
5. **test_evening_agent_settlement** — czy evening_agent poprawnie settlement'uje kupony
6. **Fix existing**: test_blend_50_50_applied (mock df_mecze), test_send_kupon_test_data (mock Telegram API)

## Claude Code Prompt

```
Tryb caveman ultra. Projekt F:\bot, PYTHONPATH=src.

ZADANIA (kolejność priorytetów):

1. GIT COMMIT:
git add -A && git commit -m "v3.4: daily sync 2026-06-05 — evening_agent, dashboard updates, scraper fixes"

2. USUN DUPLIKAT:
rm validation_errors.csv
echo "footstats.log" >> .gitignore

3. FIX 2 TESTY:
- tests/test_quick_picks_ensemble.py::test_blend_50_50_applied — sprawdź czy mock df_mecze ma wymagane kolumny (gospodarz, goscie, gole_g, gole_a, data). Dodaj brakujące kolumny do fixture.
- tests/test_telegram.py::test_send_kupon_test_data — dodaj mock.patch na requests.post żeby nie wymagał prawdziwego TELEGRAM_BOT_TOKEN.

4. BROAD EXCEPT (top 3 pliki, zamień na specyficzne):
- src/footstats/cli.py (6x) → zamień na (ImportError, ValueError, KeyError, RuntimeError) w zależności od kontekstu
- src/footstats/scrapers/superbet.py (5x) → zamień na (PWTimeout, PWError, ValueError, ConnectionError)
- src/footstats/scrapers/form_scraper.py (5x) → zamień na (PWTimeout, PWError, json.JSONDecodeError)

5. Po zmianach: pytest tests/ -v --tb=short, potwierdź 0 failures.

NIE ruszaj: poisson.py, ensemble.py, daily_agent.py (logika predykcji stable).
```
