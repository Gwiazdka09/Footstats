# Phase 4: PRODUCTION (Integration, Observability, Resilience, Deployment)

**Priority ranking:** Integration (critical) → Observability (high) → Resilience (medium) → Deployment (nice-to-have)

---

## Task 4.1: API Integration (CRITICAL)

**Goal:** Wire Phase 3 modules (response caching, checkpointing) into live API routes.

### 4.1a: Response Caching on Prediction Endpoints

**Routes to decorate:**
- `/api/predict/{match_id}` → cache 10 min (vary_by: ["user_id"])
- `/api/coupon/predict` → cache 5 min (vary_by: ["league", "user_id"])
- `/api/settings` → cache 30 min (vary_by: ["user_id"])

**Implementation:**
- Import `@cached_response` from footstats.core.response_cache
- Add decorator above each endpoint handler
- Set TTL based on data freshness needs
- Test: verify Cache-Control headers, cache hits

**Files to modify:**
- src/footstats/api/routes/coupons.py (predict endpoint)
- src/footstats/api/routes/settings.py (settings endpoint)
- src/footstats/api/main.py (if has predict endpoint)

**Tests:** 5 tests
- test_predict_endpoint_has_cache_header
- test_cache_hit_same_user_match
- test_cache_miss_different_user
- test_settings_cached
- test_cache_control_max_age_correct

### 4.1b: Checkpoint Integration in Batch Prediction

**Where:** Batch prediction job (if exists) or create new endpoint

**Implementation:**
- Wrap batch prediction loop in `CheckpointStore(batch_id, auto_load=True)` context
- Call `store.add(prediction)` for each predicted match
- On exception, checkpoint NOT saved (transactional)
- On success, checkpoint saved automatically

**Files to modify/create:**
- scripts/predict_batch.py (if exists) or new src/footstats/api/routes/batch.py

**Tests:** 4 tests
- test_batch_prediction_checkpointed
- test_batch_resume_from_checkpoint
- test_checkpoint_not_saved_on_error
- test_checkpoint_metadata_stored

**Acceptance:** Batch prediction recoverable after process crash.

---

## Task 4.2: Observability (HIGH)

**Goal:** Wire MetricsCollector into API request handlers.

### 4.2a: Metrics Collection in Request Handlers

**Metrics to track:**
- request_count (by endpoint, by method)
- request_latency (by endpoint, histogram)
- scraper_errors (by scraper, by error type)
- cache_hits vs misses
- checkpoint_save_latency

**Implementation:**
- Import MetricsCollector from footstats.core.logging_config
- Wrap endpoint handlers with timing/counting logic
- Increment counters on request start/end
- Record latency in handler middleware

**Files to modify:**
- src/footstats/api/main.py (add metrics middleware)
- src/footstats/core/logging_config.py (extend MetricsCollector)

**Tests:** 4 tests
- test_metrics_request_count_increments
- test_metrics_latency_recorded
- test_metrics_per_endpoint_breakdown
- test_prometheus_endpoint_format

### 4.2b: Prometheus Endpoint

**Endpoint:** GET /metrics

**Format:**
```
# HELP footstats_request_count Total API requests
# TYPE footstats_request_count counter
footstats_request_count{endpoint="/predict",method="POST"} 1234
footstats_request_latency{endpoint="/predict",le=0.1} 450
```

**Implementation:**
- Create /metrics route that outputs MetricsCollector state as Prometheus text format
- Use standard Prometheus naming (footstats_*_total, footstats_*_seconds)

---

## Task 4.3: Resilience Testing (MEDIUM)

**Goal:** Validate system stability under load.

### 4.3a: Load Testing

**Tools:** locust or Apache JMeter

**Scenarios:**
- Sustained 10 req/sec for 5 min
- Burst 50 req/sec for 30 sec
- Cache hit rate monitoring
- Memory growth tracking

**Tests:** 3 tests
- test_load_sustained_10rps
- test_load_burst_50rps
- test_memory_stable_after_load

### 4.3b: Stress Testing

**Scenarios:**
- Max concurrent requests (until 503)
- Cache eviction under memory pressure
- Checkpoint cleanup on full disk
- Graceful degradation

---

## Task 4.4: Deployment Configuration (NICE-TO-HAVE)

**Goal:** Prepare for production deployment.

### 4.4a: Docker Setup

**Files:**
- Dockerfile (multi-stage, optimized)
- docker-compose.yml (app + postgres + redis optional)
- .dockerignore

### 4.4b: CI/CD Pipeline

**Tools:** GitHub Actions or similar

**Pipeline:**
1. Unit tests (pytest)
2. Type check (pyright)
3. Security scan (bandit)
4. Build Docker image
5. Push to registry

---

## Implementation Order

1. **Task 4.1** (CRITICAL) — API integration: cache + checkpoint
2. **Task 4.2** (HIGH) — Observability: metrics collection + Prometheus
3. **Task 4.3** (MEDIUM) — Resilience: load/stress testing
4. **Task 4.4** (OPTIONAL) — Deployment: Docker + CI/CD

---

## Success Criteria

- All Phase 4.1 tests passing (9 total)
- Cache headers present on all decorated endpoints
- Batch prediction recoverable from checkpoint
- Prometheus /metrics endpoint returns valid format
- Load testing shows <100ms p95 latency
- System handles 50 concurrent requests without OOM
