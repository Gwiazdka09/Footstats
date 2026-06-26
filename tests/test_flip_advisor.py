"""test_flip_advisor.py — pure werdykty flipu lewarów M1 (selekcja / gating)."""
from footstats.core.flip_advisor import werdykt_selekcja, werdykt_gating


# --- werdykt_selekcja (lever #1, SELECTION_MIN_CONF) ---
# pasma: (band, n, won, acc)

def test_selekcja_brak_danych():
    assert werdykt_selekcja([])["status"] == "brak"


def test_selekcja_czeka_gdy_za_malo_high_conf():
    # tylko 4 settled w paśmie 65% (min 10) → czekaj
    r = werdykt_selekcja([(60, 20, 10, 50.0), (65, 4, 3, 75.0)])
    assert r["status"] == "czekaj" and r["n_high"] == 4


def test_selekcja_flip_gdy_high_conf_bije_ogol():
    # ogół ~52%, pasmo 65%+ ma 12 settled @ 75% → delta duża, acc_high>=55 → flip
    pasma = [(40, 30, 12, 40.0), (50, 30, 16, 53.3), (65, 8, 6, 75.0), (70, 6, 5, 83.3)]
    r = werdykt_selekcja(pasma)
    assert r["status"] == "gotowe" and r["flip"] is True
    assert r["n_high"] == 14 and r["acc_high"] > r["acc_all"]


def test_selekcja_brak_flip_gdy_high_conf_slabe():
    # pasmo high-conf nie bije ogółu (delta < 3) → flip False
    pasma = [(40, 30, 15, 50.0), (65, 12, 6, 50.0)]
    r = werdykt_selekcja(pasma)
    assert r["status"] == "gotowe" and r["flip"] is False


# --- werdykt_gating (lever #2, LEAGUE_GATING) ---
# per_liga: (league, n, won, acc)

def test_gating_dzieli_slabe_mocne():
    per = [("POL", 10, 4, 40.0), ("NED", 12, 7, 58.3), ("ESP", 9, 4, 44.4)]
    r = werdykt_gating(per)
    assert [s[0] for s in r["slabe"]] == ["POL", "ESP"]   # <50%, sort rosnąco acc
    assert [m[0] for m in r["mocne"]] == ["NED"]


def test_gating_pomija_male_n():
    # liga z n < min (8) ignorowana mimo niskiej trafności
    per = [("FRA", 3, 0, 0.0), ("ITA", 10, 6, 60.0)]
    r = werdykt_gating(per)
    assert "FRA" not in [s[0] for s in r["slabe"]]
    assert [m[0] for m in r["mocne"]] == ["ITA"]


def test_gating_sort_najslabsze_pierwsze():
    per = [("ESP", 10, 4, 40.0), ("POL", 10, 3, 30.0)]
    r = werdykt_gating(per)
    assert [s[0] for s in r["slabe"]] == ["POL", "ESP"]   # 30 < 40
