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
