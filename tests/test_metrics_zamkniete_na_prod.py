"""`/metrics` na produkcji nie może być otwarte tylko dlatego, że brakuje biblioteki.

ZNALEZISKO (audyt bezpieczeństwa 24.09.2026): bramka wyglądała tak —

    expected = os.getenv("METRICS_TOKEN", "")
    if expected and not hmac.compare_digest(x_metrics_token, expected):
        raise HTTPException(401)

czyli **brak zmiennej = brak ochrony**. Na produkcji `METRICS_TOKEN` nie jest
ustawiony (sprawdzone w `gcloud run services describe`), więc endpoint odpowiada
każdemu. Dziś nie wycieka nic, bo `prometheus_client` nie siedzi w obrazie API
i odpowiedź to `{"status": "metrics-disabled"}` — ochroną jest NIEOBECNOŚĆ
BIBLIOTEKI, nie decyzja. Wystarczy, że trafi do obrazu jako zależność
przechodnia, i wolumen ruchu z listą endpointów staje się publiczny (OWASP API8).

Ten test kotwiczy regułę odwrotnie: na produkcji bez tokenu endpoint MILCZY.
Dev i testy zostają otwarte, bo tam metryki są narzędziem pracy.

404, nie 401: dla kogoś bez tokenu nie ma powodu potwierdzać, że taki endpoint
w ogóle istnieje.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

import footstats.api.main as main


def _wywolaj(token: str = ""):
    return main.metrics_endpoint(x_metrics_token=token)


def test_prod_bez_tokenu_udaje_brak_endpointu(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("METRICS_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        _wywolaj()

    assert exc.value.status_code == 404


def test_prod_z_tokenem_wymaga_zgodnego_naglowka(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("METRICS_TOKEN", "poprawny-token")

    with pytest.raises(HTTPException) as exc:
        _wywolaj("zly-token")
    assert exc.value.status_code == 401

    # Zgodny token przechodzi bramkę. Dalej może wrócić albo payload Prometheusa,
    # albo `metrics-disabled` — zależnie od tego, czy biblioteka jest w środowisku.
    # Testujemy BRAMKĘ, nie obecność `prometheus_client`.
    wynik = _wywolaj("poprawny-token")
    assert wynik is not None


def test_dev_bez_tokenu_zostaje_otwarte(monkeypatch):
    """Lokalnie metryki są narzędziem pracy — zaciśnięcie ich tutaj tylko
    przeszkadza, a nic nie chroni (nie ma ruchu do podglądania)."""
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.delenv("METRICS_TOKEN", raising=False)

    wynik = _wywolaj()
    assert wynik is not None


def test_brak_zmiennej_env_traktowany_jak_produkcja(monkeypatch):
    """`ENV` nieustawione znaczy produkcja — tak samo jak przy `/docs` i `/mcp`.

    Gdyby domyślną wartością był dev, każde środowisko z zapomnianą zmienną
    otwierałoby metryki. Ten kierunek domyślności jest w projekcie ustalony
    (`_ENV = os.environ.get("ENV", "production")` w `api/main`).
    """
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("METRICS_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        _wywolaj()
    assert exc.value.status_code == 404
