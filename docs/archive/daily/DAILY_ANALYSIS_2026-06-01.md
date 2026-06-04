# Daily Analysis — 2026-06-01

## Co wykryto

1. **4x truncated files (P0)** — `bankroll.py` (186/207), `analyzer.py` (1394/1454), `admin_users.py` (101/113), `routes/bankroll.py` (46/47) — obcięte w trakcie zapisu
2. **157x broad `except Exception`** — top: base_playwright(14), analyzer(8), logging(7), historical_loader(7), daily_agent(7)
3. **50 uncommitted changes** — ryzyko utraty pracy przy kolejnym truncation
4. **Recurring truncation pattern** — 3. epizod w ciągu tygodnia (05-28, 05-31, 06-01). Prawdopodobna przyczyna: proces zapisu (Claude Code/edytor) przerywany lub dysk I/O
5. **Large files** — analyzer(1454), daily_agent(1401), superbet(1128), cli(1112) LOC
6. **11 DAILY_ANALYSIS docs** w docs/ — rośnie

## Co poprawiono

1. ✅ Przywrócono 4 truncated pliki z `git HEAD`
2. ✅ 0 SyntaxError w całym src/ (115 plików)
3. ✅ Zaktualizowano STATUS.md i TODO.md
4. ✅ Deprecated asyncio.get_event_loop() — brak (wcześniej naprawione)
5. ✅ Brak requests bez timeout

## Zalecane testy

```python
# test_bankroll_kelly.py
def test_kelly_fraction_edge_negative():
    """Kelly zwraca 0 gdy edge < 0."""
    assert kelly_fraction(0.3, 2.0, 1000) == 0.0

def test_kelly_fraction_max_cap():
    """Kelly nie przekracza 10% bankrolla."""
    stake = kelly_fraction(0.9, 5.0, 1000)
    assert stake <= 100.0

# test_analyzer_ocen_kupon.py
def test_ocen_kupon_returns_tuple():
    """oceń_kupon zwraca (str, int)."""
    result = oceń_kupon([{"match": "A vs B", "pick": "1"}])
    assert isinstance(result, tuple)
    assert isinstance(result[1], int)

# test_admin_deactivate.py
def test_deactivate_user_nonexistent():
    """Deactivate nieistniejącego usera → 404."""
    ...
```

## Claude Code Prompt

```
Tryb: caveman ultra. Bez wyjaśnień, tylko kod.

PILNE:
1. git add -A && git commit -m "fix: restore 4 truncated files + daily audit 06-01" && git push
2. Dodaj git pre-commit hook sprawdzający czy pliki nie są obcięte:
   scripts/check_truncation.py — dla każdego .py w src/ sprawdź czy ostatnia linia kończy się \n i czy ast.parse przechodzi. Hook: .git/hooks/pre-commit wywołuje python scripts/check_truncation.py

REFACTOR (P2):
3. src/footstats/scrapers/base_playwright.py — zamień 14x `except Exception` na konkretne: PlaywrightTimeoutError, NetworkError. Loguj traceback.
4. src/footstats/ai/analyzer.py — wydziel:
   - ai/prompts.py (stringi promptów)
   - ai/scoring.py (logika scoringu)
   Zostaw analyzer.py jako orchestrator <500 LOC.

TESTY:
5. tests/test_bankroll_kelly.py — kelly_fraction: edge<0→0, cap 10%, min 1 PLN
6. tests/test_truncation_guard.py — importuj wszystkie moduły src/, assert brak SyntaxError
```
