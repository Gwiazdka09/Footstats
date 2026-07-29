"""test_terminarz.py — terminarz lig z darmowych źródeł (openfootball + OpenLigaDB).

Po co: dotychczas system widział wyłącznie mecze z najbliższych 48h (horyzont
draftu). Terminarz całego sezonu daje: przygotowanie pod ważne kolejki/finały,
odliczanie do startu ligi i zakładkę „Terminarz" w GUI.

Źródła (oba darmowe, bez klucza):
  - openfootball (GitHub raw JSON) — 20 lig na sezon, pełne terminarze + kolejki.
  - OpenLigaDB — ligi niemieckie, dodatkowa redundancja.
"""
from __future__ import annotations

from unittest.mock import patch

import footstats.scrapers.terminarz as tm

_OPENFOOTBALL = {
    "name": "English Premier League 2025/26",
    "matches": [
        {"round": "Matchday 1", "date": "2025-08-16", "time": "20:00",
         "team1": "Manchester United FC", "team2": "Fulham FC",
         "score": {"ht": [0, 0], "ft": [1, 0]}},
        {"round": "Matchday 2", "date": "2026-09-20", "time": "17:30",
         "team1": "Arsenal FC", "team2": "Chelsea FC"},
        {"round": "Matchday 3", "date": "bledna-data",
         "team1": "X", "team2": "Y"},
        {"round": "Matchday 4", "date": "2026-09-21", "team1": "", "team2": "Z"},
    ],
}

_OPENLIGADB = [
    {
        "matchDateTime": "2026-09-25T20:30:00",
        "team1": {"teamName": "FC Bayern Munchen"},
        "team2": {"teamName": "RB Leipzig"},
        "matchIsFinished": False,
        "group": {"groupName": "5. Spieltag"},
    }
]


# ── openfootball ────────────────────────────────────────────────────────────


def test_normalizuje_mecze_openfootball():
    with patch.object(tm, "_pobierz_json", return_value=_OPENFOOTBALL):
        mecze = tm.pobierz_terminarz("en.1", "2025-26")

    assert len(mecze) == 2  # zły format daty i pusta drużyna odpadają
    m = mecze[0]
    assert m["gospodarz"] == "Manchester United FC"
    assert m["goscie"] == "Fulham FC"
    assert m["data"] == "2025-08-16"
    assert m["godzina"] == "20:00"
    assert m["kolejka"] == "Matchday 1"
    assert m["rozegrany"] is True
    assert m["wynik"] == "1-0"


def test_mecz_bez_wyniku_jest_nierozegrany():
    with patch.object(tm, "_pobierz_json", return_value=_OPENFOOTBALL):
        mecze = tm.pobierz_terminarz("en.1", "2025-26")
    przyszly = [m for m in mecze if m["data"] == "2026-09-20"][0]
    assert przyszly["rozegrany"] is False
    assert przyszly["wynik"] is None


def test_schodzi_na_poprzedni_sezon_gdy_biezacy_nieopublikowany():
    """
    openfootball publikuje z opóźnieniem — w lipcu 2026 katalog `2026-27/` dawał
    same 404. Lepiej pokazać terminarz o sezon starszy niż pustą zakładkę.
    """
    proby: list[str] = []

    def _fake(url: str):
        proby.append(url)
        return _OPENFOOTBALL if "2025-26" in url else None

    with patch.object(tm, "_pobierz_json", side_effect=_fake), \
         patch.object(tm, "biezacy_sezon", return_value="2026-27"):
        mecze = tm.pobierz_terminarz("en.1")

    assert len(proby) == 2 and "2026-27" in proby[0] and "2025-26" in proby[1]
    assert len(mecze) == 2


def test_jawny_sezon_nie_ma_fallbacku():
    """Gdy user prosi o konkretny sezon, nie podmieniamy mu go po cichu."""
    with patch.object(tm, "_pobierz_json", return_value=None) as mock:
        tm.pobierz_terminarz("en.1", "2019-20")
    assert mock.call_count == 1


def test_przeglad_lig_zachowuje_fallback_sezonu():
    """
    Regresja: `przeglad_lig` rozwiązywał sezon PRZED wywołaniem `pobierz_terminarz`,
    więc ten uznawał go za wybór jawny i tracił fallback → przegląd wracał pusty
    mimo dostępnych danych o sezon starszych.
    """
    def _fake(url: str):
        return _OPENFOOTBALL if "2025-26" in url else None

    with patch.object(tm, "_pobierz_json", side_effect=_fake), \
         patch.object(tm, "biezacy_sezon", return_value="2026-27"):
        przeglad = tm.przeglad_lig(limit_na_lige=1)

    assert przeglad, "przegląd nie może być pusty gdy poprzedni sezon jest dostępny"


