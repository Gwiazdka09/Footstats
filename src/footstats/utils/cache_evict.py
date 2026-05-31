"""Cache eviction utility — usuwa pliki cache starsze niż N dni."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

_log = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).parent.parent.parent.parent / "cache"


def evict_old_cache(max_days: int = 30, dry_run: bool = False) -> int:
    """Usuwa pliki z cache/ starsze niż max_days. Zwraca liczbę usuniętych plików."""
    if not _CACHE_DIR.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=max_days)
    deleted = 0
    freed_bytes = 0

    for path in _CACHE_DIR.rglob("*"):
        if not path.is_file():
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if mtime < cutoff:
            size = path.stat().st_size
            if not dry_run:
                path.unlink()
            deleted += 1
            freed_bytes += size

    _log.info(
        "cache evict: %d pliki, zwolniono %.1f MB (dry_run=%s)",
        deleted,
        freed_bytes / 1_048_576,
        dry_run,
    )
    return deleted
