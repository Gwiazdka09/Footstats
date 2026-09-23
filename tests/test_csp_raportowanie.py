"""CSP w trybie Report-Only musi mieć GDZIE raportować.

ZNALEZISKO (audyt bezpieczeństwa 24.09.2026): nagłówek na produkcji to
`Content-Security-Policy-Report-Only` (flaga `CSP_ENFORCE` nieustawiona), a jego
treść nie zawiera ani `report-uri`, ani `report-to`. Przeglądarka wypisuje
naruszenie do konsoli użytkownika i na tym koniec — do nas nie dociera nic.

Dlaczego to nie jest drobiazg: uzasadnienie trybu raportującego brzmiało „nie
mamy jeszcze ani jednego pomiaru naruszeń, więc wymuszanie byłoby zgadywaniem".
Bez kanału raportowania ten warunek NIGDY się nie spełni — polityka zostaje
w trybie, który nic nie blokuje i nic nie mierzy, czyli jest dekoracją. To ten
sam kształt co „zielone testy, martwa produkcja": mechanizm wygląda na obecny,
a nie robi nic.

Naprawa daje raportowi adres (`/api/csp-report`) i loguje naruszenia. Po kilku
dniach wiadomo, czy wymuszenie (`CSP_ENFORCE=1`) cokolwiek zepsuje — i to jest
decyzja właściciela projektu, nie automatu.

ODPORNOŚĆ NA ZASYPANIE LOGÓW: endpoint jest publiczny z konieczności (raport
wysyła przeglądarka, bez tokenu), więc logujemy tylko trzy pola, każde ucięte,
a globalny limiter (60/min per klient) obowiązuje jak wszędzie.
"""
from __future__ import annotations

import json
import logging

from starlette.testclient import TestClient

import footstats.api.main as main


def _client() -> TestClient:
    return TestClient(main.app)


def test_polityka_wskazuje_adres_raportu():
    assert "report-uri /api/csp-report" in main._CSP


def test_endpoint_przyjmuje_raport_przegladarki():
    """Format `application/csp-report` — tak wysyła Chrome/Safari."""
    raport = {"csp-report": {
        "document-uri": "https://footstats.example/app",
        "violated-directive": "script-src",
        "blocked-uri": "https://zly.example/x.js",
    }}
    r = _client().post("/api/csp-report", content=json.dumps(raport),
                       headers={"Content-Type": "application/csp-report"})
    assert r.status_code == 204


def test_endpoint_loguje_trzy_pola(caplog):
    raport = {"csp-report": {
        "document-uri": "https://footstats.example/app",
        "violated-directive": "style-src-elem",
        "blocked-uri": "inline",
    }}
    with caplog.at_level(logging.WARNING, logger="footstats.api.main"):
        _client().post("/api/csp-report", content=json.dumps(raport),
                       headers={"Content-Type": "application/csp-report"})

    tresc = " ".join(r.getMessage() for r in caplog.records)
    assert "style-src-elem" in tresc
    assert "inline" in tresc
    assert "/app" in tresc


def test_smiec_nie_wywraca_endpointu():
    """Publiczny endpoint dostanie kiedyś śmieci — od skanera albo pomyłki.

    Odpowiedź musi zostać 204: 500 na publicznym wejściu to darmowy sygnał
    „tu coś się wywraca", a 400 zachęca do dalszego szturchania.
    """
    c = _client()
    assert c.post("/api/csp-report", content=b"{nie-json",
                  headers={"Content-Type": "application/csp-report"}).status_code == 204
    assert c.post("/api/csp-report", content=b"[]",
                  headers={"Content-Type": "application/csp-report"}).status_code == 204
    assert c.post("/api/csp-report", content=b"",
                  headers={"Content-Type": "application/csp-report"}).status_code == 204


def test_ogromny_raport_nie_trafia_caly_do_logu(caplog):
    """Bez ucięcia jedno żądanie potrafi wepchnąć megabajt do logów Cloud Run."""
    raport = {"csp-report": {
        "document-uri": "https://footstats.example/" + "a" * 5000,
        "violated-directive": "img-src",
        "blocked-uri": "data:" + "b" * 5000,
    }}
    with caplog.at_level(logging.WARNING, logger="footstats.api.main"):
        _client().post("/api/csp-report", content=json.dumps(raport),
                       headers={"Content-Type": "application/csp-report"})

    tresc = " ".join(r.getMessage() for r in caplog.records)
    assert len(tresc) < 1000, f"log ma {len(tresc)} znaków — brak ucięcia"