def test_poprzedni_sezon():
    assert tm.poprzedni_sezon("2026-27") == "2025-26"
    assert tm.poprzedni_sezon("2000-01") == "1999-00"


def test_wynik_toleruje_warianty_ksztaltu():
    """
    Regresja z żywych danych: openfootball miesza kształty `score` w jednym repo —
    raz dict {"ft": [1,0]}, raz sama lista [1,0], raz para score1/score2.
    Wcześniej lista wywalała pobieranie AttributeError-em.
    """
    assert tm._wynik_ft({"score": {"ft": [1, 0]}}) == [1, 0]
    assert tm._wynik_ft({"score": [2, 3]}) == [2, 3]
    assert tm._wynik_ft({"score1": 0, "score2": 4}) == [0, 4]
    assert tm._wynik_ft({"score": {"ht": [0, 0]}}) == []
    assert tm._wynik_ft({}) == []
    assert tm._wynik_ft({"score": ["x", "y"]}) == []
    assert tm._wynik_ft({"score": [1]}) == []


def test_nieznana_liga_zwraca_pusto():
    assert tm.pobierz_terminarz("nie.ma.takiej", "2025-26") == []


def test_brak_danych_jest_graceful():
    with patch.object(tm, "_pobierz_json", return_value=None):
        assert tm.pobierz_terminarz("en.1", "2025-26") == []


def test_smieciowy_json_jest_graceful():
    with patch.object(tm, "_pobierz_json", return_value={"nic": 1}):
        assert tm.pobierz_terminarz("en.1", "2025-26") == []


# ── OpenLigaDB ──────────────────────────────────────────────────────────────


def test_normalizuje_mecze_openligadb():
    with patch.object(tm, "_pobierz_json", return_value=_OPENLIGADB):
        mecze = tm.pobierz_terminarz_openligadb("bl1", 2026)

    assert len(mecze) == 1
    m = mecze[0]
    assert m["gospodarz"] == "FC Bayern Munchen"
    assert m["data"] == "2026-09-25"
    assert m["godzina"] == "20:30"
    assert m["kolejka"] == "5. Spieltag"
    assert m["rozegrany"] is False


# ── widok „co nas czeka" ────────────────────────────────────────────────────


def test_nadchodzace_filtruje_przeszlosc_i_sortuje():
    mecze = [
        {"data": "2026-09-25", "godzina": "20:30", "gospodarz": "C", "goscie": "D", "rozegrany": False},
        {"data": "2025-01-01", "godzina": "12:00", "gospodarz": "A", "goscie": "B", "rozegrany": True},
        {"data": "2026-09-20", "godzina": "17:30", "gospodarz": "E", "goscie": "F", "rozegrany": False},
    ]
    wynik = tm.nadchodzace(mecze, od="2026-09-01")
    assert [m["gospodarz"] for m in wynik] == ["E", "C"]


def test_nadchodzace_respektuje_limit():
    mecze = [
        {"data": f"2026-09-{d:02d}", "godzina": "12:00", "gospodarz": f"T{d}",
         "goscie": "X", "rozegrany": False}
        for d in range(10, 20)
    ]
    assert len(tm.nadchodzace(mecze, od="2026-09-01", limit=3)) == 3


def test_start_sezonu_to_pierwszy_mecz():
    mecze = [
        {"data": "2026-09-25", "gospodarz": "A", "goscie": "B", "rozegrany": False},
        {"data": "2026-08-14", "gospodarz": "C", "goscie": "D", "rozegrany": False},
    ]
    assert tm.start_sezonu(mecze) == "2026-08-14"
    assert tm.start_sezonu([]) is None


def test_dni_do_startu():
    assert tm.dni_do("2026-08-14", dzis="2026-07-29") == 16
    assert tm.dni_do("2026-07-29", dzis="2026-07-29") == 0
    assert tm.dni_do("2026-07-01", dzis="2026-07-29") == -28
    assert tm.dni_do("bledna", dzis="2026-07-29") is None


def test_lista_lig_ma_czytelne_nazwy():
    """GUI pokazuje nazwy, nie kody plików."""
    assert tm.LIGI["en.1"]["nazwa"] == "Premier League"
    assert tm.LIGI["de.1"]["nazwa"] == "Bundesliga"
    assert all("nazwa" in v and "kraj" in v for v in tm.LIGI.values())


def test_brak_ekstraklasy_jest_jawny():
    """
    openfootball NIE ma polskiej ligi (sprawdzone 2026-07-29: 20 plików, zero pl.*).
    Ekstraklasa musi iść z API-Football. Ten test pilnuje, żeby nikt nie dopisał
    `pl.1` do LIGI w przekonaniu, że źródło ją obsługuje.
    """
    assert "pl.1" not in tm.LIGI
    assert "Ekstraklasa" not in {v["nazwa"] for v in tm.LIGI.values()}
