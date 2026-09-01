"""Log o braku kuponu musi rozroznic, KTO go opróżnił.

ZMIERZONE 01.09 (`footstats-final-bdqxq`). Log powiedzial:

    Faza final: 1 typow powstalo (...), ale kupon NIE zostal zapisany —
    warstwa LLM nie oddala struktury kuponu (kupon_a.zdarzenia puste).

Nieprawda. Kilka linii wyzej, w tym samym przebiegu:

    Usunieto 4 halucynowanych nog:
      Bromley vs Leyton Orient [Handicap +1 Gosc] — brak realnego kursu w Bzzoiro

LLM oddal nogi. Skasowala je NASZA weryfikacja, bo rynek jest poza
`TYP_DO_ODDS_KEY`. Jeden komunikat opisywal dwa rozne stany o roznych naprawach:
"popraw prompt, model nie zwraca struktury" kontra "model typuje rynki, ktorych
nie wyceniamy". Przez pierwszy z nich szukalem bledu nie tam, gdzie byl.
"""
from __future__ import annotations

import logging


# Nazwa w kodzie ma polskie "s" — alias, zeby test byl ASCII-only.
from footstats.daily_agent import _zgloś_brak_kuponu_do_zapisu as _zglos


def _komunikat(caplog) -> str:
    return " ".join(r.getMessage() for r in caplog.records)


def test_gdy_weryfikacja_skasowala_nogi_log_mowi_o_WERYFIKACJI(caplog):
    dane = {
        "top3": [{"mecz": "A vs B", "typ": "1"}],
        "kupon_a": {},
        "_usuniete_nogi": ["Bromley vs Leyton Orient [Handicap +1 Gosc] — brak realnego kursu"],
    }

    with caplog.at_level(logging.WARNING):
        _zglos("final", dane)

    tekst = _komunikat(caplog)
    assert "weryfikacj" in tekst.lower(), f"log nie wskazuje weryfikacji: {tekst}"
    assert "Handicap" in tekst, "log nie podaje, ktory rynek wypadl"
    assert "warstwa LLM nie oddala" not in tekst, (
        "log dalej obwinia LLM, choc to weryfikacja skasowala nogi"
    )


def test_gdy_LLM_nic_nie_oddal_log_mowi_o_LLM(caplog):
    """Kontrola negatywna: nie zamieniamy jednego mylacego komunikatu na drugi."""
    dane = {"top3": [{"mecz": "A vs B", "typ": "1"}], "kupon_a": {}}

    with caplog.at_level(logging.WARNING):
        _zglos("final", dane)

    assert "LLM" in _komunikat(caplog)


def test_pusta_lista_usunietych_to_nie_weryfikacja(caplog):
    """`_usuniete_nogi: []` znaczy 'weryfikacja nic nie wycieta', nie 'brak danych'."""
    dane = {"top3": [{"mecz": "A vs B", "typ": "1"}], "kupon_a": {}, "_usuniete_nogi": []}

    with caplog.at_level(logging.WARNING):
        _zglos("final", dane)

    assert "LLM" in _komunikat(caplog)


def test_zero_typow_dalej_ma_swoj_komunikat(caplog):
    with caplog.at_level(logging.WARNING):
        _zglos("final", {"top3": []})

    tekst = _komunikat(caplog).lower()
    assert "filtr" in tekst or "zero" in tekst or "0 typ" in tekst


def test_weryfikacja_zapisuje_usuniete_nogi_do_dane():
    """Bez tego zapisu log nie ma z czego rozroznic obu stanow."""
    from footstats.daily_agent import _weryfikuj_kupony

    dane = {"top3": [{"mecz": "Nieistniejacy vs Mecz", "typ": "1", "kurs": 2.0}],
            "kupon_a": {"zdarzenia": [{"mecz": "Nieistniejacy vs Mecz", "typ": "1", "kurs": 2.0}]}}

    wynik = _weryfikuj_kupony(dane, indeks={})

    assert wynik.get("_usuniete_nogi"), "usuniete nogi nie trafily do `dane`"
