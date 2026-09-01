"""Skalary numpy nie moga trafiac do SQL jako tekst.

ZMIERZONE NA PRODUKCJI 01.09 (`footstats-final-zqhzp`, planowy przebieg 09:00 UTC):

    [AI] Nie udalo sie zapisac predykcji FC Zurich vs BSC Young Boys [2]:
         schema "np" does not exist
    ALERT cicha awaria: 0 typow mimo 3 meczow po filtrach — ZERO predykcji zapisanych

W logu poprzedniego przebiegu widac to wprost w tresci odrzuconego zapytania:

    LINE 7: ..., '', 1.31, 'model', '[]', 'model_bez_llm', '[]', np.float64...

MECHANIZM: `numpy.float64` jest PODKLASA Pythonowego `float`, wiec psycopg2
adaptuje ja swoim adapterem dla floatow, a ten uzywa `repr()`. Do NumPy 1.x
`repr(np.float64(0.5))` dawalo `'0.5'`. NumPy 2.x zmienil to na
`'np.float64(0.5)'` — i taki literal ladował w SQL, gdzie Postgres czyta `np`
jako nazwe schematu.

Dlaczego bylo NIEREGULARNE: zapis padal tylko wtedy, gdy `prob_home/draw/away`
przyszly z Poissona (numpy) zamiast z Bzzoiro-ML (czyste floaty). Dlatego jednego
dnia zapisywaly sie 4 predykcje, a innego zero — przy tym samym kodzie.

Naprawa siedzi w JEDNYM miejscu, na granicy bazy: kazda inna lokalizacja
znaczylaby, ze nastepna sciezka zapisu znowu na to wpadnie.
"""
from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from footstats.utils.db import _natywna, _czysc_params


# ── konwersja pojedynczych wartosci ─────────────────────────────────────────

@pytest.mark.parametrize("wartosc,oczekiwany_typ", [
    (np.float64(0.5), float),
    (np.float32(0.25), float),
    (np.int64(7), int),
    (np.int32(3), int),
    (np.bool_(True), bool),
])
def test_skalar_numpy_staje_sie_natywny(wartosc, oczekiwany_typ):
    wynik = _natywna(wartosc)

    assert type(wynik) is oczekiwany_typ
    assert type(wynik).__module__ == "builtins"


def test_wartosc_zostaje_zachowana():
    assert _natywna(np.float64(1.31)) == pytest.approx(1.31)
    assert _natywna(np.int64(42)) == 42


def test_repr_po_konwersji_nie_niesie_juz_nazwy_modulu():
    """To jest DOKLADNIE ta wlasciwosc, ktorej brak wywalil zapis na produkcji."""
    assert "np." not in repr(_natywna(np.float64(0.5)))


@pytest.mark.parametrize("wartosc", [
    None, "tekst", 1.5, 7, True, b"bajty", [1, 2], {"a": 1},
])
def test_zwykle_wartosci_nietkniete(wartosc):
    assert _natywna(wartosc) is wartosc


# ── czyszczenie calej krotki parametrow ─────────────────────────────────────

def test_krotka_parametrow_jest_czyszczona():
    params = ("Arsenal", np.float64(52.0), None, np.int64(3), "1")

    wynik = _czysc_params(params)

    assert wynik == ("Arsenal", 52.0, None, 3, "1")
    assert all(type(w).__module__ in ("builtins", "NoneType") or w is None
               for w in wynik if w is not None)


def test_puste_parametry_zostaja_puste():
    assert _czysc_params(()) == ()
    assert _czysc_params(None) is None


def test_lista_parametrow_tez_dziala():
    """psycopg2 przyjmuje i krotki, i listy — obie sciezki musza byc czyste."""
    assert _czysc_params([np.float64(1.0)]) == (1.0,)


# ── warstwa polaczenia faktycznie tego uzywa ────────────────────────────────

class _FakeCursor:
    def __init__(self, zapis: dict):
        self._zapis = zapis

    def execute(self, sql, params=None):
        self._zapis["sql"] = sql
        self._zapis["params"] = params

    def executemany(self, sql, seq):
        self._zapis["sql"] = sql
        self._zapis["seq"] = list(seq)


class _FakeRaw:
    def __init__(self, zapis: dict):
        self._zapis = zapis

    def cursor(self, **kw):
        return _FakeCursor(self._zapis)


def _polaczenie(zapis: dict):
    from footstats.utils.db import _Conn
    conn = _Conn.__new__(_Conn)          # bez puli i bez sieci
    conn._raw = _FakeRaw(zapis)
    return conn


def test_execute_czysci_parametry():
    zapis: dict = {}

    _polaczenie(zapis).execute(
        "INSERT INTO predictions (a, b) VALUES (?, ?)",
        ("Arsenal", np.float64(52.0)),
    )

    assert zapis["params"] == ("Arsenal", 52.0)
    assert type(zapis["params"][1]) is float


def test_executemany_tez_czysci():
    zapis: dict = {}

    _polaczenie(zapis).executemany(
        "INSERT INTO t (a) VALUES (?)",
        [(np.float64(1.0),), (np.int64(2),)],
    )

    assert zapis["seq"] == [(1.0,), (2,)]


def test_znaki_zapytania_dalej_zamieniane_na_procenty():
    """Kontrola: czyszczenie parametrow nie moze zepsuc tlumaczenia SQL."""
    zapis: dict = {}

    _polaczenie(zapis).execute("SELECT * FROM t WHERE a = ? AND b = ?", (1, 2))

    assert zapis["sql"] == "SELECT * FROM t WHERE a = %s AND b = %s"
