# FootStats — Raport Dzienny 2026-06-08

## Co wykryto

1. **🔴 `__init__.py` version desync** — `__version__ = "2.7"` vs config/pyproject `3.4`. Import `footstats.__version__` zwraca złą wersję.

2. **🔴 27 uncommitted changes** — spadek z 80 (06-07), ale wciąż niezapuszczone do repo.

3. **🟡 2x `subprocess.run` bez timeout** — `daily_agent_scheduler.py` linie 23 i 67. Faza draft/final może wisieć w nieskończoność.

4. **🟡 25x `except Exception`** — bez zmian od 06-07. Top: backtest_engine(4), backtest(3), analyzer(3).

5. **⚪ 5x `subprocess.Popen` fire-and-forget** — evening_agent, cli, daily_agent, backtest, post_match_analyzer. Procesy potomne bez monitoringu.

6. **⚪ docs/PROJECT_STATE.md** — referencje do v3.3, nieaktualne.

7. **⚪ .fuse_hidden + 12x __pycache__** — artefakty do wyczyszczenia.

## Co zweryfikowano (OK)

- ✅ 193/193 plików .py parsuje się poprawnie (0 SyntaxError, 0 null bytes)
- ✅ Wszystkie `requests.get/post` mają timeout (multiline calls — potwierdzone ręcznie)
- ✅ Wszystkie `sqlite3.connect` używają context manager
- ✅ Thread safety: Lock w circuit_breaker, response_cache, lambda_optimizer
- ✅ response_cache: MAX_ENTRIES=500, eviction + TTL OK
- ✅ smoke_api.py: testpass przeniesiony do env (już naprawiony)
- ✅ Security: brak eval/pickle/os.system, brak hardcoded secrets
- ✅ 70 test files, wszystkie parsują się poprawnie
- ✅ Pipeline run_daily.bat: backup → syntax check → scheduler — OK
- ✅ pyproject.toml i config.py version sync (3.4) — OK

## Co poprawiono

1. ✅ Zaktualizowano **STATUS.md** — nowe problemy, resolved issues
2. ✅ Zaktualizowano **TODO.md** — TD11 (version), TD12 (timeout), TD13 (cleanup)

## Zalecane testy

```bash
# 1. Weryfikacja składni
python -c "import ast,os;[ast.parse(open(os.path.join(r,f)).read()) for r,_,fs in os.walk('src/footstats/') for f in fs if f.endswith('.py') and '__pycache__' not in r]"

# 2. Version consistency
python -c "from footstats import __version__; from footstats.config import VERSION; assert __version__ == '3.4', f'FAIL: {__version__}'; print('OK')"

# 3. Full test suite
pytest tests/ -v --tb=short
```

## Claude Code Prompt

```
Tryb caveman ultra. F:\bot, Python, PL komentarze.

Zrób po kolei:

1. Fix version: src/footstats/__init__.py → __version__ = "3.4"

2. Timeout w daily_agent_scheduler.py:
   - Linia ~23: subprocess.run([...], cwd=DATA_DIR.parent) → dodaj timeout=7200
   - Linia ~67: subprocess.run([...], cwd=DATA_DIR.parent) → dodaj timeout=7200

3. Cleanup:
   find . -name __pycache__ -not -path ./.venv/\* -not -path ./.vexp/\* -exec rm -rf {} +
   rm -f .fuse_hidden*
   mv DAILY_REPORT_2026-06-07.md docs/archive/daily/
   mv DAILY_REPORT_2026-06-08.md docs/archive/daily/

4. .gitignore — dodaj na koniec:
   DAILY_REPORT_*.md

5. docs/PROJECT_STATE.md — zamień "v3.3" na "v3.4" w tytule i treści

6. Git commit:
   git add -A
   git commit -m "v3.4: fix version sync, scheduler timeout, cleanup pycache"
   git push origin main

Nie ruszaj niczego innego. Żadnych refaktorów.
```
