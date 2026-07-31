"""test_cli_commands.py — render i przeplyw komend CLI (MODUL 18).

PO CO: modul mial 0% pokrycia. To on renderuje kupony i typy, ktore user czyta
na ekranie. Bledy renderu nie wywalaja pipeline'u — po prostu pokazuja zla
liczbe albo wywalaja sie na `None` z Groqa, ktory potrafi oddac niepelny JSON.

Testy sprawdzaja tez, ze funkcje interaktywne NIE wolaja Groqa, gdy user
odmowil — kazde zbedne wolanie to spalony kredyt.
"""
from __future__ import annotations

import pandas as pd
import pytest

import footstats.cli_commands as cc


@pytest.fixture
def ekran(capsys):
    """Zwraca funkcje czytajaca to, co poszlo na konsole."""
    return lambda: capsys.readouterr().out


def _typ(**kw) -> dict:
    baza = {"mecz": "Legia vs Lech", "typ": "1", "kurs": 1.85,
            "ev_netto": 4.2, "uzasadnienie": "forma domowa"}
    baza.update(kw)
    return baza


def _kupon(**kw) -> dict:
    baza = {"zdarzenia": [{"nr": 1, "mecz": "Legia vs Lech", "typ": "1", "kurs": 1.85}],
            "kurs_laczny": 2.4, "wygrana_netto": 10.6}
    baza.update(kw)
    return baza


# ── _wyswietl_ai_pewniaczki ─────────────────────────────────────────────────

def test_brak_top3_pokazuje_surowa_odpowiedz(ekran):
    cc._wyswietl_ai_pewniaczki({"_raw": "Groq oddal cos dziwnego"})
    assert "Groq oddal cos dziwnego" in ekran()


def test_brak_top3_spada_na_uzasadnienie(ekran):
    cc._wyswietl_ai_pewniaczki({"uzasadnienie": "brak sensownych typow"})
    assert "brak sensownych typow" in ekran()


def test_renderuje_tabele_top3(ekran):
    cc._wyswietl_ai_pewniaczki({"top3": [_typ(), _typ(mecz="Wisła vs Raków", typ="X")]})
    out = ekran()
    assert "TOP 3" in out
    assert "Legia" in out and "Wisła" in out


def test_ev_dodatnie_i_ujemne_renderuja_sie(ekran):
    cc._wyswietl_ai_pewniaczki({"top3": [_typ(ev_netto=5.0), _typ(ev_netto=-3.0)]})
    out = ekran()
    assert "+5.0%" in out
    assert "-3.0%" in out


def test_niepoprawne_ev_nie_wywala_renderu(ekran):
    """Groq potrafi oddac EV jako tekst — ma sie wyswietlic, nie wysypac."""
    cc._wyswietl_ai_pewniaczki({"top3": [_typ(ev_netto="wysokie")]})
    assert "wysokie" in ekran()


def test_brak_ev_daje_znak_zapytania(ekran):
    cc._wyswietl_ai_pewniaczki({"top3": [_typ(ev_netto=None)]})
    assert "?" in ekran()


def test_puste_top3_nie_wywala(ekran):
    cc._wyswietl_ai_pewniaczki({"top3": []})
    assert "TOP 3" in ekran()


def test_panele_kuponow_a_i_b(ekran):
    cc._wyswietl_ai_pewniaczki(
        {"top3": [], "kupon_a": _kupon(), "kupon_b": _kupon(kurs_laczny=8.1)},
        stawka=10.0,
    )
    out = ekran()
    assert "KUPON A" in out and "KUPON B" in out
    assert "10 PLN" in out


def test_brak_kuponu_nie_renderuje_panelu(ekran):
    cc._wyswietl_ai_pewniaczki({"top3": [], "kupon_a": None})
    assert "KUPON A" not in ekran()


def test_niepelne_zdarzenie_kuponu_nie_wywala(ekran):
    cc._wyswietl_ai_pewniaczki({"top3": [], "kupon_a": {"zdarzenia": [{}]}})
    assert "?" in ekran()


def test_ostrzezenia_renderowane(ekran):
    cc._wyswietl_ai_pewniaczki({"top3": [], "ostrzezenia": "bankroll nisko"})
    assert "bankroll nisko" in ekran()


# ── _reinicjuj_systemy ──────────────────────────────────────────────────────

def test_reinicjuj_systemy_zwraca_komplet(df_mecze_minimal):
    tabela = pd.DataFrame({"druzyna": ["Arsenal", "Chelsea"], "pozycja": [1, 2],
                           "punkty": [40, 35], "mecze": [20, 20]})
    systemy = cc._reinicjuj_systemy(tabela, df_mecze_minimal, 2, "E0")

    assert set(systemy) == {"importance", "heurystyka_eng", "h2h_sys",
                            "fortress_sys", "klasyfikator", "dw_sys"}
    assert all(v is not None for v in systemy.values())


# ── _wyswietl_menu_startowe ─────────────────────────────────────────────────

def test_menu_z_bzzoiro_oferuje_pewniaczki(ekran):
    cc._wyswietl_menu_startowe(bzzoiro=object())
    assert "Szybkie Pewniaczki" in ekran()


def test_menu_bez_bzzoiro_prosi_o_klucz(ekran):
    cc._wyswietl_menu_startowe(bzzoiro=None)
    out = ekran()
    assert "BZZOIRO_KEY" in out
    assert "Szybkie Pewniaczki 48h" not in out


