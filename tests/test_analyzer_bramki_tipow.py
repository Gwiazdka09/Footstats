"""test_analyzer_bramki_tipow.py — guardy selekcji Groq i przycinanie kuponów.

PO CO: to są bramki, które stoją MIĘDZY odpowiedzią modelu językowego a gotowym
kuponem. LLM analizuje, ale to model probabilistyczny ma decydować — te funkcje
egzekwują ten podział.

`koryguj_tip_wg_modelu` powstał z konkretnego pomiaru: Groq systematycznie
wybierał wyjazdy i remisy przeciw faworytom-gospodarzom i miał na tip=2
trafność 12,5%. Próg 33% złapał pełne +12 pp (argmax modelu 60% vs Groq 48%);
próg 15 był bezużyteczny, bo nie zmieniał niczego.

`_wymusz_40pct` przycina kupon od NAJSŁABSZEJ nogi, dopóki iloczyn szans nie
wejdzie nad próg. Kierunek przycinania jest tu wszystkim: usuwanie od najlepszej
zostawiłoby same śmieci i wyglądałoby tak samo w kodzie.

`_deduplikuj_kupony` usuwa z kuponu B nogi wspólne z A — ale TYLKO te słabe.
Kotwica ≥75% może być w obu, bo to legalna dywersyfikacja, a nie duplikat.
"""
from __future__ import annotations

import pytest

from footstats.ai.analyzer_helpers import (
    _deduplikuj_kupony,
    _wymusz_40pct,
    koryguj_tip_ou_btts,
    koryguj_tip_wg_modelu,
)


# ── koryguj_tip_wg_modelu: 1X2 ─────────────────────────────────────────────

def test_tip_zgodny_z_modelem_zostaje():
    """Model daje 55% na "1" — powyżej progu, więc bez zmian."""
    assert koryguj_tip_wg_modelu("1", 55, 25, 20) == ("1", False)


def test_tip_ponizej_progu_nadpisany_argmaxem():
    """REGRESJA: Groq wybierał wyjazdy przeciw faworytom — tip=2 miał 12.5%."""
    assert koryguj_tip_wg_modelu("2", 60, 25, 15) == ("1", True)


def test_remis_ponizej_progu_nadpisany():
    assert koryguj_tip_wg_modelu("X", 70, 20, 10) == ("1", True)


def test_argmax_rowny_tipowi_nie_jest_nadpisaniem():
    """Gdy najlepszy wybór modelu to i tak wybór Groq — nie ma czego zmieniać,
    nawet jeśli wszystkie prawdopodobieństwa są niskie."""
    assert koryguj_tip_wg_modelu("1", 32, 31, 30) == ("1", False)


def test_prog_jest_wlaczajacy():
    """Dokładnie na progu tip zostaje — próg to minimum akceptowalne."""
    assert koryguj_tip_wg_modelu("2", 40, 27, 33, prog_min=33.0) == ("2", False)


def test_prog_konfigurowalny():
    """Przy niższym progu ten sam tip przechodzi."""
    assert koryguj_tip_wg_modelu("2", 60, 25, 15, prog_min=10.0) == ("2", False)


@pytest.mark.parametrize("tip", ["Over 2.5", "BTTS", "1X", "", "cokolwiek"])
def test_rynki_spoza_1x2_nietkniete(tip):
    """Ten guard dotyczy wyłącznie 1X2 — inne rynki mają własną funkcję."""
    assert koryguj_tip_wg_modelu(tip, 10, 10, 80) == (tip, False)


@pytest.mark.parametrize("prob", [
    (None, 25, 20), (60, None, 20), (60, 25, None), (None, None, None),
])
def test_brak_prawdopodobienstw_nie_rusza_tipu(prob):
    """Mecz spoza pokrycia modelu — nie ma czym nadpisywać, więc nie ruszamy."""
    assert koryguj_tip_wg_modelu("2", *prob) == ("2", False)


# ── koryguj_tip_ou_btts: rynki dwustronne ──────────────────────────────────

@pytest.mark.parametrize("tip", ["Over 2.5", "over 2,5", "OVER", " over "])
def test_over_ponizej_progu_flipuje_na_under(tip):
    assert koryguj_tip_ou_btts(tip, o25=30, bt=None) == ("Under 2.5", True)


def test_over_powyzej_progu_zostaje():
    assert koryguj_tip_ou_btts("Over 2.5", o25=60, bt=None) == ("Over 2.5", False)


@pytest.mark.parametrize("tip", ["Under 2.5", "under 2,5", "UNDER"])
def test_under_flipuje_gdy_model_woli_over(tip):
    """P(Under) = 100 - P(Over); przy o25=70 Under ma tylko 30%."""
    assert koryguj_tip_ou_btts(tip, o25=70, bt=None) == ("Over 2.5", True)


def test_under_zostaje_gdy_model_go_popiera():
    assert koryguj_tip_ou_btts("Under 2.5", o25=40, bt=None) == ("Under 2.5", False)


