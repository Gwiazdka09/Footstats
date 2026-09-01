"""Opis meczu musi pokazac kursy tych rynkow, ktore wolno obstawic.

ZMIERZONE 01.09 — odtworzenie KROKU 3 w konfiguracji PRODUKCYJNEJ
(`daily_agent --faza final`, czyli cel_a=cel_b=None). Model oddal poprawny JSON
z trzema typami w `top3` i PUSTYM `kupon_a`, uzasadniajac to tak:

    "Wszystkie dostepne typy maja pewnosc ponizej 50 %, co czyni je nieoplacalnymi
     przy zalozonych kryteriach. Brak kursow dla rynkow Over/Under i BTTS
     uniemozliwia budowe wartosciowych kuponow."

Mial racje. Kandydat Stoke City vs Norwich City wygladal tak:

    odds  = {"home": 3.12, "draw": 3.44, "away": 2.21,
             "over_2_5": 1.79, "under_2_5": 2.0, "btts": 1.64}
    ML: 1=30% X=27% 2=42% | BTTS=56% | Over2.5=53%
    KURSY: 1=3.12 X=3.44 2=2.21          <- tylko 1X2

`_buduj_opis_meczu` renderowalo `home/draw/away` z szescioklucznikowego slownika.
Rynki, ktore JAKO JEDYNE przechodzily prog pewnosci (BTTS 56%, Over 53%), szly do
modelu bez kursu — a bez kursu nie da sie zbudowac nogi. Rynki z kursem mialy
30-42% i wypadaly na progu. Kupon `phase='final'` nie mogl powstac.

Ze `system_paper` czyta `odds` bezposrednio, ten sam mecz trafial tego dnia na
kupon `phase='system'` jako `Over 2.5 @ 1.79`. Dwie sciezki widzialy inny material.
"""
from __future__ import annotations

import pytest

from footstats.ai.analyzer import _buduj_opis_meczu


def _mecz(**nad) -> dict:
    w = {
        "gospodarz": "Stoke City", "goscie": "Norwich City",
        "liga": "Championship", "data": "2026-09-01", "godzina": "19:00",
        "metoda": "ML",
        "pw": 30.1, "pr": 27.3, "pp": 42.5, "bt": 56.3, "o25": 52.6,
        "odds": {"home": 3.12, "draw": 3.44, "away": 2.21,
                 "over_2_5": 1.79, "under_2_5": 2.0, "btts": 1.64},
        "pred": {},
    }
    w.update(nad)
    return w


@pytest.mark.parametrize("kurs", ["1.79", "2.0", "1.64"])
def test_kursy_over_under_btts_trafiaja_do_opisu(kurs):
    """Bez tych liczb model nie ma z czego zbudowac nogi na rynku >50%."""
    opis = _buduj_opis_meczu(_mecz())

    assert kurs in opis, (
        f"kurs {kurs} nie dotarl do promptu — opis: {opis!r}"
    )


@pytest.mark.parametrize("etykieta,kurs", [("Over", "1.79"), ("Under", "2.0"), ("BTTS", "1.64")])
def test_rynki_sa_nazwane_PRZY_swoim_kursie(etykieta, kurs):
    """Sama liczba nie wystarczy — model musi wiedziec, ktory rynek wycenia.

    Szukamy etykiety W TEJ SAMEJ LINII co kurs. Wersja sprawdzajaca tylko
    `etykieta in opis` przechodzila BEZ naprawy, bo "Over2.5" i "BTTS" stoja
    juz w linii `ML: ... | BTTS=56% | Over2.5=53%` — czyli test byl zielony,
    nie mierzac niczego.
    """
    opis = _buduj_opis_meczu(_mecz())

    linie_z_kursem = [l for l in opis.splitlines() if kurs in l]
    assert linie_z_kursem, f"kurs {kurs} nie dotarl do opisu"
    assert any(etykieta.lower() in l.lower() for l in linie_z_kursem), (
        f"kurs {kurs} jest, ale bez etykiety {etykieta!r} przy nim: {linie_z_kursem}"
    )


def test_kursy_1x2_nietkniete():
    """Kontrola negatywna: dokladamy rynki, nie podmieniamy istniejacych."""
    opis = _buduj_opis_meczu(_mecz())

    for kurs in ("3.12", "3.44", "2.21"):
        assert kurs in opis


def test_brak_kursow_dodatkowych_nie_wywala_opisu():
    """Zrodla czesto oddaja samo 1X2 — to normalny stan, nie awaria."""
    opis = _buduj_opis_meczu(_mecz(odds={"home": 3.12, "draw": 3.44, "away": 2.21}))

    assert "3.12" in opis
    assert "Stoke City" in opis


def test_pusty_slownik_kursow_nie_wywala_opisu():
    opis = _buduj_opis_meczu(_mecz(odds={}))

    assert "Stoke City vs Norwich City" in opis


def test_czesciowe_kursy_pokazuja_to_co_jest():
    """Brak jednego rynku nie moze kasowac pozostalych."""
    opis = _buduj_opis_meczu(_mecz(odds={"home": 3.12, "over_2_5": 1.79}))

    assert "3.12" in opis
    assert "1.79" in opis
