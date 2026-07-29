"""test_closing_odds.py — darmowe kursy zamknięcia z football-data.co.uk.

Po co: `clv_tracker.record_closing_odds` istnieje od dawna, ale nie miał taniego
źródła kursu zamknięcia — API-Football ma budżet 100/dzień i tylko przyszłe mecze.
Tymczasem CSV football-data.co.uk (już pobierany przez FootballDataSource, z cache)
ma 132 kolumny, w tym **PSCH/PSCD/PSCA = closing Pinnacle** oraz Avg/Max i O/U.

Dlaczego to ważne: bicie linii zamknięcia to jedyny uczciwy test, czy model ma edge.
Trafność sama w sobie nic nie mówi, jeśli kursy były gorsze niż rynkowe.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

import footstats.scrapers.closing_odds as co

# Nagłówek skrócony do kolumn, których używamy (realny plik ma 132).
_CSV = (
    "Date,HomeTeam,AwayTeam,FTHG,FTAG,"
    "PSCH,PSCD,PSCA,AvgCH,AvgCD,AvgCA,MaxCH,MaxCD,MaxCA,PC>2.5,PC<2.5\n"
    "15/08/2025,Liverpool,Bournemouth,4,2,1.29,6.55,9.75,1.29,6.02,8.68,1.32,6.60,10.0,1.55,2.45\n"
    "16/08/2025,Aston Villa,Newcastle,0,0,2.32,3.63,3.07,2.38,3.41,2.93,2.45,3.70,3.20,2.05,1.80\n"
)

# Wiersz bez Pinnacle — ma zejść na średnią rynkową.
_CSV_BEZ_PINNACLE = (
    "Date,HomeTeam,AwayTeam,PSCH,PSCD,PSCA,AvgCH,AvgCD,AvgCA\n"
    "15/08/2025,Liverpool,Bournemouth,,,,1.30,6.00,8.70\n"
)


def _patch_csv(tekst):
    return patch.object(co, "_csv_ligi", return_value=tekst)


# ── wybór źródła kursu ──────────────────────────────────────────────────────


def test_preferuje_pinnacle():
    """Pinnacle to najostrzejszy bukmacher — najlepszy benchmark CLV."""
    with _patch_csv(_CSV):
        k = co.kursy_zamkniecia("Liverpool", "Bournemouth", "2025-08-15")

    assert k is not None
    assert k["home"] == pytest.approx(1.29)
    assert k["draw"] == pytest.approx(6.55)
    assert k["away"] == pytest.approx(9.75)
    assert k["zrodlo"] == "pinnacle-closing"


def test_schodzi_na_srednia_gdy_brak_pinnacle():
    with _patch_csv(_CSV_BEZ_PINNACLE):
        k = co.kursy_zamkniecia("Liverpool", "Bournemouth", "2025-08-15")

    assert k["home"] == pytest.approx(1.30)
    assert k["zrodlo"] == "rynek-avg-closing"


def test_dolacza_over_under_gdy_jest():
    with _patch_csv(_CSV):
        k = co.kursy_zamkniecia("Liverpool", "Bournemouth", "2025-08-15")
    assert k["over_2_5"] == pytest.approx(1.55)
    assert k["under_2_5"] == pytest.approx(2.45)


# ── dopasowanie meczu ───────────────────────────────────────────────────────


def test_dopasowuje_mimo_roznic_w_pisowni():
    """CSV ma 'Aston Villa', my możemy mieć 'Aston Villa FC'."""
    with _patch_csv(_CSV):
        assert co.kursy_zamkniecia("Aston Villa FC", "Newcastle", "2025-08-16") is not None


def test_nie_myli_kierunku_meczu():
    """Odwrócone drużyny to inny mecz — zły kierunek zafałszowałby CLV."""
    with _patch_csv(_CSV):
        assert co.kursy_zamkniecia("Bournemouth", "Liverpool", "2025-08-15") is None


def test_zla_data_to_brak_trafienia():
    with _patch_csv(_CSV):
        assert co.kursy_zamkniecia("Liverpool", "Bournemouth", "2025-08-16") is None


def test_nieznany_mecz_zwraca_none():
    with _patch_csv(_CSV):
        assert co.kursy_zamkniecia("Realny Madryt", "Barcelona", "2025-08-15") is None


# ── odporność ───────────────────────────────────────────────────────────────


def test_brak_csv_jest_graceful():
    with _patch_csv(None):
        assert co.kursy_zamkniecia("Liverpool", "Bournemouth", "2025-08-15") is None


def test_smieciowe_kursy_pomijane():
    csv = "Date,HomeTeam,AwayTeam,PSCH,PSCD,PSCA\n15/08/2025,A,B,nieliczba,1.0,x\n"
    with _patch_csv(csv):
        assert co.kursy_zamkniecia("A", "B", "2025-08-15") is None


def test_kurs_ponizej_jedynki_odrzucony():
    """Kurs <= 1.0 jest niemożliwy — lepiej brak niż śmieć psujący CLV."""
    csv = "Date,HomeTeam,AwayTeam,PSCH,PSCD,PSCA\n15/08/2025,A,B,0.95,3.0,4.0\n"
    with _patch_csv(csv):
        assert co.kursy_zamkniecia("A", "B", "2025-08-15") is None


def test_sezon_z_daty():
    """football-data.co.uk trzyma pliki per sezon w formacie YYZZ (2526 = 2025/26)."""
    assert co._sezon_z_daty("2025-08-15") == "2526"
    assert co._sezon_z_daty("2026-03-10") == "2526"   # marzec = wciąż sezon 25/26
    assert co._sezon_z_daty("2026-08-01") == "2627"
