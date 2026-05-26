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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path("cache/checkpoints")


def _ensure_checkpoint_dir() -> None:
    """Create checkpoint directory if needed."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


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
    _ensure_checkpoint_dir()
    timestamp = timestamp or datetime.now()
    ts_str = timestamp.isoformat().replace(":", "-")
    filename = CHECKPOINT_DIR / f"{batch_id}_{ts_str}.jsonl"

    try:
        with open(filename, "w", encoding="utf-8") as f:
            for pred in predictions:
                f.write(json.dumps(pred, ensure_ascii=False) + "\n")
        logger.info(f"Checkpoint saved: {filename} ({len(predictions)} predictions)")
        return str(filename)
    except Exception as e:
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
    _ensure_checkpoint_dir()
    matching = sorted(
        CHECKPOINT_DIR.glob(f"{batch_id}_*.jsonl"),
        key=lambda p: p.name,
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
    except Exception as e:
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
    _ensure_checkpoint_dir()
    checkpoints = []

    for file in sorted(
        CHECKPOINT_DIR.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
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
        except Exception:
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
    _ensure_checkpoint_dir()
    cutoff = datetime.now() - timedelta(days=days)
    removed = 0

    for file in CHECKPOINT_DIR.glob("*.jsonl"):
        mtime = datetime.fromtimestamp(file.stat().st_mtime)
        if mtime < cutoff:
            try:
                file.unlink()
                removed += 1
            except Exception as e:
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
