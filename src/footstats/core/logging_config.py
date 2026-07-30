"""
logging_config.py – zbieranie metryk (Prometheus, opcjonalne).

Modul NIE konfiguruje juz logowania. Zawieral `setup_logging()` opartego na
loguru, ale nikt go nie wolal, a logi JSON i tak produkuje `_JsonFormatter`
(`api/main.py:42`) na czystym stdlib. Funkcja usunieta 2026-07-30 razem
z jedynym uzyciem zaleznosci `loguru` w projekcie.

DO ZROBIENIA: joby (`daily_agent` / `evening_agent`) nadal loguja plaskim
tekstem — `_JsonFormatter` obsluguje wylacznie API. Wlasciwy fix to wyciagnac
ten formatter do wspolnego modulu, a nie przywracac loguru.
"""

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
