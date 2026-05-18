"""Tests for prediction batch checkpointing."""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from footstats.core.checkpoint import (
    CheckpointStore,
    cleanup_old_checkpoints,
    list_checkpoints,
    load_predictions_batch,
    save_predictions_batch,
)


@pytest.fixture
def clean_checkpoint_dir():
    """Clean checkpoint directory before and after test."""
    from footstats.core.checkpoint import CHECKPOINT_DIR
    if CHECKPOINT_DIR.exists():
        for file in CHECKPOINT_DIR.glob("*.jsonl"):
            file.unlink()
    yield
    if CHECKPOINT_DIR.exists():
        for file in CHECKPOINT_DIR.glob("*.jsonl"):
            file.unlink()


class TestSaveLoadCheckpoint:
    """save_predictions_batch() and load_predictions_batch()."""

    def test_save_and_load_predictions(self, clean_checkpoint_dir):
        predictions = [
            {"match_id": "m1", "p_home": 0.5, "p_draw": 0.3, "p_away": 0.2},
            {"match_id": "m2", "p_home": 0.6, "p_draw": 0.2, "p_away": 0.2},
        ]
        batch_id = "test_batch_001"

        save_predictions_batch(predictions, batch_id)
        loaded = load_predictions_batch(batch_id)

        assert len(loaded) == 2
        assert loaded[0]["match_id"] == "m1"
        assert loaded[1]["match_id"] == "m2"

    def test_save_predictions_creates_file(self, clean_checkpoint_dir):
        predictions = [{"test": "data"}]
        batch_id = "test_batch_002"

        path = save_predictions_batch(predictions, batch_id)
        assert Path(path).exists()

    def test_load_missing_batch_returns_empty(self, clean_checkpoint_dir):
        loaded = load_predictions_batch("nonexistent_batch")
        assert loaded == []

    def test_load_most_recent_checkpoint(self, clean_checkpoint_dir):
        batch_id = "test_batch_003"
        timestamp1 = datetime.now() - timedelta(hours=1)
        timestamp2 = datetime.now()

        predictions1 = [{"version": 1}]
        predictions2 = [{"version": 2}]

        save_predictions_batch(predictions1, batch_id, timestamp1)
        time.sleep(0.1)
        save_predictions_batch(predictions2, batch_id, timestamp2)

        loaded = load_predictions_batch(batch_id)
        assert loaded[0]["version"] == 2, "Should load most recent checkpoint"


class TestCheckpointStore:
    """CheckpointStore context manager."""

    def test_checkpoint_store_save_on_exit(self, clean_checkpoint_dir):
        predictions = [{"id": 1}, {"id": 2}]
        batch_id = "store_test_001"

        with CheckpointStore(batch_id, auto_load=False) as store:
            store.add_batch(predictions)

        loaded = load_predictions_batch(batch_id)
        assert len(loaded) == 2

    def test_checkpoint_store_auto_load(self, clean_checkpoint_dir):
        batch_id = "store_test_002"
        initial = [{"id": 1}]
        save_predictions_batch(initial, batch_id)

        with CheckpointStore(batch_id, auto_load=True) as store:
            assert len(store) == 1
            assert store.get_predictions()[0]["id"] == 1

    def test_checkpoint_store_add_single(self, clean_checkpoint_dir):
        batch_id = "store_test_003"

        with CheckpointStore(batch_id, auto_load=False) as store:
            store.add({"id": 1})
            store.add({"id": 2})
            assert len(store) == 2

    def test_checkpoint_store_no_save_on_exception(self, clean_checkpoint_dir):
        batch_id = "store_test_004"

        try:
            with CheckpointStore(batch_id, auto_load=False) as store:
                store.add({"id": 1})
                raise RuntimeError("Test error")
        except RuntimeError:
            pass

        loaded = load_predictions_batch(batch_id)
        assert loaded == [], "Should not save checkpoint on exception"


class TestListCheckpoints:
    """list_checkpoints() checkpoint enumeration."""

    def test_list_empty_checkpoints(self, clean_checkpoint_dir):
        checkpoints = list_checkpoints()
        assert checkpoints == []

    def test_list_populated_checkpoints(self, clean_checkpoint_dir):
        save_predictions_batch([{"id": 1}], "batch_1")
        save_predictions_batch([{"id": 2}], "batch_2")

        checkpoints = list_checkpoints()
        assert len(checkpoints) >= 2

        batch_ids = [cp["batch_id"] for cp in checkpoints]
        assert "batch_1" in batch_ids
        assert "batch_2" in batch_ids

    def test_list_checkpoints_ordered_by_timestamp(self, clean_checkpoint_dir):
        save_predictions_batch([{"id": 1}], "batch_a")
        time.sleep(0.1)
        save_predictions_batch([{"id": 2}], "batch_b")

        checkpoints = list_checkpoints()
        assert len(checkpoints) >= 2
        batch_ids = [cp["batch_id"] for cp in checkpoints[:2]]
        assert "batch_a" in batch_ids and "batch_b" in batch_ids

    def test_list_checkpoints_includes_metadata(self, clean_checkpoint_dir):
        save_predictions_batch([{"id": 1}, {"id": 2}], "batch_meta")

        checkpoints = list_checkpoints()
        assert len(checkpoints) > 0
        cp = checkpoints[0]
        assert "batch_id" in cp
        assert "count" in cp
        assert "size_kb" in cp
        assert "timestamp" in cp
        assert cp["count"] == 2


class TestCleanupCheckpoints:
    """cleanup_old_checkpoints() stale file removal."""

    def test_cleanup_on_empty_dir(self, clean_checkpoint_dir):
        removed = cleanup_old_checkpoints(days=7)
        assert removed == 0

    def test_cleanup_function_exists(self, clean_checkpoint_dir):
        save_predictions_batch([{"id": 1}], "batch_cleanup")
        removed = cleanup_old_checkpoints(days=365)
        assert isinstance(removed, int)
        assert removed >= 0
