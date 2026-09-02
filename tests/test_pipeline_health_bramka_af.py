"""`pipeline-health` musi pokazywać stan bramki API-Football.

PO CO: zamknięta bramka wygląda w logach IDENTYCZNIE jak źródło, które nie ma
dziś meczów — obie sytuacje to puste `[]`. 2026-09-02 dwa razy trzeba było zgadywać,
czy API milczy, czy jest wyłączone, i za drugim razem odpowiedź brzmiała „konto
zawieszone", czego z samych logów nie dało się odczytać.

To NIE jest powód do alarmu: wyłączone źródło bywa świadomą decyzją, a potok
działa bez niego (31 kuponów 02.09 przy koncie zawieszonym od 01.08). Ma być
widoczne w odpowiedzi, nie zapalać Telegrama.
"""
from __future__ import annotations

import pytest

from footstats.api.routes import status as status_routes


@pytest.fixture
def zdrowa_baza(monkeypatch):
    """Zdrowy stan bazy — testujemy pole `apisports`, nie logikę alarmu."""
    from datetime import datetime

    class _Row(dict):
        def __getitem__(self, k):
            return dict.get(self, k)

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            teraz = datetime.now()
            if "FROM predictions" in sql and "MAX(created_at)" in sql:
                return _Wynik(_Row(ostatnia=teraz))
            if "ostatni_kupon" in sql:
                return _Wynik(_Row(ostatni_kupon=teraz))
            return _Wynik(_Row(n=0, ile=0))

    class _Wynik:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

        def fetchall(self):
            return []

    monkeypatch.setattr(status_routes, "_connect", lambda: _Conn())
    monkeypatch.setattr(status_routes, "_sprawdz_cron_secret", lambda _s: None)
    monkeypatch.setattr(status_routes, "_wyslij_alarm", lambda *a, **k: False)


def test_zdrowy_stan_pokazuje_bramke_otwarta(zdrowa_baza, monkeypatch):
    monkeypatch.delenv("APISPORTS_ENABLED", raising=False)
    odp = status_routes.pipeline_health(x_cron_secret="x")

    assert odp["apisports"]["wlaczone"] is True
    assert odp["apisports"]["zawieszone_w_tym_procesie"] is False


def test_wylaczone_zrodlo_widac_ale_nie_alarmuje(zdrowa_baza, monkeypatch):
    """Rozróżnienie, którego brakowało: „wyłączone" ≠ „brak meczów"."""
    monkeypatch.setenv("APISPORTS_ENABLED", "0")
    odp = status_routes.pipeline_health(x_cron_secret="x")

    assert odp["apisports"]["wlaczone"] is False
    assert odp["ok"] is True, "wylaczone zrodlo to nie awaria potoku"
    assert odp["powody"] == []


def test_zatrzask_po_blokadzie_konta_jest_widoczny(zdrowa_baza, monkeypatch):
    """Najważniejszy przypadek: dostawca zablokował konto, a my o tym wiemy."""
    from footstats.core import apisports_gate

    monkeypatch.delenv("APISPORTS_ENABLED", raising=False)
    apisports_gate.zglos_odpowiedz(
        {"errors": {"access": "Your account is suspended, check on dashboard."}}
    )
    odp = status_routes.pipeline_health(x_cron_secret="x")

    assert odp["apisports"]["zawieszone_w_tym_procesie"] is True
    assert odp["apisports"]["wlaczone"] is False
    # Zatrzask odróżnia się od ręcznego wyłącznika — inaczej nie da się
    # powiedzieć, czy ktoś wyłączył źródło, czy dostawca nas zablokował.
    assert odp["apisports"]["env_wylacznik"] is None
