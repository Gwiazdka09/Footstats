# Daily Analysis — 2026-05-30

## Co wykryto

1. **STATUS.md nieaktualny** — twierdził o 17x requests bez timeout i 216x broad except, ale po weryfikacji:
   - Timeout: **0 realnych** brakujących (wszystkie mają timeout=15)
   - Broad except: spadło do **172** (z 216)
   - asyncio deprecated: już naprawione
   - Subprocess: fire-and-forget, OK
2. **38 uncommitted changes** — nadal nie commitowane, ryzyko utraty
3. **Cache bloat** — 817 plików >30 dni, 283MB, brak auto-eviction
4. **4 pliki >1000 LOC** — daily_agent(1414), analyzer(1396), superbet(1128), cli(1112) — bez zmian
5. **Zbędne skrypty** — add_logging.py, fix_logging_fstrings.py (jednorazowe, mogą być usunięte)
6. **23 stare pliki logów** — logs/ zawiera kupony z kwietnia
7. **Accuracy 42.4%** — bez poprawy, M1 target 55%

## Co poprawiono/Zaproponowano

1. ✅ **STATUS.md zaktualizowany** — usunięto fałszywe alarmy (timeout, asyncio, subprocess)
2. ✅ **TODO.md zaktualizowany** — dodano Phase 10.5 (cache eviction), 10.10 (cleanup), Phase 11 (accuracy)
3. 📋 Propozycja: cache auto-eviction >30 dni
4. 📋 Propozycja: commit 38 zmian
5. 📋 Propozycja: refaktoring 4 dużych plików

## Zalecane testy

1. `test_cache_eviction` — test auto-czyszczenia cache >30 dni
2. `test_analyzer_prompts` — po wydzieleniu promptów z analyzer.py
3. `test_calibration_accuracy` — porównanie Poisson vs Bayesian Poisson na danych historycznych
4. `test_value_bet_precision` — precision/recall value bet filtra przy różnych marginach

## Claude Code Prompt

```
# CAVEMAN ULTRA — FootStats batch fix

Projekt: F:\bot
Tryb: caveman ultra — zero wyjaśnień, czysty kod.

## ZADANIA (kolejność):

### 1. GIT COMMIT (P2)
git add -A && git commit -m "v3.4: audit fixes, cleanup, status update 2026-05-30"

### 2. CACHE EVICTION (P3)
W src/footstats/utils/cache.py dodaj:

def evict_old_cache(max_days: int = 30) -> int:
    """Usuwa pliki cache starsze niż max_days. Zwraca liczbę usuniętych."""
    import time
    from pathlib import Path
    cache_dir = Path("cache")
    cutoff = time.time() - max_days * 86400
    removed = 0
    for f in cache_dir.rglob("*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    return removed

W daily_agent.py na końcu main(): evict_old_cache(30)

### 3. CLEANUP ZBĘDNYCH PLIKÓW (P4)
rm scripts/add_logging.py scripts/fix_logging_fstrings.py
# Stare logi — zostawić (mogą być potrzebne do analizy accuracy)

### 4. ANALYZER.PY REFACTOR (P3) — opcjonalnie
Wydziel z analyzer.py:
- ai/prompts.py — _get_kalibracja_blok, _get_liga_statystyki_blok, prompt templates
- ai/scoring.py — _value_bet, _kurs_do_prob, _deduplikuj_kupony, _wymusz_40pct
Zachowaj importy w analyzer.py (re-export).

Test: pytest tests/ -x -q
```
