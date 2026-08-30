"""FlashScore przestaje byc zablokowany za martwym API-Football.

ZMIERZONE 30.08. Petla enrichmentu robila `continue`, gdy API-Football nie
zwrocil meczu — a wywolanie FlashScore stoi NIZEJ w tej samej petli. Konto AF
jest zawieszone od 01.08, wiec dzialajace, niezalezne zrodlo nie bylo wolane
ANI RAZU przez miesiac. Fallback zabezpieczony za martwym zrodlem glownym.

Log produkcyjny 29.08: `Final enrichment: 0/6 kandydatow wzbogacono` — zero
bierze sie dokladnie z tego `continue`.

Kontekst kosztu: `scrape_match_with_search` odpala Playwrighta na kazde
wywolanie, wiec odblokowanie musi miec limit. Bez niego przebieg bez sedziego
z zadnego zrodla wystartowalby przegladarke dla kazdego kandydata.
"""
from __future__ import annotations

import logging

import pytest

from footstats.core import daily_phases as dp


@pytest.fixture(autouse=True)
def _bez_sieci(monkeypatch):
    """Zaden test w tym pliku nie ma prawa dotknac AF, FotMoba ani bazy sedziow."""
    monkeypatch.setattr(dp, "_wzbogac_team_news", lambda k: None)
    monkeypatch.setattr("footstats.scrapers.referee_db.referee_signal",
                        lambda name: "NEUTRALNY")
    monkeypatch.setattr("footstats.scrapers.referee_db.get_referee", lambda name: None)


def _bez_meczow_w_af(monkeypatch):
    """API-Football oddaje pusta liste — dokladnie to robi zawieszone konto."""
    class _Odp:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"response": []}

    monkeypatch.setattr("requests.get", lambda *a, **k: _Odp())


def test_flashscore_jest_wolany_gdy_AF_nie_zna_meczu(monkeypatch):
    """Sedno: brak meczu w AF ma pomijac CZESCI ZALEZNE OD AF, nie caly wiersz."""
    _bez_meczow_w_af(monkeypatch)
    wolania = []

    def _fs(gosp, gosc):
        wolania.append((gosp, gosc))
        return {"success": True, "referee": "Szymon Marciniak",
                "absences": {"home": [], "away": []}, "stadium": "Stadion"}

    monkeypatch.setattr(dp, "_flashscore_szczegoly", _fs)

    kandydaci = [{"gospodarz": "Lech", "goscie": "Legia"}]
    dp._enrichuj_finalna_faza(kandydaci, "klucz-ktory-nic-nie-zwraca")

    assert wolania == [("Lech", "Legia")]
    assert kandydaci[0]["referee_name"] == "Szymon Marciniak"


def test_absencje_flashscore_docieraja_do_kandydata(monkeypatch):
    _bez_meczow_w_af(monkeypatch)
    monkeypatch.setattr(dp, "_flashscore_szczegoly", lambda g, a: {
        "success": True, "referee": "Szymon Marciniak",
        "absences": {"home": [{"name": "Kowalski", "reason": "kontuzja"}],
                     "away": []},
    })

    k = {"gospodarz": "Lech", "goscie": "Legia"}
    dp._enrichuj_finalna_faza([k], "klucz")

    assert "Kowalski" in k.get("fs_absencje_g", "")


def test_limit_wywolan_playwrighta_jest_pilnowany(monkeypatch, caplog):
    """Bez limitu przebieg bez sedziego z zadnego zrodla startowalby
    przegladarke dla kazdego kandydata."""
    _bez_meczow_w_af(monkeypatch)
    wolania = []
    monkeypatch.setattr(dp, "_flashscore_szczegoly",
                        lambda g, a: (wolania.append(g), {"success": False})[1])
    monkeypatch.setattr(dp, "_MAX_FLASHSCORE_NA_PRZEBIEG", 2)

    kandydaci = [{"gospodarz": f"Dom{i}", "goscie": f"Gosc{i}"} for i in range(6)]
    with caplog.at_level(logging.INFO):
        dp._enrichuj_finalna_faza(kandydaci, "klucz")

    assert len(wolania) == 2, f"Playwright odpalony {len(wolania)} razy zamiast 2"
    assert "limit" in caplog.text.lower()


def test_kandydat_z_sedzia_nie_odpala_przegladarki(monkeypatch):
    """FotMob dal juz sedziego — FlashScore nie ma po co startowac."""
    _bez_meczow_w_af(monkeypatch)
    wolania = []
    monkeypatch.setattr(dp, "_flashscore_szczegoly",
                        lambda g, a: (wolania.append(g), {"success": False})[1])

    dp._enrichuj_finalna_faza(
        [{"gospodarz": "Lech", "goscie": "Legia", "referee_name": "Ktos"}], "klucz")

    assert wolania == []


def test_licznik_wzbogaconych_liczy_takze_te_bez_AF(monkeypatch, caplog):
    """`Final enrichment: 0/6` bylo prawda tylko dlatego, ze `continue` wypadal
    przed inkrementacja. Kandydat wzbogacony przez FlashScore ma sie liczyc."""
    _bez_meczow_w_af(monkeypatch)
    monkeypatch.setattr(dp, "_flashscore_szczegoly", lambda g, a: {
        "success": True, "referee": "Szymon Marciniak",
        "absences": {"home": [], "away": []}})

    kandydaci = [{"gospodarz": f"D{i}", "goscie": f"G{i}"} for i in range(3)]
    dp._enrichuj_finalna_faza(kandydaci, "klucz")

    assert all(k.get("referee_name") for k in kandydaci)
