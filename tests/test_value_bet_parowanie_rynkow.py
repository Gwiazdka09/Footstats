"""Filtr value bet musi zestawiać prawdopodobieństwo z kursem TEGO SAMEGO rynku.

DWA SPRZĘŻONE BUGI, oba ciche (2026-08-07, zmierzone na produkcji):

1. `calibrate_candidates` czytało `ai_confidence` / `pewnosc_pct` z domyślnym
   ZEREM. Kandydaci z `quick_picks` nie mają żadnego z tych pól — niosą płaskie
   `pw/pr/pp/bt/o25` — więc każdy dostawał `pewnosc_kalibrowana = 0.0`, a stąd
   EV = −100% i odrzucenie. Efekt na produkcji: `Pre-filtr value bet (EV/Kelly):
   26 → 0` przy KAŻDYM uruchomieniu, czyli zero kuponów niezależnie od danych.

2. `_get_best_odds` brało MAKSYMALNY kurs ze słownika, bez związku z rynkiem,
   z którego pochodziło prawdopodobieństwo. Samo naprawienie (1) byłoby więc
   groźniejsze niż bug: 60% na gospodarza zestawione z kursem 7.41 na gościa
   daje EV +344% i przepuszcza śmieci jako "value bet".

Dlatego naprawa musi być łączna: EV liczone per rynek, z pary
(prawdopodobieństwo modelu, kurs tego samego rynku), a kandydat oceniany
po SWOIM najlepszym rynku.
"""
from __future__ import annotations

import pytest

from footstats.core.value_bet import filter_value_bets

# Kształt kandydata z `quick_picks` — prawdopodobieństwa w procentach.
_ODDS = {"home": 4.11, "draw": 3.16, "away": 1.95,
         "over_2_5": 2.49, "under_2_5": 1.50, "btts": 2.20}


def _kandydat(**nadpisz) -> dict:
    k = {
        "gospodarz": "Avispa Fukuoka", "goscie": "Vissel Kobe", "liga": "J1 League",
        "pw": 36.7, "pr": 32.0, "pp": 31.3, "bt": 26.1, "o25": 20.1,
        "odds": dict(_ODDS),
    }
    k.update(nadpisz)
    return k


# ── bug 1: brak pola pewności nie może znaczyć zera ────────────────────────

def test_kandydat_bez_pola_pewnosci_nie_dostaje_ev_minus_sto() -> None:
    """Realny kształt z produkcji: ani `ai_confidence`, ani `pewnosc_pct`."""
    k = _kandydat()
    assert "ai_confidence" not in k and "pewnosc_pct" not in k
    wynik = filter_value_bets([k])
    assert wynik, "kandydat odrzucony mimo dodatniego EV na rynku gospodarza"


def test_zerowa_pewnosc_nadal_odrzuca() -> None:
    """Jawne 0 to realna ocena, nie brak danych — musi odrzucać.

    Tylko rynki 1X2, bo `o25=0` nie znaczy „brak pewności", tylko „zero szans
    na Over" — czyli pewne Under, które słusznie byłoby value betem.
    """
    k = _kandydat(
        pw=0.0, pr=0.0, pp=0.0,
        odds={"home": 4.11, "draw": 3.16, "away": 1.95},
    )
    assert filter_value_bets([k]) == []


# ── bug 2: parowanie rynków ────────────────────────────────────────────────

def test_prawdopodobienstwo_nie_moze_isc_z_kursem_innego_rynku() -> None:
    """Rdzeń regresji: wysoka szansa gospodarza + wysoki kurs na gościa.

    Gospodarz: 60% przy kursie 1.50 → EV = −10%, brak value.
    Gość:      15% przy kursie 7.00 → EV = +5%, ale to INNY rynek.
    Stary kod brał max(kurs) = 7.00 i mnożył przez pewność gospodarza
    → EV +320% i kandydat przechodził jako "value bet".
    """
    k = _kandydat(
        pw=60.0, pr=25.0, pp=15.0, bt=10.0, o25=10.0,
        odds={"home": 1.50, "draw": 4.00, "away": 7.00},
    )
    wynik = filter_value_bets([k])
    if wynik:
        assert wynik[0]["value_rynek"] == "away", (
            "value przypisane rynkowi, ktorego prawdopodobienstwa nie uzyto"
        )
        assert wynik[0]["ev_value_pct"] < 20.0, (
            f"EV {wynik[0]['ev_value_pct']}% — kurs sparowany z cudza szansa"
        )


def test_rynek_z_najwyzszym_ev_jest_wybrany() -> None:
    k = _kandydat(
        pw=20.0, pr=20.0, pp=60.0, bt=50.0, o25=50.0,
        odds={"home": 2.00, "draw": 3.00, "away": 2.50},
    )
    wynik = filter_value_bets([k])
    assert wynik and wynik[0]["value_rynek"] == "away"
    assert wynik[0]["ev_value_pct"] == pytest.approx(50.0, abs=0.1)


