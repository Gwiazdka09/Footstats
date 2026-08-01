"""test_coupon_settlement_para.py — dopasowanie pary drużyn przy rozliczaniu z fdb.

PO CO: `_znajdz_wynik_fdb` bierze wynik z football-data.org i rozlicza nim kupon.
Liczyło ŚREDNIĄ podobieństw obu drużyn przy progu 0.70, więc jedno idealne
trafienie przepychało złe dopasowanie drugiej strony:

    kupon "Legia – Lech Poznań"  vs  mecz "Legia – Lechia Gdańsk"
    1.00 + 0.58 = średnia 0.79 >= 0.70  ->  ROZLICZAŁO

Historia tej funkcji jest pouczająca: naprawiałem ją już raz w tej sesji,
podmieniając surowy `SequenceMatcher` na `team_similarity` (kolizja Manchester
United / City). Poprawka była dobra, ale dotyczyła tylko funkcji podobieństwa —
**uśrednianie zostało**, więc druga droga do tego samego błędu przetrwała.
Wyłapał ją dopiero rozszerzony strażnik `test_dopasowanie_nazw_audyt.py`.

Poprawka: `min` zamiast średniej — OBIE drużyny muszą przejść próg.
"""
from __future__ import annotations

import pytest

from footstats.core.coupon_settlement import _znajdz_wynik_fdb


def _mecz(home: str, away: str, hg: int = 2, ag: int = 1) -> dict:
    return {
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
        "score": {"fullTime": {"home": hg, "away": ag}},
    }


# ── sedno błędu ─────────────────────────────────────────────────────────────

def test_inny_klub_o_podobnej_nazwie_nie_rozlicza():
    """REGRESJA: Lech Poznań i Lechia Gdańsk to dwa różne kluby Ekstraklasy,
    oba grające z Legią. Średnia 0.79 przepuszczała cudzy wynik."""
    mecze = [_mecz("Legia Warszawa", "Lechia Gdansk", 4, 0)]

    assert _znajdz_wynik_fdb("Legia Warszawa", "Lech Poznan", mecze) is None


def test_ten_sam_klub_inny_rywal_nie_rozlicza():
    mecze = [_mecz("Rapid Wien", "Austria Wien", 3, 3)]

    assert _znajdz_wynik_fdb("Rapid Wien", "Rheindorf Altach", mecze) is None


def test_kolizja_gospodarza_tez_odrzucona():
    mecze = [_mecz("Lechia Gdansk", "Lech Poznan", 1, 1)]

    assert _znajdz_wynik_fdb("Legia Warszawa", "Lech Poznan", mecze) is None


def test_rezerwy_nie_rozliczaja_pierwszego_zespolu():
    mecze = [_mecz("Legia II", "Lech II", 5, 0)]

    assert _znajdz_wynik_fdb("Legia", "Lech", mecze) is None


def test_derby_nie_myla_klubow():
    """Ta sama rodzina błędów co Manchester United / City."""
    mecze = [_mecz("Manchester City", "Arsenal", 2, 0)]

    assert _znajdz_wynik_fdb("Manchester United", "Arsenal", mecze) is None


# ── poprawne dopasowania muszą przeżyć ──────────────────────────────────────

def test_dokladne_nazwy_rozliczaja():
    mecze = [_mecz("Legia Warszawa", "Lech Poznan", 2, 1)]

    assert _znajdz_wynik_fdb("Legia Warszawa", "Lech Poznan", mecze) == "2-1"


def test_warianty_nazw_rozliczaja():
    """Skrócony zapis to nadal ten sam mecz — poprawka nie może go zablokować."""
    mecze = [_mecz("Manchester United", "Manchester City", 1, 3)]

    assert _znajdz_wynik_fdb("Man Utd", "Man City", mecze) == "1-3"


def test_wybiera_najlepsze_dopasowanie():
    mecze = [
        _mecz("Legia Warszawa", "Lechia Gdansk", 4, 0),
        _mecz("Legia Warszawa", "Lech Poznan", 2, 1),
    ]

    assert _znajdz_wynik_fdb("Legia Warszawa", "Lech Poznan", mecze) == "2-1"


# ── dane niekompletne ───────────────────────────────────────────────────────

@pytest.mark.parametrize("hg,ag", [(None, 1), (2, None), (None, None)])
def test_mecz_bez_wyniku_nie_rozlicza(hg, ag):
    """Brak gola w danych to niekompletny wpis, nie remis 0-0."""
    mecze = [_mecz("Legia Warszawa", "Lech Poznan", hg, ag)]

    assert _znajdz_wynik_fdb("Legia Warszawa", "Lech Poznan", mecze) is None


def test_pusta_lista_meczow():
    assert _znajdz_wynik_fdb("Legia", "Lech", []) is None


def test_wpis_bez_nazw_druzyn_pomijany():
    """Pusta nazwa po normalizacji nie może pasować do wszystkiego."""
    mecze = [{"homeTeam": {}, "awayTeam": {}, "score": {"fullTime": {"home": 1, "away": 0}}}]

    assert _znajdz_wynik_fdb("Legia", "Lech", mecze) is None