# ── _ai_blok_pewniaczki ─────────────────────────────────────────────────────

def test_blok_ai_pomija_pusta_liste(monkeypatch):
    wolania = []
    monkeypatch.setattr(cc, "ai_groq_dostepny", lambda: wolania.append("sprawdzono"))
    cc._ai_blok_pewniaczki([])
    assert wolania == [], "sprawdzano Groqa mimo braku typow"


def test_blok_ai_konczy_gdy_brak_klucza(monkeypatch, ekran):
    monkeypatch.setattr(cc, "ai_groq_dostepny", lambda: False)
    cc._ai_blok_pewniaczki([{"mecz": "A vs B"}])
    assert "AI niedostepne" in ekran()


def test_blok_ai_nie_wola_groqa_po_odmowie(monkeypatch):
    wolania = []
    monkeypatch.setattr(cc, "ai_groq_dostepny", lambda: True)
    monkeypatch.setattr(cc.Confirm, "ask", lambda *a, **k: False)
    monkeypatch.setattr(cc, "ai_analiza_pewniaczki",
                        lambda w: wolania.append("wywolano") or {})
    cc._ai_blok_pewniaczki([{"mecz": "A vs B"}])
    assert wolania == [], "user odmowil, a Groq i tak zapytany"


def test_blok_ai_renderuje_analize_i_nie_pyta_o_kupon(monkeypatch, ekran):
    odpowiedzi = iter([True, False])       # zgoda na analizę, odmowa kuponu
    monkeypatch.setattr(cc, "ai_groq_dostepny", lambda: True)
    monkeypatch.setattr(cc.Confirm, "ask", lambda *a, **k: next(odpowiedzi))
    monkeypatch.setattr(cc, "ai_analiza_pewniaczki",
                        lambda w: {"top3": [_typ()], "kupon_a": _kupon()})
    sprawdzone = []
    monkeypatch.setattr(cc, "ai_sprawdz_kupon",
                        lambda *a, **k: sprawdzone.append(a) or "ocena")

    cc._ai_blok_pewniaczki([{"mecz": "A vs B"}])

    assert "Legia" in ekran()
    assert sprawdzone == []


def test_blok_ai_lapie_blad_analizy(monkeypatch, ekran):
    monkeypatch.setattr(cc, "ai_groq_dostepny", lambda: True)
    monkeypatch.setattr(cc.Confirm, "ask", lambda *a, **k: True)

    def _wybuch(w):
        raise RuntimeError("Groq 503")

    monkeypatch.setattr(cc, "ai_analiza_pewniaczki", _wybuch)
    cc._ai_blok_pewniaczki([{"mecz": "A vs B"}])
    assert "AI blad" in ekran()


def test_blok_ai_sprawdza_kupon_uzytkownika(monkeypatch, ekran):
    monkeypatch.setattr(cc, "ai_groq_dostepny", lambda: True)
    monkeypatch.setattr(cc.Confirm, "ask", lambda *a, **k: True)
    monkeypatch.setattr(cc, "ai_analiza_pewniaczki", lambda w: {"top3": []})
    pytania = iter(["Legia 1 @1.85", "12"])
    monkeypatch.setattr(cc.Prompt, "ask", lambda *a, **k: next(pytania))

    przechwycone = {}

    def _ocen(picks_text, stawka, wzorzec_ml=None):
        przechwycone.update(picks=picks_text, stawka=stawka)
        return "Kupon rozsadny"

    monkeypatch.setattr(cc, "ai_sprawdz_kupon", _ocen)
    cc._ai_blok_pewniaczki([{"mecz": "A vs B"}])

    assert przechwycone["picks"] == "Legia 1 @1.85"
    assert przechwycone["stawka"] == 12.0
    assert "Kupon rozsadny" in ekran()


def test_pusty_kupon_uzytkownika_konczy_bez_wolania_ai(monkeypatch):
    monkeypatch.setattr(cc, "ai_groq_dostepny", lambda: True)
    monkeypatch.setattr(cc.Confirm, "ask", lambda *a, **k: True)
    monkeypatch.setattr(cc, "ai_analiza_pewniaczki", lambda w: {"top3": []})
    monkeypatch.setattr(cc.Prompt, "ask", lambda *a, **k: "   ")
    wolania = []
    monkeypatch.setattr(cc, "ai_sprawdz_kupon",
                        lambda *a, **k: wolania.append(a) or "x")

    cc._ai_blok_pewniaczki([{"mecz": "A vs B"}])
    assert wolania == []


def test_niepoprawna_stawka_spada_na_domyslna(monkeypatch):
    monkeypatch.setattr(cc, "ai_groq_dostepny", lambda: True)
    monkeypatch.setattr(cc.Confirm, "ask", lambda *a, **k: True)
    monkeypatch.setattr(cc, "ai_analiza_pewniaczki", lambda w: {"top3": []})
    pytania = iter(["Legia 1 @1.85", "duzo"])
    monkeypatch.setattr(cc.Prompt, "ask", lambda *a, **k: next(pytania))

    przechwycone = {}
    monkeypatch.setattr(cc, "ai_sprawdz_kupon",
                        lambda picks, stawka, wzorzec_ml=None:
                        przechwycone.update(stawka=stawka) or "ok")

    cc._ai_blok_pewniaczki([{"mecz": "A vs B"}])
    assert przechwycone["stawka"] == 5.0
