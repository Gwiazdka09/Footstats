"""Import historii z Neona do Supabase — logika przenoszenia, bez bazy.

KONTEKST: Neon był zablokowany quotą od 18.07 i odblokował się 08.08. Leży tam
195 predykcji (108 rozliczonych, skuteczność 38,0%) i 117 lekcji `ai_feedback`
z okresu 06.05–10.07, czyli SPRZED naprawy Poissona. Supabase ma własne wiersze
od 20.07, więc daty się nie nakładają i import jest dopisaniem, nie scalaniem.

Trzy rzeczy muszą być pewne, bo zapis idzie na produkcję:
  * `id` z obu baz kolidują (Neon 1-242, Supabase 1-26) — nie wolno ich
    przenosić; `ai_feedback.match_id` trzeba przemapować na NOWE id predykcji;
  * każdy importowany wiersz pochodzi z ery Bzzoiro-ML i musi tak być
    ostemplowany, inaczej wpadnie do porównania jako predykcja naszego modelu;
  * ponowne uruchomienie nie może zdublować danych.
"""
from __future__ import annotations

import pytest

from scripts.import_neon_do_supabase import (
    ZRODLO_HISTORYCZNE,
    klucz_predykcji,
    remapuj_lekcje,
    wiersze_do_wstawienia,
)


def _pred(**nadpisz) -> dict:
    p = {
        "id": 7, "match_date": "2026-06-01", "team_home": "Lech Poznan",
        "team_away": "Legia", "ai_tip": "1", "ai_confidence": 60,
        "league": "Ekstraklasa", "tip_correct": 1,
    }
    p.update(nadpisz)
    return p


# ── klucz naturalny ────────────────────────────────────────────────────────

def test_klucz_ignoruje_id_i_czas() -> None:
    a = klucz_predykcji(_pred(id=1, match_date="2026-06-01 20:30:00"))
    b = klucz_predykcji(_pred(id=999, match_date="2026-06-01"))
    assert a == b, "ten sam mecz i typ musza dac ten sam klucz"


def test_klucz_rozroznia_typ() -> None:
    assert klucz_predykcji(_pred(ai_tip="1")) != klucz_predykcji(_pred(ai_tip="X"))


def test_klucz_rozroznia_druzyny() -> None:
    assert klucz_predykcji(_pred(team_away="Lechia")) != klucz_predykcji(_pred())


# ── co wchodzi, a co nie ───────────────────────────────────────────────────

def test_wszystko_wchodzi_gdy_baza_pusta() -> None:
    zrodlo = [_pred(id=1), _pred(id=2, ai_tip="X")]
    assert len(wiersze_do_wstawienia(zrodlo, set())) == 2


def test_juz_obecne_nie_wchodzi_ponownie() -> None:
    """Drugie uruchomienie ma być bezczynne, nie podwajać historii."""
    zrodlo = [_pred(id=1), _pred(id=2, ai_tip="X")]
    istniejace = {klucz_predykcji(zrodlo[0])}
    wynik = wiersze_do_wstawienia(zrodlo, istniejace)
    assert len(wynik) == 1 and wynik[0]["ai_tip"] == "X"


def test_duplikaty_w_samym_zrodle_wchodza_raz() -> None:
    zrodlo = [_pred(id=1), _pred(id=2)]
    assert len(wiersze_do_wstawienia(zrodlo, set())) == 1


def test_kazdy_wiersz_dostaje_stempel_bzzoiro() -> None:
    """Cała ta historia powstała przed 07.08, gdy Poisson nie działał."""
    for w in wiersze_do_wstawienia([_pred(), _pred(ai_tip="X")], set()):
        assert w["model_source"] == ZRODLO_HISTORYCZNE == "bzzoiro-ml"


def test_stempel_nie_jest_nadpisywany_gdy_zrodlo_go_ma() -> None:
    w = wiersze_do_wstawienia([_pred(model_source="poisson-dc")], set())
    assert w[0]["model_source"] == "poisson-dc"


