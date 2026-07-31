"""test_analyzer_helpers_kupony.py — bramki jakosci kuponu po stronie Pythona.

PO CO: `_wymusz_40pct` i `_deduplikuj_kupony` to OSTATNIA linia obrony przed
tym, co wymysli Groq. Jesli przestana dzialac, do bazy trafiaja kupony
o szansie 8% podane jako "40%+", a nikt tego nie zobaczy — model zawsze
raportuje, ze jest dobrze.

`_wyciagnij_json` to wejscie do calego parsowania odpowiedzi LLM. Groq
regularnie opakowuje JSON w tekst albo bloki markdown; kazdy taki przypadek
musi konczyc sie slownikiem, nigdy wyjatkiem.
"""
from __future__ import annotations

import pytest

from footstats.ai.analyzer_helpers import (
    _deduplikuj_kupony,
    _wyciagnij_json,
    _wymusz_40pct,
)


def _noga(mecz="Legia vs Lech", typ="1", kurs=1.8, pewnosc=70) -> dict:
    return {"mecz": mecz, "typ": typ, "kurs": kurs, "pewnosc_pct": pewnosc}


# ── _wyciagnij_json ─────────────────────────────────────────────────────────

def test_czysty_json():
    assert _wyciagnij_json('{"typ": "1", "pewnosc": 70}') == {"typ": "1", "pewnosc": 70}


def test_json_otoczony_tekstem():
    """Groq lubi dopisac 'Oto analiza:' przed JSON-em."""
    tekst = 'Oto moja analiza:\n{"typ": "X", "pewnosc": 55}\nMam nadzieje, ze pomoglem.'
    assert _wyciagnij_json(tekst)["typ"] == "X"


def test_json_w_bloku_markdown():
    tekst = '```json\n{"typ": "2", "pewnosc": 61}\n```'
    assert _wyciagnij_json(tekst)["pewnosc"] == 61


def test_zagniezdzony_json_bierze_caly_blok():
    tekst = '{"kupon_a": {"zdarzenia": [{"typ": "1"}]}, "top3": []}'
    wynik = _wyciagnij_json(tekst)
    assert wynik["kupon_a"]["zdarzenia"][0]["typ"] == "1"


def test_smieci_daja_bezpieczny_fallback():
    """Nie moze rzucic — pipeline poleci dalej z 'brak'."""
    wynik = _wyciagnij_json("kompletnie niepoprawna odpowiedz bez nawiasow")
    assert wynik["typ"] == "brak"
    assert wynik["pewnosc"] == 0
    assert wynik["value_bet"] is False
    assert "niepoprawna" in wynik["uzasadnienie"]


def test_uszkodzony_json_w_nawiasach_tez_daje_fallback():
    wynik = _wyciagnij_json('{"typ": "1", "pewnosc":}')
    assert wynik["typ"] == "brak"


def test_fallback_przycina_dlugi_tekst():
    assert len(_wyciagnij_json("x" * 900)["uzasadnienie"]) <= 300


# ── _wymusz_40pct ───────────────────────────────────────────────────────────

def test_kupon_powyzej_progu_zostaje_nietkniety():
    dane = {"kupon_a": {"zdarzenia": [_noga(pewnosc=80), _noga(mecz="B", pewnosc=70)]}}
    _wymusz_40pct(dane)
    assert len(dane["kupon_a"]["zdarzenia"]) == 2
    assert dane["kupon_a"]["szansa_wygranej_pct"] == 56.0     # 0.8 * 0.7


def test_przycina_najslabsza_noge_dopoki_prog_nieosiagniety():
    """3 nogi 70/60/50 = 21% → wypada najslabsza (50), zostaje 0.7*0.6 = 42% ≥ 40 → stop.

    Petla przycina TYLKO tyle, ile trzeba — nie zjada calego kuponu.
    """
    dane = {"kupon_a": {"zdarzenia": [
        _noga(mecz="A", pewnosc=70), _noga(mecz="B", pewnosc=60),
        _noga(mecz="C", pewnosc=50),
    ]}}
    _wymusz_40pct(dane)

    zostale = {z["mecz"] for z in dane["kupon_a"]["zdarzenia"]}
    assert zostale == {"A", "B"}
    assert dane["kupon_a"]["szansa_wygranej_pct"] == 42.0


def test_przycina_wielokrotnie_az_do_jednej_nogi():
    """4 nogi 60/55/50/45: 7.4% → 16.5% → 33% → wciaz <40, wiec zostaje sama 60%.

    Petla tnie dopoki `len > 1`, wiec przy slabym zestawie konczy na singlu —
    i to jest zamierzone: lepszy single niz AKO ponizej progu.
    """
    dane = {"kupon_a": {"zdarzenia": [
        _noga(mecz="A", pewnosc=60), _noga(mecz="B", pewnosc=55),
        _noga(mecz="C", pewnosc=50), _noga(mecz="D", pewnosc=45),
    ]}}
    _wymusz_40pct(dane)

    assert {z["mecz"] for z in dane["kupon_a"]["zdarzenia"]} == {"A"}
    assert dane["kupon_a"]["szansa_wygranej_pct"] == 60.0


def test_zostawia_minimum_jedna_noge_nawet_ponizej_progu():
    dane = {"kupon_a": {"zdarzenia": [_noga(pewnosc=20)]}}
    _wymusz_40pct(dane)
    assert len(dane["kupon_a"]["zdarzenia"]) == 1
    assert dane["kupon_a"]["szansa_wygranej_pct"] == 20.0


