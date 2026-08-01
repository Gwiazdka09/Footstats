"""test_quick_picks_filtry.py — co w ogóle wchodzi do skanu pewniaczków.

PO CO: `szybkie_pewniaczki_2dni` decyduje, które mecze trafiają do dalszej
analizy. Filtry na wejściu są tanie i ciche, więc łatwo je uszkodzić bez
zauważenia — a każdy przepuszczony śmieć kończy jako typ w kuponie.

Cztery bezpieczniki:

  * MECZ ROZEGRANY / W TRAKCIE nie może wejść do skanu. Typowanie meczu, który
    już się toczy, to nie predykcja — to zakład na wynik częściowo znany.
  * HORYZONT CZASOWY. Mecz za tydzień ma inne składy i inne kursy; skan jest
    z założenia krótkoterminowy.
  * BRAK ŹRÓDŁA. Gdy Bzzoiro jest niedostępne albo klucz nie przeszedł
    walidacji, funkcja ma zwrócić pustą listę, a nie próbować liczyć bez danych.
  * BRAK ML I BRAK HISTORII → mecz pomijany. Komentarz w kodzie mówi to wprost:
    „lepiej zero kuponów niż typ zgadywany".
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import footstats.core.quick_picks as qp


class _Bzzoiro:
    """Atrapa klienta — oddaje ustaloną listę zdarzeń."""

    def __init__(self, zdarzenia=None, valid=True, blad=None):
        self._valid = valid
        self._zdarzenia = zdarzenia or []
        self._blad = blad
        self.wywolan = 0

    def predykcje_tygodnia(self):
        self.wywolan += 1
        if self._blad:
            raise self._blad
        return self._zdarzenia


def _zdarzenie(**nadpisz) -> dict:
    """Mecz za 24h z kompletem danych ML."""
    za_dobe = datetime.now() + timedelta(hours=24)
    ev = {
        "gosp": "Legia", "gosc": "Lech", "liga": "POL-Ekstraklasa",
        "data": za_dobe.strftime("%Y-%m-%d"),
        "godzina": za_dobe.strftime("%H:%M"),
        "status": "notstarted",
        "pred_ml": {"prob_home_win": 70, "prob_draw": 20, "prob_away_win": 10,
                    "prob_over_25": 55, "prob_btts_yes": 50,
                    "most_likely_score": {"home": 2, "away": 0}},
        "odds": {"home": 1.60, "draw": 3.80, "away": 5.00},
    }
    ev.update(nadpisz)
    return ev


@pytest.fixture(autouse=True)
def _cicho(monkeypatch):
    monkeypatch.setattr(qp.console, "print", lambda *a, **k: None)


# ── brak źródła ─────────────────────────────────────────────────────────────

def test_brak_klienta_to_pusta_lista():
    assert qp.szybkie_pewniaczki_2dni(None) == []


def test_niezwalidowany_klucz_nie_pyta_api():
    """`_valid=False` znaczy, że klucza nikt nie potwierdził — fail-closed."""
    bz = _Bzzoiro([_zdarzenie()], valid=False)

    assert qp.szybkie_pewniaczki_2dni(bz) == []
    assert bz.wywolan == 0


def test_awaria_api_to_pusta_lista():
    """Błąd źródła nie może wywalić całego skanu."""
    bz = _Bzzoiro(blad=RuntimeError("503"))

    assert qp.szybkie_pewniaczki_2dni(bz) == []


def test_brak_wydarzen_to_pusta_lista():
    assert qp.szybkie_pewniaczki_2dni(_Bzzoiro([])) == []


# ── status meczu ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["inprogress", "finished", "canceled",
                                    "postponed", "1H", "HT"])
def test_mecz_rozegrany_lub_w_trakcie_pomijany(status):
    """Typowanie meczu, który już trwa, to zakład na wynik częściowo znany."""
    bz = _Bzzoiro([_zdarzenie(status=status)])

    assert qp.szybkie_pewniaczki_2dni(bz) == []


@pytest.mark.parametrize("status", ["notstarted", "scheduled", "", None])
def test_mecz_przed_startem_przechodzi_filtr_statusu(status):
    """Brak statusu traktujemy jak "jeszcze się nie zaczął"."""
    bz = _Bzzoiro([_zdarzenie(status=status)])

    # Filtr statusu przepuszcza — dalej decyduje próg pewności, nie status.
    qp.szybkie_pewniaczki_2dni(bz, prog=0)

    assert bz.wywolan == 1


# ── horyzont czasowy ────────────────────────────────────────────────────────

def test_mecz_poza_horyzontem_pomijany():
    """Mecz za tydzień ma inne składy i inne kursy."""
    za_tydzien = datetime.now() + timedelta(days=7)
    bz = _Bzzoiro([_zdarzenie(data=za_tydzien.strftime("%Y-%m-%d"),
                              godzina=za_tydzien.strftime("%H:%M"))])

    assert qp.szybkie_pewniaczki_2dni(bz, prog=0, godziny=48) == []


def test_mecz_z_przeszlosci_pomijany():
    wczoraj = datetime.now() - timedelta(days=1)
    bz = _Bzzoiro([_zdarzenie(data=wczoraj.strftime("%Y-%m-%d"),
                              godzina=wczoraj.strftime("%H:%M"))])

    assert qp.szybkie_pewniaczki_2dni(bz, prog=0) == []


def test_szerszy_horyzont_wpuszcza_dalszy_mecz():
    za_5_dni = datetime.now() + timedelta(days=5)
    ev = _zdarzenie(data=za_5_dni.strftime("%Y-%m-%d"),
                    godzina=za_5_dni.strftime("%H:%M"))

    wąski = qp.szybkie_pewniaczki_2dni(_Bzzoiro([ev]), prog=0, godziny=48)
    szeroki = qp.szybkie_pewniaczki_2dni(_Bzzoiro([ev]), prog=0, godziny=24 * 7)

    assert wąski == []
    assert len(szeroki) >= 1


# ── niekompletne dane wejściowe ─────────────────────────────────────────────

@pytest.mark.parametrize("brak", [
    {"gosp": ""}, {"gosc": ""}, {"data": ""},
    {"gosp": None}, {"gosc": None},
])
def test_wydarzenie_bez_kluczowych_pol_pomijane(brak):
    """Bez nazw drużyn albo daty nie da się ani rozliczyć, ani zweryfikować."""
    bz = _Bzzoiro([_zdarzenie(**brak)])

    assert qp.szybkie_pewniaczki_2dni(bz, prog=0) == []


def test_zepsuta_godzina_nie_wywala_skanu():
    """Śmieć w jednym polu nie może zatrzymać całego skanu — data sama wystarczy."""
    jutro = datetime.now() + timedelta(hours=20)
    bz = _Bzzoiro([_zdarzenie(data=jutro.strftime("%Y-%m-%d"), godzina="nie-godzina")])

    qp.szybkie_pewniaczki_2dni(bz, prog=0)  # nie rzuca

    assert bz.wywolan == 1


def test_zepsuta_data_pomija_wydarzenie():
    bz = _Bzzoiro([_zdarzenie(data="wczoraj-kiedys", godzina="20:00")])

    assert qp.szybkie_pewniaczki_2dni(bz, prog=0) == []


# ── brak ML i brak historii ─────────────────────────────────────────────────

def test_brak_ml_bez_historii_pomija_mecz():
    """Komentarz w kodzie mówi to wprost: lepiej zero kuponów niż typ zgadywany."""
    bz = _Bzzoiro([_zdarzenie(pred_ml=None)])

    assert qp.szybkie_pewniaczki_2dni(bz, prog=0, df_mecze=None) == []


def test_puste_ml_traktowane_jak_brak():
    bz = _Bzzoiro([_zdarzenie(pred_ml={})])

    assert qp.szybkie_pewniaczki_2dni(bz, prog=0, df_mecze=None) == []


# ── próg pewności ───────────────────────────────────────────────────────────

def test_wysoki_prog_odrzuca_slabe_typy():
    """Próg 99% nie przepuści meczu, w którym model daje 70%."""
    bz = _Bzzoiro([_zdarzenie()])

    assert qp.szybkie_pewniaczki_2dni(bz, prog=99) == []


def test_niski_prog_przepuszcza():
    bz = _Bzzoiro([_zdarzenie()])

    assert len(qp.szybkie_pewniaczki_2dni(bz, prog=0)) >= 1


def test_wynik_niesie_nazwy_i_lige():
    wynik = qp.szybkie_pewniaczki_2dni(_Bzzoiro([_zdarzenie()]), prog=0)

    assert wynik[0]["gospodarz"] == "Legia"
    assert wynik[0]["goscie"] == "Lech"
    assert wynik[0]["liga"] == "POL-Ekstraklasa"