@pytest.mark.parametrize("tip", ["BTTS", "btts yes", "GG"])
def test_btts_ponizej_progu_flipuje(tip):
    assert koryguj_tip_ou_btts(tip, o25=None, bt=30) == ("BTTS NO", True)


@pytest.mark.parametrize("tip", ["BTTS NO", "btts nie", "NG", "no btts"])
def test_btts_no_flipuje_gdy_model_woli_gg(tip):
    assert koryguj_tip_ou_btts(tip, o25=None, bt=80) == ("BTTS", True)


def test_prog_dwustronny_wlaczajacy():
    """Dokładnie 45% zostaje — flip dopiero PONIŻEJ progu."""
    assert koryguj_tip_ou_btts("Over 2.5", o25=45, bt=None) == ("Over 2.5", False)


@pytest.mark.parametrize("tip", ["1", "X", "2", "handicap", ""])
def test_rynki_1x2_nietkniete_przez_guard_dwustronny(tip):
    assert koryguj_tip_ou_btts(tip, o25=10, bt=10) == (tip, False)


def test_brak_prob_modelu_nie_rusza_tipu():
    assert koryguj_tip_ou_btts("Over 2.5", o25=None, bt=None) == ("Over 2.5", False)


# ── _wymusz_40pct: przycinanie od najsłabszej nogi ─────────────────────────

def _noga(mecz: str, pewnosc: int, kurs: float = 2.0, typ: str = "1") -> dict:
    return {"mecz": mecz, "typ": typ, "pewnosc_pct": pewnosc, "kurs": kurs}


def _kupon(*nogi: dict) -> dict:
    return {"kupon_a": {"zdarzenia": list(nogi)}}


def test_kupon_powyzej_progu_nietkniety():
    dane = _kupon(_noga("A", 80), _noga("B", 70))

    _wymusz_40pct(dane)

    assert len(dane["kupon_a"]["zdarzenia"]) == 2


def test_najslabsza_noga_usuwana_pierwsza():
    """Kierunek przycinania jest tu wszystkim — usuwanie od najlepszej
    zostawiłoby same śmieci i wyglądałoby w kodzie tak samo."""
    dane = _kupon(_noga("mocna", 90), _noga("srednia", 70), _noga("slaba", 30))

    _wymusz_40pct(dane)

    zostale = {z["mecz"] for z in dane["kupon_a"]["zdarzenia"]}
    assert "slaba" not in zostale
    assert "mocna" in zostale


def test_przycinanie_zatrzymuje_sie_nad_progiem():
    """90% × 70% = 63% — to już powyżej 40%, więc dalej nie tniemy."""
    dane = _kupon(_noga("mocna", 90), _noga("srednia", 70), _noga("slaba", 30))

    _wymusz_40pct(dane)

    assert len(dane["kupon_a"]["zdarzenia"]) == 2


def test_zawsze_zostaje_co_najmniej_jedna_noga():
    """Kupon bez nóg to nie kupon — lepiej singiel niż pustka."""
    dane = _kupon(_noga("a", 10), _noga("b", 10), _noga("c", 10))

    _wymusz_40pct(dane)

    assert len(dane["kupon_a"]["zdarzenia"]) == 1


def test_zostaje_najmocniejsza_noga():
    dane = _kupon(_noga("slaba", 10), _noga("mocna", 35), _noga("srednia", 20))

    _wymusz_40pct(dane)

    assert dane["kupon_a"]["zdarzenia"][0]["mecz"] == "mocna"


def test_kurs_przeliczony_po_przycieciu():
    """Kurs sprzed przycięcia opisywałby kupon, którego już nie ma."""
    dane = _kupon(_noga("a", 90, kurs=1.5), _noga("b", 80, kurs=2.0),
                  _noga("c", 20, kurs=5.0))

    _wymusz_40pct(dane)

    assert dane["kupon_a"]["kurs_laczny"] == pytest.approx(3.0)


def test_szansa_przeliczona_po_przycieciu():
    dane = _kupon(_noga("a", 90), _noga("b", 80), _noga("c", 20))

    _wymusz_40pct(dane)

    assert dane["kupon_a"]["szansa_wygranej_pct"] == pytest.approx(72.0)


def test_oba_kupony_przycinane():
    dane = {"kupon_a": {"zdarzenia": [_noga("a1", 90), _noga("a2", 20)]},
            "kupon_b": {"zdarzenia": [_noga("b1", 90), _noga("b2", 20)]}}

    _wymusz_40pct(dane)

    assert len(dane["kupon_a"]["zdarzenia"]) == 1
    assert len(dane["kupon_b"]["zdarzenia"]) == 1


def test_pusty_kupon_pomijany():
    dane = {"kupon_a": {"zdarzenia": []}}

    _wymusz_40pct(dane)  # nie rzuca

    assert dane["kupon_a"]["zdarzenia"] == []


def test_brak_kuponu_nie_wywala():
    dane = {}

    _wymusz_40pct(dane)

    assert dane == {}


