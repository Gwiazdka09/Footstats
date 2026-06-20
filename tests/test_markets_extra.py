"""Opcjonalne rynki (06-20): dokładny wynik + multigoal — generacja i settlement."""
from footstats.utils.betting import oblicz_tip_correct
from footstats.core.markets import build_market_catalog


# ── Settlement: dokładny wynik ────────────────────────────────────────────
def test_dokladny_wynik_trafiony():
    assert oblicz_tip_correct("Wynik 2:1", "2-1") == 1
    assert oblicz_tip_correct("WYNIK 2:1", (2, 1)) == 1
    assert oblicz_tip_correct("2:1", "2-1") == 1


def test_dokladny_wynik_nietrafiony():
    assert oblicz_tip_correct("Wynik 2:1", "1-1") == 0
    assert oblicz_tip_correct("Wynik 2:1", "2-0") == 0
    # odwrócony wynik to NIE to samo
    assert oblicz_tip_correct("Wynik 2:1", "1-2") == 0


def test_dokladny_wynik_brak_bramek_none():
    assert oblicz_tip_correct("Wynik 2:1", "1") is None


# ── Settlement: multigoal ─────────────────────────────────────────────────
def test_multigoal_w_przedziale():
    assert oblicz_tip_correct("Multigoal 2-3", "2-1") == 1   # total=3
    assert oblicz_tip_correct("Multigoal 2-3", "1-1") == 1   # total=2
    assert oblicz_tip_correct("MULTIGOAL 4-6", "3-2") == 1   # total=5


def test_multigoal_poza_przedzialem():
    assert oblicz_tip_correct("Multigoal 2-3", "0-1") == 0   # total=1
    assert oblicz_tip_correct("Multigoal 2-3", "3-1") == 0   # total=4


def test_multigoal_granice_wlacznie():
    assert oblicz_tip_correct("Multigoal 1-2", "1-0") == 1   # dolna granica
    assert oblicz_tip_correct("Multigoal 1-2", "1-1") == 1   # górna granica


# ── Generacja: katalog zawiera nowe grupy, tipy rozliczalne ───────────────
def test_katalog_ma_dokladny_wynik_i_multigoal():
    grupy = build_market_catalog(1.6, 1.1)
    nazwy = {g["grupa"] for g in grupy}
    assert "Dokładny wynik" in nazwy
    assert "Multigoal" in nazwy


def test_katalog_tipy_sa_rozliczalne():
    # Każdy tip z nowych grup musi być rozliczalny przez oblicz_tip_correct (nie None na realnym wyniku).
    grupy = build_market_catalog(1.6, 1.1)
    for g in grupy:
        if g["grupa"] in ("Dokładny wynik", "Multigoal"):
            for r in g["rynki"]:
                assert oblicz_tip_correct(r["tip"], "2-1") in (0, 1), f"nierozliczalny: {r['tip']}"


def test_katalog_kursy_dodatnie():
    grupy = build_market_catalog(1.6, 1.1)
    for g in grupy:
        for r in g["rynki"]:
            assert r["kurs"] > 1.0, f"{r['rynek']} kurs {r['kurs']} <= 1.0"