def test_przelicza_kurs_laczny_po_przycieciu():
    dane = {"kupon_a": {"zdarzenia": [
        _noga(mecz="A", kurs=2.0, pewnosc=90), _noga(mecz="B", kurs=3.0, pewnosc=20),
    ]}}
    _wymusz_40pct(dane)
    assert dane["kupon_a"]["kurs_laczny"] == 2.0, "kurs usunietej nogi zostal w iloczynie"


def test_oznacza_kupon_jako_przyciety():
    dane = {"kupon_a": {"zdarzenia": [_noga(pewnosc=90), _noga(mecz="B", pewnosc=90)]}}
    _wymusz_40pct(dane)
    assert dane["kupon_a"]["_trimmed"] is True


def test_obsluguje_oba_kupony():
    dane = {
        "kupon_a": {"zdarzenia": [_noga(pewnosc=90)]},
        "kupon_b": {"zdarzenia": [_noga(mecz="B", pewnosc=30), _noga(mecz="C", pewnosc=30)]},
    }
    _wymusz_40pct(dane)
    assert len(dane["kupon_b"]["zdarzenia"]) == 1


def test_pusty_kupon_pomijany():
    dane = {"kupon_a": {"zdarzenia": []}}
    _wymusz_40pct(dane)
    assert "_trimmed" not in dane["kupon_a"]


def test_brak_pewnosci_traktowany_jak_50():
    dane = {"kupon_a": {"zdarzenia": [{"mecz": "A", "kurs": 2.0}]}}
    _wymusz_40pct(dane)
    assert dane["kupon_a"]["szansa_wygranej_pct"] == 50.0


def test_wlasny_prog_respektowany():
    dane = {"kupon_a": {"zdarzenia": [
        _noga(mecz="A", pewnosc=80), _noga(mecz="B", pewnosc=80),
    ]}}
    _wymusz_40pct(dane, min_szansa=70.0)      # 0.8*0.8=64% < 70 → przytnij
    assert len(dane["kupon_a"]["zdarzenia"]) == 1


# ── _deduplikuj_kupony ──────────────────────────────────────────────────────

def test_usuwa_z_b_slaba_noge_wspoldzielona_z_a():
    dane = {
        "kupon_a": {"zdarzenia": [_noga(mecz="Legia vs Lech", pewnosc=60)]},
        "kupon_b": {"zdarzenia": [
            _noga(mecz="Legia vs Lech", pewnosc=60),
            _noga(mecz="Wisła vs Raków", pewnosc=65),
        ]},
    }
    _deduplikuj_kupony(dane)
    mecze_b = {z["mecz"] for z in dane["kupon_b"]["zdarzenia"]}
    assert mecze_b == {"Wisła vs Raków"}
    assert dane["kupon_b"]["_deduped"] is True


def test_kotwica_moze_byc_w_obu_kuponach():
    """Noga >=75% to legalna dywersyfikacja, nie duplikat do wyciecia."""
    dane = {
        "kupon_a": {"zdarzenia": [_noga(mecz="Celtic vs Dundee", pewnosc=85)]},
        "kupon_b": {"zdarzenia": [_noga(mecz="Celtic vs Dundee", pewnosc=85)]},
    }
    _deduplikuj_kupony(dane)
    assert len(dane["kupon_b"]["zdarzenia"]) == 1
    assert "_deduped" not in dane["kupon_b"]


def test_dopasowanie_ignoruje_wielkosc_liter_i_spacje():
    dane = {
        "kupon_a": {"zdarzenia": [_noga(mecz="Legia vs Lech", typ="1", pewnosc=60)]},
        "kupon_b": {"zdarzenia": [_noga(mecz="  LEGIA VS LECH  ", typ=" 1 ", pewnosc=60)]},
    }
    _deduplikuj_kupony(dane)
    assert dane["kupon_b"]["zdarzenia"] == []


def test_ten_sam_mecz_inny_typ_zostaje():
    dane = {
        "kupon_a": {"zdarzenia": [_noga(typ="1", pewnosc=60)]},
        "kupon_b": {"zdarzenia": [_noga(typ="Over 2.5", pewnosc=60)]},
    }
    _deduplikuj_kupony(dane)
    assert len(dane["kupon_b"]["zdarzenia"]) == 1


def test_przelicza_kurs_i_szanse_po_wycieciu():
    dane = {
        "kupon_a": {"zdarzenia": [_noga(mecz="A", pewnosc=60)]},
        "kupon_b": {"zdarzenia": [
            _noga(mecz="A", pewnosc=60),
            _noga(mecz="B", kurs=2.0, pewnosc=50),
        ]},
    }
    _deduplikuj_kupony(dane)
    assert dane["kupon_b"]["kurs_laczny"] == 2.0
    assert dane["kupon_b"]["szansa_wygranej_pct"] == 50.0


def test_wyciecie_wszystkiego_zeruje_szanse():
    dane = {
        "kupon_a": {"zdarzenia": [_noga(mecz="A", pewnosc=60)]},
        "kupon_b": {"zdarzenia": [_noga(mecz="A", pewnosc=60)]},
    }
    _deduplikuj_kupony(dane)
    assert dane["kupon_b"]["zdarzenia"] == []
    assert dane["kupon_b"]["kurs_laczny"] == 1.0
    assert dane["kupon_b"]["szansa_wygranej_pct"] == 0.0


@pytest.mark.parametrize("dane", [
    {},
    {"kupon_a": {"zdarzenia": []}, "kupon_b": {"zdarzenia": [_noga()]}},
    {"kupon_a": {"zdarzenia": [_noga()]}, "kupon_b": {"zdarzenia": []}},
    {"kupon_a": None, "kupon_b": None},
])
def test_brak_ktoregos_kuponu_nie_wywala(dane):
    _deduplikuj_kupony(dane)          # nie rzuca
