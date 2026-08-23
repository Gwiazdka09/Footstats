"""M5 — flaga wyłączająca BTTS z puli selekcji `najlepszy_typ`.

DLACZEGO W OGOLE: `najlepszy_typ` bierze argmax po surowym prawdopodobienstwie
z szesciu typow naraz (1/X/2/Over/Under/BTTS). Rynek DWUSTRONNY ma zawsze jedna
strone >=50% z definicji, trojstronny dzieli prawdopodobienstwo na trzy — dlatego
2-way wygrywa argmax w 74% meczow (zmierzone 17.08 na 1755 meczach,
`test_selekcja_stronniczosc_rynkow.py`). BTTS trafia do kuponu z powodu
STRUKTURY reguly, nie dlatego, ze mamy tam przewage.

A przewagi tam nie mamy: walk-forward n=15 460 daje model 53.2% przy czestosci
bazowej 54.4% (Brier 0.2496 vs 0.2480) — "zawsze BTTS tak" BIJE model.

CZEGO TA FLAGA *NIE* MA ZA SOBA — powiedziane wprost, bo wpis M5 w TODO twierdzil
inaczej: nie ma pomiaru ROI pokazujacego, ze bez BTTS jest lepiej. Liczby
-10,7% / -13,5% / -14,7% cytowane w M5 to TRZY REGULY SELEKCJI na tych samych
danych (argmax p / argmax EV / argmax przewagi), a nie warianty z BTTS i bez.

Pomiar na produkcji 23.08 (wspolne okno 2026-05-06..2026-08-16, n=147):
BTTS n=13, trafnosc 23.1%, ROI -51.9%; bez BTTS ROI +2.9% wobec -2.0% ogolem.
Kierunek sie zgadza, ale n=13 to szum: jeden zaklad wiecej przesuwa ROI o 14,5 pp,
a test dwumianowy po korekcie na wybor najgorszego z czterech rynkow daje p=0,111.

DLATEGO DOMYSLNIE FLAGA JEST WYLACZONA. Zostaje gotowa do flipu, gdy uzbiera sie
probka — tak samo jak `SELECTION_MIN_CONF` i `LEAGUE_GATING`.
"""
from __future__ import annotations

import pytest

from footstats.core import system_paper
from footstats.core.system_paper import najlepszy_typ


def _mecz(**nadpisz) -> dict:
    """Kandydat, w ktorym BTTS ma NAJWYZSZE p — czyli argmax go wybierze."""
    dane = {
        "gospodarz": "A", "goscie": "B",
        "pw": 45.0, "pr": 25.0, "pp": 30.0,
        "o25": 55.0,
        "bt": 70.0,
        "odds": {"home": 2.2, "draw": 3.4, "away": 3.0,
                 "over_2_5": 1.9, "under_2_5": 1.9, "btts": 1.8},
    }
    dane.update(nadpisz)
    return dane


# ── domyslnie nic sie nie zmienia ───────────────────────────────────────────

def test_domyslnie_btts_dalej_w_puli(monkeypatch):
    """Flaga ma byc zbudowana WYLACZONA — pomiar jej jeszcze nie uzasadnia."""
    monkeypatch.delenv("SELECTION_SKIP_BTTS", raising=False)

    wynik = najlepszy_typ(_mecz())

    assert wynik is not None
    assert wynik[1] == "BTTS", "domyslne zachowanie zmienione bez pomiaru"


# ── flaga wlaczona ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("wartosc", ["1", "true", "True"])
def test_flaga_wyrzuca_btts_z_puli(monkeypatch, wartosc: str):
    monkeypatch.setenv("SELECTION_SKIP_BTTS", wartosc)

    wynik = najlepszy_typ(_mecz())

    assert wynik is not None, "wyrzucenie BTTS nie moze zostawic meczu bez typu"
    assert wynik[1] != "BTTS"


def test_po_wyrzuceniu_wybiera_kolejny_najlepszy(monkeypatch):
    """Nie 'brak typu', tylko nastepny w kolejnosci — inaczej flaga po cichu
    kasowalaby zaklady zamiast je przekierowywac."""
    monkeypatch.setenv("SELECTION_SKIP_BTTS", "1")

    prob, tip, _ = najlepszy_typ(_mecz())

    # p: BTTS 70 (wyrzucone) > Over 2.5 55 > pw 45 = Under 2.5 45 > pp 30 > pr 25
    assert tip == "Over 2.5", tip
    assert prob == pytest.approx(55.0)


def test_mecz_gdzie_btts_i_tak_nie_wygrywal_bez_zmian(monkeypatch):
    """Flaga nie moze ruszac meczow, w ktorych BTTS nie byl argmaxem."""
    mecz = _mecz(bt=20.0, pw=80.0)

    monkeypatch.delenv("SELECTION_SKIP_BTTS", raising=False)
    bez_flagi = najlepszy_typ(mecz)
    monkeypatch.setenv("SELECTION_SKIP_BTTS", "1")
    z_flaga = najlepszy_typ(mecz)

    assert bez_flagi == z_flaga


def test_brak_innego_legalnego_typu_daje_None(monkeypatch):
    """Gdy BTTS byl JEDYNYM typem przechodzacym filtry, po wyrzuceniu ma byc None,
    a nie typ ponizej progu przemycony tylnymi drzwiami."""
    monkeypatch.setenv("SELECTION_SKIP_BTTS", "1")
    mecz = _mecz(pw=10.0, pr=10.0, pp=10.0, o25=50.0,
                 odds={"btts": 1.8})   # tylko BTTS ma kurs

    assert najlepszy_typ(mecz) is None


# ── zachowanie flagi ────────────────────────────────────────────────────────

@pytest.mark.parametrize("wartosc", ["0", "", "nie", "false"])
def test_smieciowa_wartosc_nie_wlacza_flagi(monkeypatch, wartosc: str):
    """Literowka w env nie moze po cichu zmienic reguly selekcji na produkcji."""
    monkeypatch.setenv("SELECTION_SKIP_BTTS", wartosc)

    assert najlepszy_typ(_mecz())[1] == "BTTS"


def test_flaga_czytana_przy_kazdym_wywolaniu(monkeypatch):
    """Jak `SELECTION_MIN_CONF` — flip bez redeploy kodu. Odczyt w czasie importu
    znaczylby, ze zmiana env dziala dopiero po restarcie kontenera."""
    monkeypatch.setenv("SELECTION_SKIP_BTTS", "1")
    assert najlepszy_typ(_mecz())[1] != "BTTS"

    monkeypatch.setenv("SELECTION_SKIP_BTTS", "0")
    assert najlepszy_typ(_mecz())[1] == "BTTS"


def test_funkcja_pomocnicza_istnieje():
    """Reguła ma mieć jedno miejsce, a nie `os.getenv` rozsiane po module."""
    assert callable(system_paper._pomijaj_btts)
