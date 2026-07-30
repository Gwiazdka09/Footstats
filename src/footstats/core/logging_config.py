"""
logging_config.py – strukturalne logi JSON (stdlib) + metryki Prometheus.

Formatter mieszkal wczesniej w `api/main.py`, wiec logi JSON mialo WYLACZNIE
API. Joby (`daily_agent`, `evening_agent`) leca w Cloud Run Jobs i logowaly
plaskim tekstem — nie dalo sie po nich filtrowac w Cloud Logging, mimo ze to
one wykonuja caly pipeline predykcji. Przeniesione tutaj 2026-07-30, oba
wejscia korzystaja z jednego zrodla.

Wczesniej byl tu `setup_logging()` oparty na loguru — nikt go nie wolal,
usuniety razem z jedyna zaleznoscia od loguru.

Uzycie w jobie:
    from footstats.core.logging_config import skonfiguruj_logi_json
    skonfiguruj_logi_json()
"""

import json
import logging
from contextvars import ContextVar

# Ustawiane przez _RequestIDMiddleware w API. W jobach zostaje puste —
# to normalne, joby nie obsluguja requestow.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class JsonFormatter(logging.Formatter):
    """Jedna linia JSON na wpis — format czytany przez Cloud Logging."""

    def format(self, record: logging.LogRecord) -> str:
        ładunek = {
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
            "time": self.formatTime(record),
            "request_id": request_id_var.get(""),
        }
        # Poprzednia wersja nadpisywala format() i NIGDY nie siegala po exc_info,
        # wiec `log.error(..., exc_info=True)` gubil caly traceback — bledy
        # w logach byly jednolinijkowe i bezuzyteczne. Pole dodajemy tylko gdy
        # wyjatek faktycznie jest, zeby nie puchly zwykle wpisy.
        if record.exc_info:
            ładunek["exc"] = self.formatException(record.exc_info)
        return json.dumps(ładunek, ensure_ascii=False)


def skonfiguruj_logi_json(level: int = logging.INFO) -> None:
    """Wpina JsonFormatter na root loggerze. Idempotentne.

    Powtorne wywolanie nie dokłada handlera — inaczej kazda linia logu
    pojawialaby sie podwojnie (a joby i API potrafia importowac sie wzajemnie).
    """
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        root.setLevel(level)
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)


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
