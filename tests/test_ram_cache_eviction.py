import pytest
import time
from datetime import datetime, timedelta
from footstats.utils.cache import _cache_set, _cache_get, _ram_cache_cleanup, _RAM_CACHE, MAX_RAM_ENTRIES


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear RAM cache before each test."""
    _RAM_CACHE.clear()
    yield
    _RAM_CACHE.clear()


def test_max_entries_overflow_evicts_oldest():
    """Test that when MAX_RAM_ENTRIES is exceeded, oldest entry is evicted."""
    # Fill cache to MAX_RAM_ENTRIES
    for i in range(MAX_RAM_ENTRIES):
        _cache_set(f"key_{i}", f"data_{i}")
        time.sleep(0.001)  # Ensure different timestamps

    assert len(_RAM_CACHE) == MAX_RAM_ENTRIES

    # Add one more — should evict oldest
    _cache_set("key_new", "data_new")

    assert len(_RAM_CACHE) == MAX_RAM_ENTRIES
    assert "key_0" not in _RAM_CACHE  # Oldest should be gone
    assert "key_new" in _RAM_CACHE


def test_ttl_expiry_cache_miss():
    """Test that expired entries return None on get."""
    _cache_set("expiring_key", "data")

    # Verify it exists
    assert _cache_get("expiring_key") == "data"

    # Manually set old timestamp to expire it
    _RAM_CACHE["expiring_key"]["ts"] = datetime.now() - timedelta(hours=1)

    # Should miss now
    assert _cache_get("expiring_key") is None


def test_cleanup_removes_expired_entries():
    """Test that _ram_cache_cleanup removes expired entries."""
    _cache_set("fresh", "data")
    _cache_set("old", "data")

    # Age the 'old' entry
    _RAM_CACHE["old"]["ts"] = datetime.now() - timedelta(hours=2)

    assert len(_RAM_CACHE) == 2

    # Cleanup with 60 min TTL
    _ram_cache_cleanup(ttl_minutes=60)

    # Old should be gone, fresh should remain
    assert "fresh" in _RAM_CACHE
    assert "old" not in _RAM_CACHE
    assert len(_RAM_CACHE) == 1
