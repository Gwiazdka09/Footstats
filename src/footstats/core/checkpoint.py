"""
checkpoint.py – Pipeline checkpointing for prediction batch recovery.

Exports:
    CheckpointStore — class for saving/loading prediction batches
    save_predictions_batch(predictions, batch_id, timestamp)
    load_predictions_batch(batch_id)
    list_checkpoints(limit)
    cleanup_old_checkpoints(days)
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from footstats.utils.paths import katalog_cache

logger = logging.getLogger(__name__)

# Domyslnie pod wspolnym korzeniem cache (`utils.paths`), zeby jedna zmienna
# izolowala CALY cache procesu. `CHECKPOINT_DIR` dalej wygrywa — na nim opiera sie
# fikstura `clean_checkpoint_dir` w tests/test_checkpoint.py.
_NAZWA_KATALOGU = "checkpoints"


def _checkpoint_dir() -> Path:
    """
    Katalog checkpointów, czytany z env przy KAŻDYM wywołaniu (nie raz przy imporcie) —
    ten sam wzorzec co `SELECTION_SKIP_BTTS` w `core/system_paper.py`. Pozwala testom
    podmienić katalog na `tmp_path` (izolacja równoległych przebiegów pytest) bez
    zmiany domyślnej ścieżki produkcyjnej.
    """
    return Path(os.getenv("CHECKPOINT_DIR") or katalog_cache(_NAZWA_KATALOGU))


def _ensure_checkpoint_dir() -> Path:
    """Create checkpoint directory if needed and return its path."""
    checkpoint_dir = _checkpoint_dir()
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    return checkpoint_dir


def _parse_checkpoint_timestamp(stem: str) -> datetime:
    """
    Odtwarza znacznik czasu zakodowany w nazwie pliku (odwrotność transformacji
    z `save_predictions_batch`: `timestamp.isoformat().replace(":", "-")`).

    `batch_id` sam może zawierać `_` (np. "league_pl_2026w20"), więc granicę między
    nim a znacznikiem czasu wyznacza OSTATNI `_` w nazwie (ts_str nigdy nie zawiera
    `_`) — ta sama konwencja, co przy odczycie `batch_id` w `list_checkpoints`.

    Podnosi ValueError, gdy nazwa nie parsuje się wg tego schematu; wołający
    (`_checkpoint_sort_key`) łapie to i loguje awaryjne przejście na mtime.
    """
    last_underscore = stem.rfind("_")
    ts_part = stem[last_underscore + 1:] if last_underscore != -1 else stem
    if last_underscore == -1 or "T" not in ts_part:
        raise ValueError(f"Nie znaleziono znacznika czasu w nazwie: {stem}")
    date_part, _, time_part = ts_part.partition("T")
    iso_candidate = f"{date_part}T{time_part.replace('-', ':')}"
    return datetime.fromisoformat(iso_candidate)


def _checkpoint_sort_key(path: Path) -> datetime:
    """
    Klucz sortowania „najnowszy pierwszy".

    Priorytet ma znacznik zakodowany w nazwie pliku (intencja writera, rozdzielczość
    mikrosekundowa) — `st_mtime` systemu plików ma rozdzielczość rzędu milisekund i przy
    kilku checkpointach zapisanych szybko po sobie regularnie daje remisy, przy których
    sortowanie zwraca arbitralną kolejność zamiast faktycznie najnowszego pliku. mtime
    zostaje wyłącznie jako awaryjny tiebreak dla nazw, których nie da się sparsować.
    """
    try:
        return _parse_checkpoint_timestamp(path.stem)
    except ValueError as e:
        logger.warning(
            f"Checkpoint {path.name}: nie sparsowano znacznika czasu z nazwy ({e}), "
            "używam mtime jako awaryjnego klucza sortowania"
        )
        return datetime.fromtimestamp(path.stat().st_mtime)


def save_predictions_batch(
    predictions: list[dict[str, Any]],
    batch_id: str,
    timestamp: Optional[datetime] = None,
) -> str:
    """
    Save prediction batch to disk.

    Args:
        predictions: List of prediction dicts
        batch_id: Unique batch identifier (e.g., "league_pl_2026w20")
        timestamp: Optional timestamp (defaults to now)

    Returns:
        Path to saved checkpoint file
    """
    checkpoint_dir = _ensure_checkpoint_dir()
    timestamp = timestamp or datetime.now()
    ts_str = timestamp.isoformat().replace(":", "-")
    filename = checkpoint_dir / f"{batch_id}_{ts_str}.jsonl"

    try:
        with open(filename, "w", encoding="utf-8") as f:
            for pred in predictions:
                f.write(json.dumps(pred, ensure_ascii=False, default=str) + "\n")
        logger.info(f"Checkpoint saved: {filename} ({len(predictions)} predictions)")
        return str(filename)
    except (OSError, ValueError) as e:
        logger.error(f"Failed to save checkpoint {batch_id}: {e}")
        raise


def load_predictions_batch(batch_id: str) -> list[dict[str, Any]]:
    """
    Load most recent prediction batch for batch_id.

    Args:
        batch_id: Batch identifier to load

    Returns:
        List of prediction dicts, or empty list if not found
    """
    checkpoint_dir = _ensure_checkpoint_dir()
    matching = sorted(
        checkpoint_dir.glob(f"{batch_id}_*.jsonl"),
        key=_checkpoint_sort_key,
        reverse=True,
    )

    if not matching:
        logger.warning(f"No checkpoint found for batch_id: {batch_id}")
        return []

    newest = matching[0]
    try:
        predictions = []
        with open(newest, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    predictions.append(json.loads(line))
        logger.info(f"Checkpoint loaded: {newest} ({len(predictions)} predictions)")
        return predictions
    except (OSError, ValueError) as e:
        logger.error(f"Failed to load checkpoint {newest}: {e}")
        return []


def list_checkpoints(limit: int = 20) -> list[dict[str, Any]]:
    """
    List recent checkpoints.

    Args:
        limit: Max number of checkpoints to return

    Returns:
        List of dicts with checkpoint info (path, batch_id, size, timestamp)
    """
    checkpoint_dir = _ensure_checkpoint_dir()
    checkpoints = []

    for file in sorted(
        checkpoint_dir.glob("*.jsonl"),
        key=_checkpoint_sort_key,
        reverse=True,
    )[:limit]:
        try:
            stem = file.stem
            if "_" not in stem:
                continue
            last_underscore = stem.rfind("_")
            batch_id = stem[:last_underscore]

            size_kb = file.stat().st_size // 1024
            mtime = datetime.fromtimestamp(file.stat().st_mtime)
            with open(file, "r", encoding="utf-8") as f:
                count = sum(1 for _ in f)
            checkpoints.append({
                "file": file.name,
                "batch_id": batch_id,
                "count": count,
                "size_kb": size_kb,
                "timestamp": mtime.isoformat(),
            })
        except (OSError, ValueError):
            pass

    return checkpoints


def cleanup_old_checkpoints(days: int = 7) -> int:
    """
    Remove checkpoint files older than N days.

    Args:
        days: Age threshold

    Returns:
        Number of files removed
    """
    checkpoint_dir = _ensure_checkpoint_dir()
    cutoff = datetime.now() - timedelta(days=days)
    removed = 0

    for file in checkpoint_dir.glob("*.jsonl"):
        mtime = datetime.fromtimestamp(file.stat().st_mtime)
        if mtime < cutoff:
            try:
                file.unlink()
                removed += 1
            except OSError as e:
                logger.error(f"Failed to remove checkpoint {file}: {e}")

    if removed > 0:
        logger.info(f"Cleaned up {removed} old checkpoints")

    return removed


class CheckpointStore:
    """Context manager for batch prediction checkpointing."""

    def __init__(self, batch_id: str, auto_load: bool = True):
        """
        Initialize checkpoint store.

        Args:
            batch_id: Unique batch identifier
            auto_load: If True, load existing checkpoint on enter
        """
        self.batch_id = batch_id
        self.auto_load = auto_load
        self.predictions: list[dict[str, Any]] = []
        self.start_time = datetime.now()

    def __enter__(self):
        """Load existing checkpoint if available."""
        if self.auto_load:
            self.predictions = load_predictions_batch(self.batch_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Save checkpoint on exit (unless exception)."""
        if exc_type is None:
            save_predictions_batch(self.predictions, self.batch_id, self.start_time)

    def add(self, prediction: dict[str, Any]) -> None:
        """Add single prediction to batch."""
        self.predictions.append(prediction)

    def add_batch(self, predictions: list[dict[str, Any]]) -> None:
        """Add multiple predictions to batch."""
        self.predictions.extend(predictions)

    def get_predictions(self) -> list[dict[str, Any]]:
        """Get current predictions in batch."""
        return self.predictions

    def __len__(self) -> int:
        """Get number of predictions in batch."""
        return len(self.predictions)
