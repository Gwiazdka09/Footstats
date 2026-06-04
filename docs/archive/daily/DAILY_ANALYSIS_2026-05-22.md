# FootStats Daily Analysis — 2026-05-22

## Co wykryto

1. **`_RESPONSE_CACHE` unbounded dict** (response_cache.py:21) — brak MAX_ENTRIES/eviction. Przy dlugim uptime API pamiec rosnie bez limitu. PRIORYTET.
2. **223x `except Exception`** — bare except w 15+ plikach. Top: sts(16), superbet(15), base_playwright(14). Ciche bledy, brak logowania.
3. **Duplikat `from langfuse import Langfuse`** w analyzer.py (linia 17 i 25) — podwojny import tego samego modulu.
4. **`asyncio.get_event_loop()` deprecated** w async_utils.py (2x) — Python 3.12+ warning, powinno byc `get_running_loop()`.
5. **Stale pliki w repo**: brain_graph.html (duplikat), validation_errors.csv (duplikat), tests/scratch, data/lf_sig.txt, data/lf_ver.txt, data/env_wzor.txt.
6. **GUI scaffolding** (counter.ts, typescript.svg, vite.svg) — nieuzywane pliki z template Vite.
7. **PowerShell injection** w `_powiadomienie_windows` — `replace("'", "''")`  to slabe zabezpieczenie, ale ryzyko niskie (dane z wewnetrznych zrodel).

## Co poprawiono/Zaproponowano

1. Zaktualizowano STATUS.md z pelnym audytem 2026-05-22.
2. Zaktualizowano TODO.md — dodano P4.8, P4.9, P4.10 + propozycje testow.
3. Zidentyfikowano brak eviction w response_cache jako krytyczny → P4.8.
4. Zidentyfikowano 5 nowych propozycji testow.

## Zalecane testy

1. `test_response_cache_eviction.py` — max entries, TTL, memory cap
2. `test_referee_db_conn_cleanup.py` — sqlite context manager
3. `test_daily_agent_prefilter.py` — edge cases pre-filtrow
4. `test_coupon_settlement_edge.py` — partial/void settlement
5. `test_powiadomienie_windows.py` — PS escape test

## Claude Code Prompt (Caveman Ultra)

```
Tryb: caveman ultra. Brak wyjasnien. Czysty kod. PL komentarze.

TASK 1 — response_cache.py (KRYTYCZNY):
- Linia 21: `_RESPONSE_CACHE: dict = {}` → dodaj MAX_ENTRIES=500
- Po kazdym put: if len > MAX_ENTRIES → usun najstarszy wpis (po "stored_at")
- Dodaj cleanup_expired() wywolywany co 100 put-ow

TASK 2 — analyzer.py:
- Usun linia 25: duplikat `from langfuse import Langfuse` (juz jest na linii 17)

TASK 3 — async_utils.py:
- Linia 52,84: zamien `asyncio.get_event_loop()` na:
  ```python
  try:
      loop = asyncio.get_running_loop()
  except RuntimeError:
      loop = asyncio.new_event_loop()
  ```

TASK 4 — Root cleanup (usun pliki):
- brain_graph.html (root, duplikat assets/)
- validation_errors.csv (root, duplikat data/)
- tests/scratch
- data/lf_sig.txt
- data/lf_ver.txt
- data/env_wzor.txt
- src/footstats/gui/src/counter.ts
- src/footstats/gui/src/assets/typescript.svg
- src/footstats/gui/src/assets/vite.svg

TASK 5 — test_response_cache_eviction.py:
```python
"""Testy eviction cache."""
import time
from footstats.core.response_cache import _RESPONSE_CACHE, clear_response_cache

def test_cache_max_entries():
    """Cache nie przekracza MAX_ENTRIES."""
    clear_response_cache()
    # wypelnij cache > MAX_ENTRIES
    from footstats.core.response_cache import MAX_ENTRIES
    for i in range(MAX_ENTRIES + 50):
        _RESPONSE_CACHE[f"test_key_{i}"] = {"data": i, "stored_at": time.time()}
    # Wywolaj cleanup
    from footstats.core.response_cache import _cleanup_expired
    _cleanup_expired()
    assert len(_RESPONSE_CACHE) <= MAX_ENTRIES
    clear_response_cache()

def test_cache_ttl_expiry():
    """Stare wpisy sa usuwane."""
    clear_response_cache()
    _RESPONSE_CACHE["old"] = {"data": 1, "stored_at": time.time() - 9999, "ttl": 10}
    _RESPONSE_CACHE["new"] = {"data": 2, "stored_at": time.time(), "ttl": 600}
    from footstats.core.response_cache import _cleanup_expired
    _cleanup_expired()
    assert "old" not in _RESPONSE_CACHE
    assert "new" in _RESPONSE_CACHE
    clear_response_cache()
```

Kolejnosc: TASK 1 → TASK 2 → TASK 3 → TASK 4 → TASK 5. Commit po kazdym TASK.
```
