"""
test_system_paper.py — FAZA 19: wybór typu do single-leg kuponów System.
Weryfikuje filtry Fazy 17 (longshot, min prob) i wybór max prawdopodobieństwa.
"""
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
