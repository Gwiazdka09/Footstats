"""test_analyzer_scout_bloki.py — scout filter + bloki wstrzykiwane do promptu.

`oceń_kupon` to BRAMKA: score < 50 wetuje kupon. Parsowanie score'a z odpowiedzi
LLM-a bylo nieprzetestowane, a od niego zalezy, czy kupon w ogole powstanie.
Blad w tym parserze = albo wszystko przechodzi, albo nic.

Bloki `_get_kalibracja_blok` / `_get_liga_statystyki_blok` wchodza wprost do
promptu — gdy cicho zwroca "", model traci kontekst historyczny i nikt tego
nie widzi po wyniku.
"""
from __future__ import annotations

import pytest

from footstats.ai.analyzer import (
    _SCOUT_VETO_THRESHOLD,
    _get_kalibracja_blok,
    _get_liga_statystyki_blok,
    ai_groq_dostepny,
    oceń_kupon,
)


def _noga(**kw) -> dict:
    baza = {"home": "Legia", "away": "Lech", "tip": "1", "odds": 1.85,
            "prob": 0.55, "ev_netto": 0.04}
    baza.update(kw)
    return baza


@pytest.fixture
def llm(monkeypatch):
    """Podstawia _zapytaj_typera; zwraca liste promptow i pozwala ustawic odpowiedz."""
    stan = {"odpowiedz": "Analiza OK\nSCORE: 72", "prompty": []}

    def _fake(prompt: str, max_tokens: int = 600) -> str:
        stan["prompty"].append(prompt)
        if isinstance(stan["odpowiedz"], Exception):
            raise stan["odpowiedz"]
        return stan["odpowiedz"]

    import footstats.ai.analyzer as an
    monkeypatch.setattr(an, "_zapytaj_typera", _fake)
    return stan


# ── oceń_kupon ──────────────────────────────────────────────────────────────

def test_pusty_kupon_dostaje_zero_bez_pytania_llm(llm):
    reasoning, score = oceń_kupon([])
    assert score == 0
    assert llm["prompty"] == [], "zapytano LLM o pusty kupon — palenie kredytów"


def test_parsuje_score_z_odpowiedzi(llm):
    llm["odpowiedz"] = "Nogi solidne.\nSCORE: 81"
    reasoning, score = oceń_kupon([_noga()])
    assert score == 81
    assert "Nogi solidne" in reasoning


def test_bierze_ostatni_score_gdy_kilka(llm):
    """LLM potrafi rozmyslac na glos — liczy sie werdykt koncowy."""
    llm["odpowiedz"] = "SCORE: 30\npo namysle jednak lepiej\nSCORE: 65"
    assert oceń_kupon([_noga()])[1] == 65


def test_score_przycinany_do_zakresu_0_100(llm):
    llm["odpowiedz"] = "SCORE: 250"
    assert oceń_kupon([_noga()])[1] == 100
    llm["odpowiedz"] = "SCORE: -40"
    assert oceń_kupon([_noga()])[1] == 0


def test_niepoprawny_score_spada_na_prog_weta(llm):
    llm["odpowiedz"] = "SCORE: bardzo dobrze"
    assert oceń_kupon([_noga()])[1] == _SCOUT_VETO_THRESHOLD


def test_brak_score_w_odpowiedzi_spada_na_prog(llm):
    llm["odpowiedz"] = "Kupon wyglada rozsadnie, ale bez oceny liczbowej."
    assert oceń_kupon([_noga()])[1] == _SCOUT_VETO_THRESHOLD


def test_score_rozpoznawany_niezaleznie_od_wielkosci_liter(llm):
    llm["odpowiedz"] = "score: 44"
    assert oceń_kupon([_noga()])[1] == 44


def test_awaria_llm_nie_blokuje_pipeline(llm):
    """Padniety Groq ma dac neutralny prog, a nie wywalic budowanie kuponu."""
    llm["odpowiedz"] = RuntimeError("Groq 503")
    reasoning, score = oceń_kupon([_noga()])
    assert score == _SCOUT_VETO_THRESHOLD
    assert "niedostępny" in reasoning


