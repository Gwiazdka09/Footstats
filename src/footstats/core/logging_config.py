"""
logging_config.py – Structured JSON logging with loguru.

Setup:
    from footstats.core.logging_config import setup_logging
    setup_logging()
"""

import logging
import sys
from pathlib import Path

try:
    from loguru import logger as loguru_logger
    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False


def setup_logging(json_sink: str = "logs/footstats.jsonl", level: str = "INFO") -> None:
    """
    Configure structured JSON logging with loguru.

    Args:
        json_sink: Path to JSON log file
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    if not HAS_LOGURU:
        logging.warning("[Logging] loguru not installed, using stdlib logging")
        return

    # Create logs directory
    Path(json_sink).parent.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    loguru_logger.remove()

    # Add JSON sink (production)
    loguru_logger.add(
        json_sink,
        format="{message}",
        serialize=True,
        level=level,
        rotation="100 MB",
        retention="7 days",
    )

    # Add console sink (colorized, development)
    loguru_logger.add(
        sys.stdout,
        format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=level,
    )


# Optional: Prometheus metrics setup (stubs for now)
try:
    from prometheus_client import Counter, Histogram
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False


class MetricsCollector:
    """Simple metrics collection (Prometheus-compatible)."""

    def __init__(self):
        if not HAS_PROMETHEUS:
            self.enabled = False
            return

        self.enabled = True
        self.request_count = Counter(
            "footstats_requests_total",
            "Total API requests",
            ["endpoint", "status"],
        )
        self.request_latency = Histogram(
            "footstats_request_duration_seconds",
            "API request latency",
            ["endpoint"],
        )
        self.scraper_errors = Counter(
            "footstats_scraper_errors_total",
            "Total scraper errors",
            ["scraper"],
        )

    def record_request(self, endpoint: str, status: int, latency: float) -> None:
        if self.enabled:
            self.request_count.labels(endpoint=endpoint, status=status).inc()
            self.request_latency.labels(endpoint=endpoint).observe(latency)



# Global metrics instance
metrics = MetricsCollector()
