"""Testy core/match_tips.build_tips — sugerowany typ = argmax 1X2, nie zawsze '1'."""
import pytest

from footstats.core.match_tips import build_tips, over15_z_over25


def _match(ph, pr, pp, *, odds=None):
    m = {
        "id": "t1", "gosp": "A", "gosc": "B", "liga": "Test",
        "pred_ml": {"prob_home_win": ph, "prob_draw": pr, "prob_away_win": pp},
    }
    if odds:
        m["odds"] = odds
    return m


def test_suggested_tip_to_faworyt_gospodarz():
    out = build_tips(_match(0.60, 0.25, 0.15))
    assert out["suggested_tip"]["tip"] == "1"


def test_suggested_tip_to_faworyt_gosc_nie_zawsze_1():
    # Gość zdecydowany faworyt → sugerowany MUSI być "2", nie "1" (regresja buga GUI).
    out = build_tips(_match(0.15, 0.25, 0.60))
    assert out["suggested_tip"]["tip"] == "2"


def test_suggested_tip_to_remis_gdy_najwyzszy():
    out = build_tips(_match(0.30, 0.45, 0.25))
    assert out["suggested_tip"]["tip"] == "X"


def test_suggested_tip_niesie_kurs_zgodny_z_wyborem():
    odds = {"home": 5.0, "draw": 3.8, "away": 1.55}
    out = build_tips(_match(0.18, 0.27, 0.55, odds=odds))
    sug = out["suggested_tip"]
    assert sug["tip"] == "2"
    assert sug["odds"] == 1.55  # kurs sugerowanego = kurs "2", nie "1"


def _tip(out, tip):
    return next(t for t in out["tips"] if t["tip"] == tip)


def test_double_chance_nigdy_ponizej_1():
    # Faworyt-gospodarz z realnymi kursami: naiwne 1/(1/a+1/b) dawało 1X < 1.0
    # (kurs niemożliwy). Devig musi dać > 1.0. Regresja "Moje uwagi" (06-20).
    odds = {"home": 1.15, "draw": 6.5, "away": 13.0}
    out = build_tips(_match(0.85, 0.11, 0.04, odds=odds))
    o1x = _tip(out, "1X")["odds"]
    ox2 = _tip(out, "X2")["odds"]
    assert o1x > 1.0, f"1X={o1x} nie może być <=1.0"
    assert ox2 > 1.0, f"X2={ox2} nie może być <=1.0"
    # 1X (gosp+remis) przy faworycie-gospodarzu = niski kurs, ale realny (>1)
    assert 1.0 < o1x < 1.2


def test_wszystkie_kursy_powyzej_1():
    # Żaden wyświetlany kurs nie może być <= 1.0 (nie istnieją takie u bukmachera).
    odds = {"home": 1.08, "draw": 9.0, "away": 21.0}
    out = build_tips(_match(0.92, 0.06, 0.02, odds=odds))
    zle = [(t["tip"], t["odds"]) for t in out["tips"] if t["odds"] <= 1.0]
    assert zle == [], f"kursy <=1.0: {zle}"


# Krok 0 (22.10): Over 1.5 było liczone jako Over 2.5 + 15 pp — liczba bez
# podstaw, widoczna w kreatorze. Teraz suma goli ~ Poisson(λ) z λ dobranym
# tak, żeby P(suma >= 3) = Over 2.5; Over 1.5 = P(suma >= 2).
@pytest.mark.parametrize("po, oczekiwane", [
    (5.0, 19.8), (30.0, 57.0), (55.0, 78.3), (70.0, 87.6), (90.0, 96.9),
])
def test_over15_z_over25_wartosci_poissona(po, oczekiwane):
    assert over15_z_over25(po) == pytest.approx(oczekiwane, abs=0.05)


@pytest.mark.parametrize("po", [1.0, 10.0, 30.0, 50.0, 70.0, 95.0])
def test_over15_zawsze_wieksze_od_over25(po):
    assert over15_z_over25(po) > po


def test_over15_nie_pokazuje_100_procent():
    assert over15_z_over25(99.9) <= 99.0


def test_build_tips_over15_z_poissona_nie_heurystyka():
    m = _match(0.45, 0.27, 0.28)
    m["pred_ml"]["prob_over_25"] = 0.30
    tips = {t["tip"]: t for t in build_tips(m)["tips"]}
    # heurystyka dawała 45.0
    assert tips["Over 1.5"]["prob"] == pytest.approx(57.0, abs=0.05)