def test_prompt_zawiera_wszystkie_nogi(llm):
    oceń_kupon([_noga(home="A", away="B"), _noga(home="C", away="D")])
    prompt = llm["prompty"][0]
    assert "A vs B" in prompt and "C vs D" in prompt
    assert "1." in prompt and "2." in prompt


def test_prompt_akceptuje_alternatywne_nazwy_pol(llm):
    """Nogi z quick_picks maja `kurs`/`pw_cal` zamiast `odds`/`prob`."""
    oceń_kupon([{"home": "A", "away": "B", "tip": "X", "kurs": 3.4, "pw_cal": 0.29}])
    prompt = llm["prompty"][0]
    assert "3.4" in prompt and "0.29" in prompt


def test_kontekst_trafia_do_promptu(llm):
    oceń_kupon([_noga()], kontekst="Legia bez trzech obrońców")
    assert "bez trzech obrońców" in llm["prompty"][0]


# ── bloki do promptu ────────────────────────────────────────────────────────

def test_kalibracja_zwraca_tekst_z_trenera(monkeypatch):
    import footstats.ai.trainer as tr
    monkeypatch.setattr(tr, "get_kalibracja_inject", lambda: "KALIBRACJA: obniż o 5pp")
    assert _get_kalibracja_blok() == "KALIBRACJA: obniż o 5pp"


def test_kalibracja_cicha_na_blad(monkeypatch):
    import footstats.ai.trainer as tr

    def _wybuch():
        raise KeyError("brak pliku")

    monkeypatch.setattr(tr, "get_kalibracja_inject", _wybuch)
    assert _get_kalibracja_blok() == ""


def test_liga_statystyki_pomija_male_proby(monkeypatch):
    """n < 100 to za malo, zeby cokolwiek sugerowac modelowi."""
    import footstats.ai.trainer as tr
    monkeypatch.setattr(tr, "load_lessons", lambda: {"pattern_summary": {
        "results_by_league": {
            "MALA": {"n": 40, "over25_pct": 70, "home_win": 50},
            "DUZA": {"n": 500, "over25_pct": 52, "btts_pct": 48,
                     "avg_goals": 2.6, "home_win": 44},
        }}})
    blok = _get_liga_statystyki_blok()
    assert "DUZA" in blok
    assert "MALA" not in blok


def test_liga_statystyki_oznacza_marchewke_i_przewage_domu(monkeypatch):
    import footstats.ai.trainer as tr
    monkeypatch.setattr(tr, "load_lessons", lambda: {"pattern_summary": {
        "results_by_league": {
            "GOLOWA": {"n": 300, "over25_pct": 62, "btts_pct": 55,
                       "avg_goals": 3.1, "home_win": 49},
        }}})
    blok = _get_liga_statystyki_blok()
    assert "MARCHEWKA Over2.5" in blok
    assert "silna przewaga domu" in blok


def test_liga_statystyki_puste_gdy_brak_danych(monkeypatch):
    import footstats.ai.trainer as tr
    monkeypatch.setattr(tr, "load_lessons", lambda: {})
    assert _get_liga_statystyki_blok() == ""


def test_liga_statystyki_ciche_na_blad(monkeypatch):
    import footstats.ai.trainer as tr

    def _wybuch():
        raise AttributeError("zly ksztalt")

    monkeypatch.setattr(tr, "load_lessons", _wybuch)
    assert _get_liga_statystyki_blok() == ""


# ── dostepnosc Groqa ────────────────────────────────────────────────────────

def test_groq_dostepny_gdy_klucz_ustawiony(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_cokolwiek")
    assert ai_groq_dostepny() is True


@pytest.mark.parametrize("wartosc", ["", "   "])
def test_groq_niedostepny_dla_pustego_klucza(monkeypatch, wartosc):
    monkeypatch.setenv("GROQ_API_KEY", wartosc)
    assert ai_groq_dostepny() is False


def test_groq_niedostepny_bez_zmiennej(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert ai_groq_dostepny() is False