def test_id_zrodla_nie_jedzie_do_bazy() -> None:
    """Zakresy id kolidują — nowe id nadaje sekwencja Supabase."""
    w = wiersze_do_wstawienia([_pred(id=242)], set())
    assert "id" not in w[0]


def test_coupon_id_nie_jedzie_do_bazy() -> None:
    """Wskazywałby na kupon z innej bazy. W Neonie i tak jest pusty we wszystkich."""
    w = wiersze_do_wstawienia([_pred(coupon_id=15)], set())
    assert "coupon_id" not in w[0]


def test_puste_zrodlo() -> None:
    assert wiersze_do_wstawienia([], set()) == []


# ── remapowanie lekcji ─────────────────────────────────────────────────────

def test_lekcja_dostaje_nowe_id_predykcji() -> None:
    lekcje = [{"id": 3, "match_id": 42, "reason_for_failure": "x", "prediction_details": "{}"}]
    gotowe, sieroty = remapuj_lekcje(lekcje, {42: 108})
    assert sieroty == 0
    assert gotowe[0]["match_id"] == 108


def test_lekcja_bez_predykcji_jest_pomijana() -> None:
    """`match_id` jest NOT NULL, więc sieroty trzeba odrzucić, nie wstawiać puste."""
    lekcje = [{"id": 3, "match_id": 999, "reason_for_failure": "x", "prediction_details": "{}"}]
    gotowe, sieroty = remapuj_lekcje(lekcje, {42: 108})
    assert gotowe == [] and sieroty == 1


def test_lekcja_nie_niesie_wlasnego_id() -> None:
    lekcje = [{"id": 3, "match_id": 42, "reason_for_failure": "x", "prediction_details": "{}"}]
    gotowe, _ = remapuj_lekcje(lekcje, {42: 108})
    assert "id" not in gotowe[0]


def test_remap_nie_myli_predykcji() -> None:
    """Najgroźniejszy błąd: lekcja podpięta pod cudzy mecz."""
    lekcje = [
        {"match_id": 1, "reason_for_failure": "a", "prediction_details": "{}"},
        {"match_id": 2, "reason_for_failure": "b", "prediction_details": "{}"},
    ]
    gotowe, _ = remapuj_lekcje(lekcje, {1: 500, 2: 600})
    assert [g["match_id"] for g in gotowe] == [500, 600]
    assert [g["reason_for_failure"] for g in gotowe] == ["a", "b"]


@pytest.mark.parametrize("mapa", [{}, {1: 10}])
def test_pusta_lista_lekcji(mapa: dict) -> None:
    assert remapuj_lekcje([], mapa) == ([], 0)


# ── skladanie zapytania ────────────────────────────────────────────────────

class _KursorAtrapa:
    def __init__(self) -> None:
        self.zapytania: list = []

    def execute(self, zapytanie, wartosci=None) -> None:
        self.zapytania.append((zapytanie, wartosci))

    @staticmethod
    def fetchone():
        return (1,)


def test_kolumna_spoza_bialej_listy_przerywa_import() -> None:
    """Nazwy kolumn pochodzą z DRUGIEJ bazy — nie mogą wpaść do zapytania na ślepo."""
    from scripts.import_neon_do_supabase import KOLUMNY_LEKCJI, _wstaw

    with pytest.raises(ValueError, match="bialej listy"):
        _wstaw(_KursorAtrapa(), "ai_feedback", [{"match_id": 1, "drop_table": "x"}],
               KOLUMNY_LEKCJI)


def test_dozwolone_kolumny_przechodza() -> None:
    from scripts.import_neon_do_supabase import KOLUMNY_LEKCJI, _wstaw

    kursor = _KursorAtrapa()
    nowe = _wstaw(kursor, "ai_feedback",
                  [{"match_id": 5, "reason_for_failure": "x"}], KOLUMNY_LEKCJI)
    assert nowe == [1]
    assert kursor.zapytania[0][1] == [5, "x"]
