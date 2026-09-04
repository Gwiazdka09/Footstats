"""Obserwacja team-news musi PRZEŻYĆ do bazy — inaczej flaga nic nie uruchamia.

STAN ZASTANY (2026-09-04). `daily_phases._policz_edge_absencji` liczy komplet:
skorygowaną λ, `p_over_abs`, `edge_absencje` i udziały nieobecnych. Zapisuje to
OBOK `o25`, świadomie nie nadpisując — i słusznie, bo tej korekty nie da się
zwalidować walk-forwardem, skoro historii kontuzji nie ma ani u nas, ani
u FotMoba. Docstring tamtej funkcji mówi wprost, że pola `*_abs` istnieją po to,
by „za kilkadziesiąt meczów porównać z rzeczywistością".

Tyle że `edge_absencje` nie czyta NIC poza testami. Ląduje w słowniku kandydata
i ginie razem z procesem. Włączenie `FOOTSTATS_TEAM_NEWS=1` policzyłoby więc
przewagę i ją wyrzuciło — po trzech miesiącach zbierania mielibyśmy dokładnie
tyle samo danych co dziś, czyli zero.

To jest ten sam wzorzec co poprzednio: caly podsystem z testami, liczący liczbę,
której nikt nie przechowuje. `model_log` już trzyma prawdopodobieństwa i λ tego
samego meczu i już dorabia `actual_result` przy rozliczeniu — brakuje wyłącznie
przepisania czterech pól ze słownika do INSERT-a.

CO TO ODBLOKOWUJE: mając w jednym wierszu `prob_over25` (przed korektą),
`p_over_abs` (po), `rynek_p_over` (cena w tamtej chwili) i `over25_correct`
(prawda), można zapytać: gdy korekta za absencje rozjechała się z ceną, KTO MIAŁ
RACJĘ. To jedyne pytanie o przewagę, na które nie odpowiedzieliśmy pomiarem
z 04.09, bo tamten mierzył wyłącznie informację publiczną.
"""
from __future__ import annotations

import pytest

from footstats.core import kalibracja_log as kl


class _Kursor:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _Conn:
    """Atrapa bazy — notuje zapytania, nie udaje istniejącego wiersza."""

    def __init__(self):
        self.zapytania: list[tuple] = []

    def execute(self, sql, params=()):
        plaski = " ".join(sql.split())
        self.zapytania.append((plaski, params))
        if plaski.upper().startswith("INSERT"):
            return _Kursor([{"id": 7}])
        return _Kursor([])

    def executescript(self, sql):
        self.zapytania.append((" ".join(sql.split()), ()))

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def insert(self) -> tuple:
        wstawki = [z for z in self.zapytania if z[0].upper().startswith("INSERT")]
        assert wstawki, "nie bylo zadnego INSERT-a"
        return wstawki[0]


@pytest.fixture
def baza(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: conn)
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: None)
    return conn


def _kandydat(**nadpisz) -> dict:
    k = {
        "gospodarz": "Legia", "goscie": "Lech", "data": "2026-09-10",
        "liga": "POL-Ekstraklasa",
        "pw": 45.0, "pr": 27.0, "pp": 28.0,
        "o25": 52.0, "bt": 51.0,
        "lambda_h": 1.55, "lambda_a": 1.20,
    }
    k.update(nadpisz)
    return k


def _wartosci_insertu(conn) -> dict:
    """Mapuje nazwy kolumn z INSERT-a na wartości — PO NAZWIE, nie po pozycji.

    `assert 0.031 in params` przeszedłby, gdyby dwie kolumny miały tę samą
    wartość albo gdyby ktoś zamienił je miejscami. Zamiana `udzial_home`
    z `udzial_away` jest dokładnie tym rodzajem błędu, który przeżyje lata.
    """
    sql, params = conn.insert()
    kolumny = sql.split("(", 1)[1].split(")", 1)[0]
    nazwy = [k.strip() for k in kolumny.split(",")]
    return dict(zip(nazwy, params))


def test_edge_absencji_trafia_do_bazy(baza):
    kl.zapisz_ocene(_kandydat(
        p_over_abs=47.5, edge_absencje=-0.045, rynek_p_over=52.0,
        absencje_udzial_home=0.31, absencje_udzial_away=0.0,
        absencje_pewne_home=2, absencje_pewne_away=0,
    ))
    w = _wartosci_insertu(baza)
    assert w["p_over_abs"] == 47.5
    assert w["edge_absencje"] == -0.045
    assert w["rynek_p_over"] == 52.0


