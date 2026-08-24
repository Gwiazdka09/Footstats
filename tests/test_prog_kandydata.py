"""Prog kandydata (`AGENT_KANDYDAT_PROG`) — SKALA PROCENTOWA, nie ulamek.

DLACZEGO TEN PLIK ISTNIEJE: wartosc byla zapisana jako `0.55` z komentarzem
"prog pewnosci", ale trafia do `_typy_pewne`, ktore porownuje ja z pw/pr/pp/bt/
o25/u25 wyrazonymi w PROCENTACH (0-100) — tak samo jak `PEWNIACZEK_PROG = 40.0`
i `MIN_PROB = 40.0` w `system_paper`. `0.55` znaczylo wiec "co najmniej 0,55%",
czyli filtr kandydatow nie odrzucal NICZEGO.

Panel jednoczesnie pokazywal `kandydat_prog: 55.0` (`settings.py` mnozylo przez
100), wiec interfejs raportowal prog, ktorego nie bylo — dokladnie ten sam ksztalt
awarii co "zielone testy, martwa prod": nikt nie mial testu na ten tor.

Zero testow dotykalo `AGENT_KANDYDAT_PROG` przed tym plikiem.
"""
from __future__ import annotations

import importlib
import os

import pytest

os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")

import footstats.config as cfg  # noqa: E402
from footstats.core.weekly_picks import _typy_pewne  # noqa: E402


# ── skala ───────────────────────────────────────────────────────────────────

def test_prog_kandydata_jest_w_procentach_nie_w_ulamku():
    """`0.55` przechodzilo jako 0,55% i przepuszczalo kazdy mecz."""
    assert cfg.AGENT_KANDYDAT_PROG > 1.0, (
        f"AGENT_KANDYDAT_PROG={cfg.AGENT_KANDYDAT_PROG} wyglada na ulamek; "
        "`_typy_pewne` porownuje go z procentami (0-100)"
    )


def test_ta_sama_skala_co_pewniaczek_prog():
    """Obie stale ida do tego samego porownania w `_typy_pewne`."""
    assert 0.0 <= cfg.AGENT_KANDYDAT_PROG <= 100.0
    assert 0.0 <= cfg.PEWNIACZEK_PROG <= 100.0


def test_domyslny_prog_to_50():
    assert cfg.AGENT_KANDYDAT_PROG == 50.0


# ── prog realnie odrzuca ────────────────────────────────────────────────────

def test_slabe_typy_odrzucone_przy_progu_50():
    """Sedno bledu: przy `0.55` KAZDY z osmiu typow przechodzil (patrz test nizej)."""
    typy = _typy_pewne(pw=30.0, pr=25.0, pp=45.0, bt=48.0, o25=44.0, u25=44.0,
                       g="Aaa", a="Bbb", prog=cfg.AGENT_KANDYDAT_PROG)

    opisy = [o for o, _ in typy]
    for slaby in ("BTTS TAK", "Over 2.5", "Under 2.5"):
        assert slaby not in opisy, f"{slaby} < 50% nie moze przejsc: {opisy}"
    assert not any(o.startswith(("1 –", "2 –")) for o in opisy), opisy


def test_prog_50_nie_odsiewa_meczu_przez_podwojna_szanse():
    """OGRANICZENIE, nie usterka — warto miec je zapisane.

    `_typy_pewne` liczy tez 1X / X2 / 12. Suma trzech par podwojnej szansy to
    2*(pw+pr+pp) = 200%, wiec ZAWSZE ktoras jest >= 66,7% — zaden mecz z predykcja
    1X2 nie odpadnie na progu 50. Prog kandydata jest wiec szerokim sitem, a realny
    filtr kuponu to `najlepszy_typ` (`MIN_PROB` / `SELECTION_MIN_CONF`), ktore
    podwojnej szansy w ogole nie obstawia (`_ODDS_KEY` zna tylko 1/X/2/O/U/BTTS).

    Test jest tu po to, zeby nikt nie uznal progu kandydata za brame selekcji.
    """
    typy = _typy_pewne(pw=30.0, pr=25.0, pp=45.0, bt=10.0, o25=10.0, u25=10.0,
                       g="Aaa", a="Bbb", prog=cfg.AGENT_KANDYDAT_PROG)

    opisy = [o for o, _ in typy]
    assert opisy, "podwojna szansa zawsze przepusci mecz z predykcja 1X2"
    assert all("–" in o and o.split("–")[0].strip() in ("1X", "X2", "12")
               for o in opisy), opisy


def test_mecz_powyzej_progu_przechodzi():
    typy = _typy_pewne(pw=58.0, pr=20.0, pp=22.0, bt=40.0, o25=45.0, u25=55.0,
                       g="Aaa", a="Bbb", prog=cfg.AGENT_KANDYDAT_PROG)

    opisy = [o for o, _ in typy]
    assert any(o.startswith("1 –") for o in opisy), opisy
    assert any(o == "Under 2.5" for o in opisy), opisy
    assert not any(o == "Over 2.5" for o in opisy), "45% < 50% nie moze przejsc"


def test_stary_ulamek_przepuszczalby_wszystko():
    """Dowod regresji — gdyby ktos wrocil do 0.55, filtr znowu bylby martwy."""
    typy = _typy_pewne(pw=1.0, pr=1.0, pp=1.0, bt=1.0, o25=1.0, u25=1.0,
                       g="Aaa", a="Bbb", prog=0.55)

    assert len(typy) == 8, "0.55 przepuszcza kazdy z osmiu typow"


# ── env override, jak pozostale lewary (flip bez redeploya) ─────────────────

@pytest.mark.parametrize("wartosc,oczekiwane", [("40", 40.0), ("65.5", 65.5)])
def test_env_nadpisuje_prog(monkeypatch, wartosc: str, oczekiwane: float):
    monkeypatch.setenv("AGENT_KANDYDAT_PROG", wartosc)
    przeladowany = importlib.reload(cfg)
    try:
        assert przeladowany.AGENT_KANDYDAT_PROG == oczekiwane
    finally:
        monkeypatch.delenv("AGENT_KANDYDAT_PROG", raising=False)
        importlib.reload(cfg)


# ── panel nie moze klamac o progu ───────────────────────────────────────────

def test_settings_zwraca_prog_w_procentach():
    """`settings.py` mnozylo przez 100 — przy progu 50 dawaloby 5000."""
    import footstats.api.routes.settings as s

    zrodlo = open(s.__file__, encoding="utf-8").read()
    assert "AGENT_KANDYDAT_PROG * 100" not in zrodlo, (
        "prog jest juz w procentach; mnozenie przez 100 daje 5000"
    )


def test_config_endpoint_podaje_te_sama_liczbe_co_stala():
    import footstats.api.routes.status as st

    zrodlo = open(st.__file__, encoding="utf-8").read()
    assert '"min_confidence": cfg.AGENT_KANDYDAT_PROG' in zrodlo
