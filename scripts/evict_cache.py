"""CLI wrapper for cache eviction. Uruchamiać ręcznie lub z crona."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from footstats.utils.cache_evict import evict_old_cache  # noqa: E402

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evict old cache files")
    parser.add_argument("--days", type=int, default=30, help="Wiek pliku w dniach (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Tylko pokazuj, nie usuwaj")
    args = parser.parse_args()
    n = evict_old_cache(max_days=args.days, dry_run=args.dry_run)
    print(f"Łącznie: {n} pliki")
