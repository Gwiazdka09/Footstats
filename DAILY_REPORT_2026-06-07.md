# FootStats — Raport Dzienny 2026-06-07

## Co wykryto

1. **🔴 KRYTYCZNE: 26 plików truncated (obcięte w połowie linii)** — cli.py, config.py, decision_score.py, circuit_breaker.py, async_utils.py, processing.py, 8 scraperów, cache.py, coupons.py, migrations.py, runner.py + 5 testów. Pliki ucinały się w połowie stringa/nawiasu. Python nie mógł ich zaimportować.

2. **🔴 KRYTYCZNE: 4 pliki z trailing null bytes** — analyzer.py (8130 nulls), daily_agent.py (6071 nulls), context_scraper.py (130), smoke_api.py (77). ast.parse() zwracał "source code string cannot contain null bytes".

3. **🟡 80 uncommitted changes** w git — ryzyko utraty pracy przy kolejnym incydencie.

4. **🟡 25x `except Exception`** — spadek z 67 (po przywróceniu plików z HEAD), głównie backtest_engine(4), backtest(3), analyzer(3).

5. **🟡 .gitignore** — brakowało wpisów `footstats.log` i `validation_errors.csv`.

6. **⚪ 5x subprocess.Popen** fire-and-forget — brak monitoringu procesów potomnych.

## Co poprawiono

1. ✅ **Przywrócono 26 truncated plików** z git HEAD (git show + cp)
2. ✅ **Usunięto null bytes z 4 plików** (strip trailing \x00)
3. ✅ **193/193 .py parsuje się poprawnie** (121 src + 72 tests)
4. ✅ **Dodano do .gitignore**: footstats.log, validation_errors.csv
5. ✅ **Zaktualizowano STATUS.md** i **TODO.md**

## Zalecane testy

```bash
# 1. Weryfikacja składni (po każdej sesji Claude Code)
python -c "import ast,os;[ast.parse(open(os.path.join(r,f)).read()) for r,_,fs in os.walk('src/footstats/') for f in fs if f.endswith('.py') and '__pycache__' not in r]"

# 2. Test importu kluczowych modułów
python -c "from footstats.daily_agent import _pobierz_kandydatow; print('daily_agent OK')"
python -c "from footstats.ai.analyzer import analyze_match; print('analyzer OK')"
python -c "from footstats.config import VERSION; print(f'config OK: {VERSION}')"

# 3. Pełny test suite
pytest tests/ -v --tb=short

# 4. Pre-commit hook: null byte detection
python -c "import os;[print(f'NULL: {os.path.join(r,f)}') for r,_,fs in os.walk('src/') for f in fs if f.endswith('.py') and b'\x00' in open(os.path.join(r,f),'rb').read()]"
```

## Claude Code Prompt

```
Tryb caveman ultra. Projekt F:\bot, Python, PL komentarze.

PILNE — zrób po kolei:

1. git add -A && git commit -m "v3.4: fix 30 truncated/null files, gitignore update" && git push origin main

2. Dodaj pre-edit backup hook (.claude/hooks/pre-edit.sh):
   - Przed każdą edycją pliku .py kopiuj oryginał do .claude/backups/
   - Format: {filename}.{timestamp}.bak

3. Przenieś "testpass" z smoke_api.py do .env:
   - .env: SMOKE_TEST_PASS=testpass  
   - smoke_api.py: os.getenv("SMOKE_TEST_PASS", "changeme")

4. Wyczyść __pycache__:
   find src/ tests/ scripts/ -name __pycache__ -exec rm -rf {} +

5. Usuń validation_errors.csv z root (duplikat data/):
   del F:\bot\validation_errors.csv

Nie zmieniaj logiki modelu. Nie ruszaj daily_agent ani ensemble.
```
