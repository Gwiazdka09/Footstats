"""Endpointy sięgające po zewnętrzne wyniki muszą mieć dłuższy limit czasu.

`_TimeoutMiddleware` tnie żądanie po 10 s, chyba że ścieżka jest na liście
`_LONG_RUNNING_PATHS` (120 s). Lista jest ręczna, więc rozjeżdża się po cichu:
`/api/cron/settle-manual` do 24.08 rozliczał wyłącznie z naszej bazy i mieścił się
w 10 s. Po włączeniu D5 (`MANUAL_SETTLE_EXTERNAL=1`) zaczął odpytywać API-Football
i FlashScore dla każdej nogi bez naszej predykcji — pierwsze wywołanie na produkcji
wróciło `{"detail": "Request timeout", "timeout_s": 10.0}` (HTTP 504).

Groźne jest to, że Cloud Scheduler ma `attemptDeadline: 180s`, więc 504 z naszego
własnego middleware wygląda z jego strony jak zwykła awaria endpointu i idzie
w retry — a rozliczanie nie rusza z miejsca. Zero testów pilnowało tej listy.
"""
from __future__ import annotations

import pytest

from footstats.api.main import _LONG_RUNNING_PATHS, _LONG_RUNNING_TIMEOUT


@pytest.mark.parametrize("sciezka", [
    "/api/cron/settle",
    "/api/cron/settle-manual",
    "/api/cron/draft",
    "/api/coupons/settle",
])
def test_endpointy_z_zewnetrznymi_zrodlami_maja_dluzszy_limit(sciezka: str):
    """Każdy z nich może wołać `_find_leg_result` albo scraper — 10 s nie wystarczy."""
    assert sciezka in _LONG_RUNNING_PATHS, (
        f"{sciezka} sięga po zewnętrzne dane, a dostanie limit 10 s → 504"
    )


def test_dlugi_limit_miesci_sie_w_deadline_schedulera():
    """Schedulery mają `attemptDeadline: 180s`. Limit aplikacji musi być KRÓTSZY —
    inaczej to Scheduler przerywa połączenie w trakcie zapisu do bazy, zamiast
    dostać uczciwą odpowiedź."""
    assert _LONG_RUNNING_TIMEOUT < 180.0


def test_lista_zawiera_tylko_istniejace_sciezki():
    """Literówka w ścieżce jest niewidoczna: wpis nie pasuje do niczego, a endpoint
    dostaje po cichu 10 s — dokładnie ten sam objaw co brak wpisu."""
    from footstats.api.main import app

    znane = {r.path for r in app.routes if hasattr(r, "path")}
    nieznane = _LONG_RUNNING_PATHS - znane

    assert not nieznane, f"w liscie sa sciezki, ktorych aplikacja nie zna: {nieznane}"