def test_prog_konfigurowalny_przy_celu_wygranej():
    """Cel wygranej obniża próg do 5% — nogi o niskiej szansie mają zostać."""
    dane = _kupon(_noga("a", 30), _noga("b", 25))

    _wymusz_40pct(dane, min_szansa=5.0)

    assert len(dane["kupon_a"]["zdarzenia"]) == 2


# ── _deduplikuj_kupony ─────────────────────────────────────────────────────

def test_slaba_noga_wspoldzielona_usuwana_z_b():
    dane = {"kupon_a": {"zdarzenia": [_noga("Legia vs Lech", 50)]},
            "kupon_b": {"zdarzenia": [_noga("Legia vs Lech", 50), _noga("Inny", 80)]}}

    _deduplikuj_kupony(dane)

    assert [z["mecz"] for z in dane["kupon_b"]["zdarzenia"]] == ["Inny"]


def test_kotwica_moze_byc_w_obu_kuponach():
    """Noga ≥75% w obu kuponach to legalna dywersyfikacja, nie duplikat."""
    dane = {"kupon_a": {"zdarzenia": [_noga("Legia vs Lech", 85)]},
            "kupon_b": {"zdarzenia": [_noga("Legia vs Lech", 85), _noga("Inny", 60)]}}

    _deduplikuj_kupony(dane)

    assert len(dane["kupon_b"]["zdarzenia"]) == 2


def test_ten_sam_mecz_inny_typ_to_nie_duplikat():
    """Over i Under na tym samym meczu to różne zakłady."""
    dane = {"kupon_a": {"zdarzenia": [_noga("Legia vs Lech", 50, typ="1")]},
            "kupon_b": {"zdarzenia": [_noga("Legia vs Lech", 50, typ="Over 2.5")]}}

    _deduplikuj_kupony(dane)

    assert len(dane["kupon_b"]["zdarzenia"]) == 1


def test_porownanie_niewrazliwe_na_wielkosc_liter_i_spacje():
    """Groq bywa niekonsekwentny w zapisie — duplikat ma zostać rozpoznany."""
    dane = {"kupon_a": {"zdarzenia": [{"mecz": "Legia vs Lech", "typ": "1",
                                       "pewnosc_pct": 50, "kurs": 2.0}]},
            "kupon_b": {"zdarzenia": [{"mecz": "  LEGIA VS LECH ", "typ": " 1 ",
                                       "pewnosc_pct": 50, "kurs": 2.0}]}}

    _deduplikuj_kupony(dane)

    assert dane["kupon_b"]["zdarzenia"] == []


def test_kurs_i_szansa_przeliczone_po_dedupie():
    dane = {"kupon_a": {"zdarzenia": [_noga("wspolna", 50)]},
            "kupon_b": {"zdarzenia": [_noga("wspolna", 50, kurs=3.0),
                                      _noga("wlasna", 80, kurs=1.5)]}}

    _deduplikuj_kupony(dane)

    assert dane["kupon_b"]["kurs_laczny"] == pytest.approx(1.5)
    assert dane["kupon_b"]["szansa_wygranej_pct"] == pytest.approx(80.0)


def test_pusty_kupon_b_po_dedupie_ma_zerowa_szanse():
    """Kupon bez nóg nie może zostać z kursem sprzed przycięcia."""
    dane = {"kupon_a": {"zdarzenia": [_noga("wspolna", 50)]},
            "kupon_b": {"zdarzenia": [_noga("wspolna", 50, kurs=3.0)]}}

    _deduplikuj_kupony(dane)

    assert dane["kupon_b"]["zdarzenia"] == []
    assert dane["kupon_b"]["kurs_laczny"] == 1.0
    assert dane["kupon_b"]["szansa_wygranej_pct"] == 0.0


def test_dedup_oznacza_kupon():
    dane = {"kupon_a": {"zdarzenia": [_noga("wspolna", 50)]},
            "kupon_b": {"zdarzenia": [_noga("wspolna", 50), _noga("inna", 80)]}}

    _deduplikuj_kupony(dane)

    assert dane["kupon_b"]["_deduped"] is True


def test_brak_zmian_nie_oznacza_kuponu():
    """Flaga `_deduped` ma znaczyć "coś usunięto", nie "sprawdzono"."""
    dane = {"kupon_a": {"zdarzenia": [_noga("a", 50)]},
            "kupon_b": {"zdarzenia": [_noga("b", 50)]}}

    _deduplikuj_kupony(dane)

    assert "_deduped" not in dane["kupon_b"]


@pytest.mark.parametrize("dane", [
    {},
    {"kupon_a": {"zdarzenia": []}, "kupon_b": {"zdarzenia": [{"mecz": "x", "typ": "1"}]}},
    {"kupon_a": {"zdarzenia": [{"mecz": "x", "typ": "1"}]}, "kupon_b": {"zdarzenia": []}},
])
def test_brakujacy_kupon_nie_wywala(dane):
    _deduplikuj_kupony(dane)
