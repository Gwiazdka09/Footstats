"""
test_system_paper.py — FAZA 19: wybór typu do single-leg kuponów System.
Weryfikuje filtry Fazy 17 (longshot, min prob) i wybór max prawdopodobieństwa.
"""
import pytest

from footstats.core.system_paper import najlepszy_typ, _prob_dla_typu


def _w(pw=0, pr=0, pp=0, o25=0, bt=0, odds=None):
    return {"pw": pw, "pr": pr, "pp": pp, "o25": o25, "bt": bt, "odds": odds or {}}


def test_prob_dla_typu_mapuje_pola():
    w = _w(pw=68, pr=20, pp=12, o25=62, bt=55)
    assert _prob_dla_typu(w, "1") == 68
    assert _prob_dla_typu(w, "X") == 20
    assert _prob_dla_typu(w, "2") == 12
    assert _prob_dla_typu(w, "Over 2.5") == 62
    assert _prob_dla_typu(w, "Under 2.5") == 38  # 100 - 62
    assert _prob_dla_typu(w, "BTTS") == 55


def test_wybiera_najwyzsze_prawdopodobienstwo():
    w = _w(pw=68, pr=20, pp=12, o25=62, bt=55,
           odds={"home": 1.5, "draw": 4.2, "away": 7.0, "over_2_5": 1.8, "btts": 1.9})
    best = najlepszy_typ(w)
    assert best is not None
    prob, tip, kurs = best
    assert tip == "1"        # pw=68 najwyzsze wsrod legalnych
    assert prob == 68
    assert kurs == 1.5


def test_odrzuca_longshot_kurs():
    # tip "2" pp=12 i tak za niski, ale sprawdzamy ze longshot kurs nie przechodzi
    w = _w(pw=30, pp=55, odds={"away": 8.5, "home": 2.0})
    best = najlepszy_typ(w)
    # away pp=55 ma kurs 8.5 > 4.0 -> odrzucony; home pw=30 < 40 -> odrzucony
    assert best is None


def test_odrzuca_niska_pewnosc():
    w = _w(pw=35, pr=33, pp=32, odds={"home": 2.0, "draw": 3.0, "away": 3.5})
    # wszystkie < 40% -> brak typu
    assert najlepszy_typ(w) is None


def test_odrzuca_brak_kursu():
    w = _w(pw=70, odds={})  # brak kursu dla home
    assert najlepszy_typ(w) is None


def test_pomija_kurs_ponizej_min():
    w = _w(pw=80, odds={"home": 1.05})  # kurs < 1.2
    assert najlepszy_typ(w) is None


def test_wybiera_legalny_gdy_najlepszy_to_longshot():
    # pp=60 (away) ma kurs 6.0 (longshot, odrzuc), ale Over 2.5 o25=50 kurs 1.9 OK
    w = _w(pw=25, pp=60, o25=50, odds={"away": 6.0, "over_2_5": 1.9, "home": 5.0})
    best = najlepszy_typ(w)
    assert best is not None
    prob, tip, kurs = best
    assert tip == "Over 2.5"
    assert prob == 50


# --- M1 lever #1: selekcja high-conf (env SELECTION_MIN_CONF, default OFF = MIN_PROB) ---

def test_selection_min_conf_domyslnie_przepuszcza_50(monkeypatch):
    """Env nieustawiony → próg = MIN_PROB (40), typ z prob 50 przechodzi (zero zmiany)."""
    monkeypatch.delenv("SELECTION_MIN_CONF", raising=False)
    w = _w(pw=50, odds={"home": 1.9})
    best = najlepszy_typ(w)
    assert best is not None and best[0] == 50


def test_selection_min_conf_65_odrzuca_50(monkeypatch):
    """SELECTION_MIN_CONF=65 → typ z prob 50 odrzucony (selekcja high-conf)."""
    monkeypatch.setenv("SELECTION_MIN_CONF", "65")
    w = _w(pw=50, odds={"home": 1.9})
    assert najlepszy_typ(w) is None


def test_selection_min_conf_65_przepuszcza_70(monkeypatch):
    """SELECTION_MIN_CONF=65 → typ z prob 70 przechodzi."""
    monkeypatch.setenv("SELECTION_MIN_CONF", "65")
    w = _w(pw=70, odds={"home": 1.5})
    best = najlepszy_typ(w)
    assert best is not None and best[1] == "1" and best[0] == 70


@pytest.mark.parametrize("bad", ["abc", "-5", "150", ""])
def test_selection_min_conf_smieci_fallback_do_40(monkeypatch, bad):
    """Niepoprawna wartość / poza [0,100] → fallback do MIN_PROB (40)."""
    monkeypatch.setenv("SELECTION_MIN_CONF", bad)
    w = _w(pw=50, odds={"home": 1.9})
    assert najlepszy_typ(w) is not None, f"bad={bad!r} powinno spaść do 40"