def test_udzialy_nie_zamieniaja_sie_stronami(baza):
    """Gospodarz i gość różnią się tu wszystkim — zamiana byłaby cicha."""
    kl.zapisz_ocene(_kandydat(
        p_over_abs=47.5, edge_absencje=-0.045,
        absencje_udzial_home=0.31, absencje_udzial_away=0.07,
        absencje_pewne_home=2, absencje_pewne_away=1,
    ))
    w = _wartosci_insertu(baza)
    assert w["absencje_udzial_home"] == 0.31
    assert w["absencje_udzial_away"] == 0.07
    assert w["absencje_pewne_home"] == 2
    assert w["absencje_pewne_away"] == 1


def test_prob_over25_zostaje_wartoscia_SPRZED_korekty(baza):
    """W jednym wierszu muszą być OBIE liczby, inaczej nie ma czego porównywać.

    `_policz_edge_absencji` celowo nie nadpisuje `o25`. Gdyby zapis brał
    `p_over_abs` do `prob_over25`, wiersz mialby wersje po korekcie dwa razy
    i pytanie "czy korekta pomogla" przestaloby istniec.
    """
    kl.zapisz_ocene(_kandydat(o25=52.0, p_over_abs=47.5))
    w = _wartosci_insertu(baza)
    assert w["prob_over25"] == 52.0
    assert w["p_over_abs"] == 47.5


def test_mecz_bez_absencji_zapisuje_NULL_a_nie_zero(baza):
    """Zero znaczy "policzone i wyszlo zero". Brak znaczy "nie liczylismy".

    Zlanie tych dwoch stanow zatrulo by kazda pozniejsza analize: mecze bez
    team-news weszlyby do niej jako "korekta nic nie zmienila".
    """
    kl.zapisz_ocene(_kandydat())
    w = _wartosci_insertu(baza)
    for kol in ("p_over_abs", "edge_absencje", "rynek_p_over",
                "absencje_udzial_home", "absencje_udzial_away"):
        assert w[kol] is None, f"{kol} powinno byc NULL, jest {w[kol]!r}"


@pytest.mark.parametrize("kolumna", [
    "p_over_abs", "edge_absencje", "rynek_p_over",
    "absencje_udzial_home", "absencje_udzial_away",
    "absencje_pewne_home", "absencje_pewne_away",
])
def test_schemat_dokladany_idempotentnym_alterem(monkeypatch, kolumna):
    """Tabela zyje na produkcji, wiec `CREATE IF NOT EXISTS` jej nie ruszy.

    Ten sam powod co przy `model_source` i `draw_correct` — bez ALTER-ow nowe
    kolumny istnialyby wylacznie w testach, a produkcja wywalalaby sie na
    INSERT-cie. Sprawdzamy WYKONANE zapytania, nie tekst zrodla: ALTER-y sa
    generowane w petli, wiec grep po pliku niczego by nie dowiodl.
    """
    conn = _Conn()
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: conn)
    kl.init_kalibracja_log()
    altery = [z[0] for z in conn.zapytania if "ALTER TABLE" in z[0].upper()]
    assert any(f"ADD COLUMN IF NOT EXISTS {kolumna}" in a for a in altery), (
        f"brak idempotentnego ALTER dla {kolumna}; wykonane: {altery}"
    )


def test_daily_phases_zapisuje_cene_rynku_do_kandydata():
    """Bez ceny z TAMTEJ chwili nie da sie orzec, kto mial racje.

    `edge` sam w sobie nie wystarcza: jest roznica, wiec bez jednego ze
    skladnikow nie odtworzy sie drugiego po zaokragleniach.
    """
    from footstats.core.daily_phases import _policz_edge_absencji

    kandydat = {
        "gospodarz": "Legia", "goscie": "Lech",
        "lambda_h": 1.6, "lambda_a": 1.1,
        "market_p_over": 0.55,
        "_absencje_pewne_nazwiska_home": ["Kowalski"],
        "_absencje_pewne_nazwiska_away": [],
    }
    import footstats.core.daily_phases as dp
    _stare = dp._goal_shares_for
    dp._goal_shares_for = lambda *a, **k: {"kowalski": 0.25}
    try:
        _policz_edge_absencji([kandydat])
    finally:
        dp._goal_shares_for = _stare

    assert kandydat.get("rynek_p_over") == 0.55
