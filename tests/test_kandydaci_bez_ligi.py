"""Kandydat bez nazwy ligi omija whitelistę — i nikt tego nie liczy.

KONTEKST (24-25.08.2026): 20 kuponów z 15.08 przepadło, bo żadne źródło nie
oddało wyniku. Rozliczalność per rozgrywki pokazała, gdzie jest dziura — ligi
krajowe 84-100%, ale **Carabao Cup 5/38 (13%)**, Champions League 6/19,
Europa 10/25. Puchary są nierozliczalne, odkąd konto API-Football wisi
zawieszone od 01.08.

I tu zagadka: pucharów NIE MA na whiteliście (98 pozycji, `ENFORCE=True`),
a mimo to pucharowe kupony powstały. `_pre_filtruj_ligi` ma udokumentowany wyjątek:

    # Kandydaci bez nazwy ligi (np. API-Football) — zawsze zachowywani.
    if liga and LIGA_WHITELIST_ENFORCE and ...

Pusta nazwa ligi omija whitelistę CAŁKOWICIE. To prawdopodobna droga, którą
puchary wchodzą do kuponów — ale to hipoteza, a nie pomiar, bo ta gałąź nie
zostawia po sobie ŻADNEGO śladu. Dokładnie ten sam kształt, co gałąź blacklisty
przed 13.08: milczała, więc diagnoza wymagała grzebania w bazie.

Ten test wymusza policzenie i zgłoszenie. Jeden dzień produkcji rozstrzygnie,
czy hipoteza jest prawdziwa — zamiast kolejnego zgadywania.

Wyjątek zostaje: odrzucanie kandydatów bez ligi zabiłoby źródła, które nazwy
nie podają. Chodzi o WIDOCZNOŚĆ, nie o zaostrzenie filtra.
"""
from __future__ import annotations

import logging

import pytest

from footstats.core.daily_filters import _pre_filtruj_ligi


def _kandydat(liga: str) -> dict:
    return {"gospodarz": "A", "goscie": "B", "liga": liga, "pw": 50.0}


@pytest.fixture(autouse=True)
def whitelist_wlaczona(monkeypatch):
    """Wyjątek dotyczy wyłącznie stanu z ENFORCE=True — inaczej nie ma czego omijać."""
    import footstats.config as cfg

    monkeypatch.setattr(cfg, "LIGA_WHITELIST_ENFORCE", True, raising=False)
    monkeypatch.setattr(cfg, "LIGI_WHITELIST", ["Premier League"], raising=False)


def test_kandydat_bez_ligi_wciaz_przechodzi():
    """Zachowanie NIE zmienia się — źródła bez nazwy ligi muszą dalej działać."""
    wynik = _pre_filtruj_ligi([_kandydat(""), _kandydat("Premier League")])

    assert len(wynik) == 2


def test_omijajacy_whiteliste_sa_policzeni(caplog):
    """Bez licznika ta gałąź jest niewidzialna."""
    import footstats.core.daily_filters as df

    with caplog.at_level(logging.WARNING, logger=df.logger.name):
        _pre_filtruj_ligi([_kandydat(""), _kandydat(""), _kandydat("Premier League")])

    tresc = " ".join(r.getMessage() for r in caplog.records)
    assert tresc, "kandydaci omijajacy whiteliste nie zostawili sladu"
    assert "2" in tresc, f"log nie podaje ILU ominelo whiteliste: {tresc}"


def test_brak_omijajacych_nie_generuje_szumu(caplog):
    """Log przy każdym przebiegu przestaje cokolwiek znaczyć."""
    import footstats.core.daily_filters as df

    with caplog.at_level(logging.WARNING, logger=df.logger.name):
        _pre_filtruj_ligi([_kandydat("Premier League")])

    assert not [r for r in caplog.records if "whitelist" in r.getMessage().lower()]