def test_under_liczone_jako_dopelnienie_over() -> None:
    """`o25` to szansa na Over — Under to 100 − o25, nie osobne pole."""
    k = _kandydat(
        pw=10.0, pr=10.0, pp=10.0, bt=10.0, o25=20.0,
        odds={"under_2_5": 1.50},
    )
    wynik = filter_value_bets([k])
    assert wynik and wynik[0]["value_rynek"] == "under_2_5"
    # 80% * 1.50 = 1.20 → EV +20%
    assert wynik[0]["ev_value_pct"] == pytest.approx(20.0, abs=0.1)


def test_kursy_rynkow_efektywnych_sa_odrzucane() -> None:
    """Marża bukmachera: kursy zgodne z naszymi szansami dają ujemne EV."""
    k = _kandydat(
        pw=50.0, pr=25.0, pp=25.0, bt=50.0, o25=50.0,
        odds={"home": 1.90, "draw": 3.60, "away": 3.60,
              "over_2_5": 1.90, "under_2_5": 1.90, "btts": 1.90},
    )
    assert filter_value_bets([k]) == []


def test_kurs_ponizej_jedynki_ignorowany() -> None:
    k = _kandydat(pw=90.0, odds={"home": 0.9, "away": 1.01})
    assert filter_value_bets([k]) == []


# ── zachowania, których nie wolno zepsuć ───────────────────────────────────

def test_brak_kursow_zostawia_kandydata() -> None:
    """Bez kursów nie da się policzyć EV — odrzucenie byłoby zgadywaniem."""
    k = _kandydat(odds={})
    assert len(filter_value_bets([k])) == 1


def test_stary_ksztalt_z_pewnoscia_i_pojedynczym_kursem_dziala() -> None:
    """Ścieżka warstwy AI: jedno `pewnosc_pct` + jeden `kurs`, bez słownika."""
    k = {"gospodarz": "A", "goscie": "B", "pewnosc_pct": 60.0, "kurs": 2.0}
    wynik = filter_value_bets([k])
    assert wynik and wynik[0]["ev_value_pct"] == pytest.approx(20.0, abs=0.1)


def test_stary_ksztalt_bez_edge_odrzucony() -> None:
    k = {"gospodarz": "A", "goscie": "B", "pewnosc_pct": 40.0, "kurs": 2.0}
    assert filter_value_bets([k]) == []


def test_slownik_kursow_pod_etykieta_typu_dziala() -> None:
    """Warstwa AI podaje `odds` kluczowane etykietą typu, nie nazwą rynku.

    Jedna wartość kursu + jedno `pewnosc_pct` = parowanie jednoznaczne, więc
    wolno je policzyć. Regresja: przepisanie filtra na rynki nazwane
    (home/draw/away) przestało ten kształt rozpoznawać i kandydat przechodził
    bez oceny EV.
    """
    k = {"pewnosc_pct": 60, "odds": {"1": 2.5}}
    wynik = filter_value_bets([k])
    assert wynik and wynik[0]["ev_value_pct"] == pytest.approx(50.0, abs=0.1)


def test_slownik_kursow_pod_etykieta_typu_odrzuca_bez_edge() -> None:
    k = {"pewnosc_pct": 40, "odds": {"1": 2.5}}
    assert filter_value_bets([k]) == []


def test_wiele_nieznanych_kursow_przy_jednej_pewnosci_nie_jest_zgadywane() -> None:
    """Kilka kursów i jedna pewność — nie wiadomo, którego wyniku dotyczy.

    Branie maksimum było dokładnie tym bugiem, który naprawiamy. Kandydat
    zostaje nieoceniony (przechodzi dalej), zamiast dostać zmyślone EV.
    """
    k = {"pewnosc_pct": 60, "odds": {"1": 1.5, "X": 3.5, "2": 9.0}}
    wynik = filter_value_bets([k])
    assert len(wynik) == 1
    assert "ev_value_pct" not in wynik[0], "EV policzone z niesparowanego kursu"


def test_kelly_ponizej_progu_odrzuca_mimo_dodatniego_ev() -> None:
    """EV dodatnie, ale stawka Kelly'ego znikoma — nie warto ryzykować."""
    k = {"gospodarz": "A", "goscie": "B", "pewnosc_pct": 50.0, "kurs": 2.07}
    wynik = filter_value_bets([k], min_ev_pct=3.0, min_kelly_pct=10.0)
    assert wynik == []


def test_wejscie_nie_jest_mutowane() -> None:
    k = _kandydat()
    kopia = dict(k)
    filter_value_bets([k])
    assert k == kopia, "filtr zmodyfikowal kandydata wejsciowego"


def test_pusta_lista() -> None:
    assert filter_value_bets([]) == []


def test_kalibracja_nie_fabrykuje_zera(monkeypatch) -> None:
    """`calibrate_candidates` nie może wstawiać 0.0, gdy nie ma czego kalibrować."""
    from footstats.core.probability_calibrator import calibrate_candidates

    k = _kandydat()
    calibrate_candidates([k])
    assert k.get("pewnosc_kalibrowana") != 0.0, (
        "brak pola pewnosci potraktowany jako pewnosc zerowa"
    )
