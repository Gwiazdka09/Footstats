# Raport Dzienny — 2026-05-31

## Co wykryto

1. **🔴 P0: 7 truncated plików** — quick_picks.py, response_cache.py, bankroll.py, coupons.py, auth.py, main.py, migrations.py — ucięte w trakcie zapisu, SyntaxError uniemożliwiał import
2. **🟡 P1: 50 uncommitted changes** — wzrost z 38 (05-30) do 50 — rosnące ryzyko utraty pracy
3. **🟡 P2: 174x `except Exception`** — top pliki: base_playwright(14), sts(13), daily_agent(8)
4. **🟡 P2: Accuracy 42.4%** — bez zmian, poniżej M1 target 55%
5. **⚪ P4: 25 starych logów w logs/**, 10 DAILY_ANALYSIS docs w docs/, 2 jednorazowe skrypty (add_logging.py, fix_logging_fstrings.py)

## Co poprawiono

1. ✅ **7 truncated plików przywrócone z git HEAD** — wszystkie .py kompilują się poprawnie
2. ✅ **STATUS.md zaktualizowany** — nowe metryki, nowy wpis w resolved issues
3. ✅ **TODO.md zaktualizowany** — BUG-3, priorytet commitu podniesiony do P1
4. ✅ **Timeout audit**: wszystkie requests.get/post mają timeout (1 false positive w docstringu)
5. ✅ **Brak null bytes, brak bare except, brak deprecated asyncio (poza 1x cleanup w async_utils)**

## Zalecane testy

1. `pytest tests/test_api_routes.py -v` — weryfikacja przywróconych routes (bankroll, coupons)
2. `pytest tests/test_auth.py -v` — weryfikacja require_admin po restore auth.py
3. `python -m py_compile src/footstats/core/quick_picks.py` — smoke test przywróconego pliku
4. `pytest tests/test_core_pure.py -v` — regresja core logic
5. Nowy test: `test_no_truncated_files.py` — sprawdza czy każdy .py kompiluje się (py_compile)

## Claude Code Prompt

```
Caveman ultra mode. Zrob po kolei:

1. GIT COMMIT TERAZ:
git add -A && git commit -m "fix: restore 7 truncated files, audit 2026-05-31"

2. Nowy test tests/test_compile_all.py:
import py_compile, glob, pytest
@pytest.mark.parametrize("f", glob.glob("src/footstats/**/*.py", recursive=True))
def test_compiles(f):
    py_compile.compile(f, doraise=True)

3. Top 5 broad except w base_playwright.py (14x) — zamien na konkretne:
- TimeoutError, PlaywrightError dla Playwright ops
- ValueError, KeyError dla parsowania
- requests.RequestException dla HTTP
Nie ruszaj tych w blokach retry/cleanup.

4. Uruchom: pytest tests/ -x -q
```
