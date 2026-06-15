"""Jednorazowy test polaczenia z Sentry. Usage:
    SENTRY_DSN=https://...@....ingest.sentry.io/... python scripts/sentry_test.py
"""
import os
import sys

import sentry_sdk

dsn = os.environ.get("SENTRY_DSN", "")
if not dsn.startswith("https://"):
    sys.exit("SENTRY_DSN nieustawiony lub niepoprawny (musi zaczynac sie od https://)")

sentry_sdk.init(dsn=dsn, environment="test", traces_sample_rate=1.0, default_integrations=False)

sentry_sdk.capture_message("FootStats: testowy event z sentry_test.py", level="info")

try:
    1 / 0
except ZeroDivisionError:
    sentry_sdk.capture_exception()

sentry_sdk.flush()
print("Wyslano: 1 message + 1 exception. Sprawdz Sentry -> Issues (zakres dat: dzis).")
