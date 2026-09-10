"""Alarmy KONCOWE: czy produkcja liczy to, co mierzymy — nie tylko czy cos powstaje.

`pipeline-health` pytal dotad o trzy rzeczy: czy przybywa predykcji, czy
rozliczenia nadazaja, czy draft zyje. Wszystkie trzy swiecily zielono, kiedy:

    * Poisson liczyl 28% ocen, reszte fallback Bzzoiro (do 10.09);
    * `model_log.lambda_h` byla pusta w 1231 z 1231 wierszy (do 10.09);
    * team-news byl martwy na trzech poziomach (do 07.09);
    * CLV nie powstalo ANI RAZU w historii projektu (do 07.09), a Over/Under
      nie dostawal kursu zamkniecia nigdy (do 10.09).

Kazda z tych awarii miala zielone testy jednostkowe. Decyzja 10.09: zamiast
kolejnych testow — alarm na SKUTEK w bazie produkcyjnej.

Progi sa CELOWO niskie: alarm ma lapac zapasc, nie wahanie dnia. Szum zabija
alarm tak samo skutecznie jak cisza (111 ostrzezen na godzine z 07.09).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from footstats.core import alarmy_jakosci as aj


class _Kursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Conn:
    """Atrapa: odpowiedz wybierana po fragmencie SQL."""

    def __init__(self, oceny_24h=None, oceny_72h=None, clv=None):
        self.oceny_24h = oceny_24h or {"n": 40, "pois": 16, "pois_lambda": 16}
        self.oceny_72h = oceny_72h or {"n": 120, "tn": 9}
        self.clv = clv or {"mapowalne": 30, "z_clv": 6}
        self.zapytania: list[tuple[str, tuple]] = []

    def execute(self, sql, params=()):
        plaski = " ".join(sql.split())
        self.zapytania.append((plaski, params))
        if "coupons" in plaski:
            return _Kursor(self.clv)
        if "72 hours" in plaski:
            return _Kursor(self.oceny_72h)
        return _Kursor(self.oceny_24h)


def test_zdrowy_stan_milczy():
    powody, metryki = aj.sprawdz_jakosc(_Conn())
    assert powody == []
    assert metryki["pokrycie_poissona"] == pytest.approx(0.40)
    assert metryki["clv_z_kursem"] == 6


# ── pokrycie Poissona ───────────────────────────────────────────────────────

def test_zapasc_poissona_alarmuje():
    powody, _ = aj.sprawdz_jakosc(_Conn(oceny_24h={"n": 40, "pois": 4, "pois_lambda": 4}))
    assert any("Poisson" in p and "10%" in p for p in powody), powody


def test_mala_proba_nie_alarmuje():
    """Przerwa reprezentacyjna: 8 ocen, 0 z Poissona — to nie awaria."""
    powody, _ = aj.sprawdz_jakosc(_Conn(oceny_24h={"n": 8, "pois": 0, "pois_lambda": 0}))
    assert not any("Poisson" in p for p in powody)


# ── λ w dzienniku ───────────────────────────────────────────────────────────

def test_lambda_znika_z_dziennika_alarmuje():
    powody, _ = aj.sprawdz_jakosc(_Conn(oceny_24h={"n": 40, "pois": 15, "pois_lambda": 0}))
    assert any("λ" in p for p in powody), powody


def test_lambda_przy_malej_liczbie_poissona_milczy():
    powody, _ = aj.sprawdz_jakosc(_Conn(oceny_24h={"n": 40, "pois": 9, "pois_lambda": 0}))
    assert not any("λ" in p for p in powody)


# ── team-news ───────────────────────────────────────────────────────────────

def test_team_news_martwy_trzy_dni_alarmuje():
    powody, _ = aj.sprawdz_jakosc(_Conn(oceny_72h={"n": 120, "tn": 0}))
    assert any("team-news" in p for p in powody), powody


def test_team_news_przy_malej_probie_milczy():
    powody, _ = aj.sprawdz_jakosc(_Conn(oceny_72h={"n": 20, "tn": 0}))
    assert not any("team-news" in p for p in powody)


# ── CLV ─────────────────────────────────────────────────────────────────────

def test_clv_martwe_alarmuje():
    powody, _ = aj.sprawdz_jakosc(_Conn(clv={"mapowalne": 30, "z_clv": 0}))
    assert any("CLV" in p for p in powody), powody


@pytest.mark.parametrize("clv", [{"mapowalne": 10, "z_clv": 0}, {"mapowalne": 30, "z_clv": 1}])
def test_clv_mala_proba_albo_zywe_milczy(clv):
    powody, _ = aj.sprawdz_jakosc(_Conn(clv=clv))
    assert not any("CLV" in p for p in powody)


def test_clv_liczy_tylko_typy_z_cena_w_csv():
    """BTTS czy podwojna szansa nigdy nie dostana kursu — nie moga zanizac proporcji."""
    conn = _Conn()
    aj.sprawdz_jakosc(conn)
    [(sql, params)] = [(s, p) for s, p in conn.zapytania if "coupons" in s]
    typy = set(params[0])
    assert {"1", "X", "2", "OVER 2.5", "UNDER 2.5"} <= typy
    assert "BTTS" not in typy


# ── odpornosc ───────────────────────────────────────────────────────────────

def test_brak_kolumn_w_wierszu_nie_wybucha():
    """Wiersz bez oczekiwanych kluczy (np. atrapa innego testu) = zero, nie KeyError."""
    class _Pusta(_Conn):
        def execute(self, sql, params=()):
            return _Kursor({"cos_innego": 1})

    powody, metryki = aj.sprawdz_jakosc(_Pusta())
    assert powody == [] and metryki["oceny_24h"] == 0


def test_sql_bez_znaku_zapytania_poza_parametrami_i_bez_procentow():
    """`utils.db._Conn._fix` zamienia KAZDE `?` na `%s`, a `%` psuje formatowanie
    psycopg2 — operator jsonb `?` albo LIKE '%x%' wysadzilyby zapytanie na prod."""
    conn = _Conn()
    aj.sprawdz_jakosc(conn)
    for sql, params in conn.zapytania:
        assert sql.count("?") == len(params), sql
        assert "%" not in sql, sql


def test_pipeline_health_wola_kontrole_jakosci():
    zrodlo = Path("src/footstats/api/routes/status.py").read_text(encoding="utf-8")
    kod = "\n".join(l for l in zrodlo.splitlines() if not l.lstrip().startswith("#"))
    assert "sprawdz_jakosc(" in kod
