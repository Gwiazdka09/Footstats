#!/usr/bin/env bash
# run_job.sh — entrypoint Cloud Run Job. Dispatch wg JOB_PHASE (final|evening).
# Używane przez Dockerfile.jobs. Lokalnie: JOB_PHASE=final ./scripts/run_job.sh
set -euo pipefail

PHASE="${JOB_PHASE:-final}"
echo "[run_job] JOB_PHASE=${PHASE} start $(date -u +%FT%TZ)"

case "${PHASE}" in
  final)
    python -m footstats.daily_agent --faza final
    ;;
  draft)
    python -m footstats.daily_agent --faza draft --system-paper
    ;;
  evening)
    python -m footstats.evening_agent
    ;;
  *)
    echo "[run_job] Nieznana JOB_PHASE='${PHASE}' (final|draft|evening)" >&2
    exit 2
    ;;
esac

echo "[run_job] JOB_PHASE=${PHASE} koniec exit=$? $(date -u +%FT%TZ)"
