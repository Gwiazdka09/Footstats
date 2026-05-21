# Phase 3: QUALITY (Poisson Smoothing, Caching, Checkpointing)

**Goal:** Improve Poisson prediction robustness, reduce API response latency via HTTP caching, and support batch prediction checkpointing.

---

## Task 3.1: Poisson Smoothing & Edge Case Handling

**Module:** `src/footstats/core/poisson.py` (extend `_macierz()`)

**Changes:**
- Add Laplace (add-one) smoothing to prevent zero probabilities
- Handle extreme lambda values (very low/high attack/defense)
- Smooth probability distributions to avoid numerical instability
- Document smoothing rationale

**Tests:** `tests/test_poisson_edge_cases.py` (5 tests)
- test_extreme_low_lambdas (lambda < 0.1)
- test_extreme_high_lambdas (lambda > 5.0)
- test_zero_probability_smoothing
- test_matrix_normalization (ensure sum = 1.0)
- test_btts_valid_range (0-1)

**Acceptance:** All tests pass, no NaN/Inf in matrix output.

---

## Task 3.2: HTTP Response Caching with Cache-Control Headers

**Module:** `src/footstats/core/response_cache.py` (new)

**Exports:**
- `cached_response(ttl_seconds=300, vary_by=[])` — decorator for GET endpoints
- `cache_key_builder(request, vary_by)` — build cache key from request
- `clear_response_cache(prefix)` — invalidate cache by pattern

**Features:**
- Cache-Control: max-age=300, must-revalidate
- ETag support for conditional requests (If-None-Match)
- Vary header for different query params/auth
- In-memory store with TTL

**Integration:**
- Decorate predict/coupon endpoints in API routes
- Set cache TTL = 5-15 min for predictions
- Invalidate on user profile changes

**Tests:** `tests/test_response_cache.py` (6 tests)
- test_cache_hit_within_ttl
- test_cache_miss_after_ttl
- test_etag_304_response
- test_vary_param_separate_cache
- test_auth_vary (different users separate cache)
- test_cache_invalidation_pattern

**Acceptance:** Response time <50ms for cached endpoints.

---

## Task 3.3: Pipeline Checkpointing (Prediction State Snapshots)

**Module:** `src/footstats/core/checkpoint.py` (new)

**Exports:**
- `CheckpointStore` — saves/loads prediction batches
- `save_predictions_batch(predictions, batch_id, timestamp)` — to `.cache/predictions/{batch_id}.jsonl`
- `load_predictions_batch(batch_id)` → list[dict]
- `list_checkpoints(limit=20)` → sorted by timestamp
- `cleanup_old_checkpoints(days=7)` — auto-cleanup

**Usage:**
- Called after batch prediction (e.g., league predictions)
- Allows resuming interrupted batch jobs
- Can replay predictions for audit trail

**Tests:** `tests/test_checkpoint.py` (5 tests)
- test_save_load_predictions
- test_checkpoint_persistence
- test_cleanup_old_checkpoints
- test_list_checkpoints_ordered
- test_missing_checkpoint_graceful

**Acceptance:** Predictions recoverable after process crash.

---

## Implementation Order
1. Task 3.1 (Poisson smoothing) — lowest risk, isolated
2. Task 3.2 (HTTP caching) — moderate risk, API surface
3. Task 3.3 (checkpointing) — moderate risk, new module

---

## Test Coverage Target
- Total tests: ~16 (5 + 6 + 5)
- Coverage: >85% of new modules
- All existing Phase 1+2 tests must still pass
