"""test_analyzer_pewniaczki.py — `ai_analiza_pewniaczki`: od pewniaczków do kuponu.

PO CO: to główny generator typów. Wchodzi lista kandydatów, wychodzi gotowy
kupon. Po odpowiedzi modelu biegnie łańcuch bramek, który decyduje, co realnie
wejdzie do kuponu — i każde ogniwo da się po cichu ominąć:

  * PEWNOŚĆ NÓG nadpisywana prawdopodobieństwem MODELU, nie tym, co Groq sam
    o sobie napisał. To jest sedno "Celu B": bramki mają liczyć się na modelu,
    a nie na deklaracji LLM-a.
  * PRÓG SZANSY zależy od tego, czy podano cel wygranej: bez celu 40%, z celem
    5%. Cel odblokowuje nogi o niskiej szansie — pomylenie tych progów oznacza
    albo kupon nie do trafienia, albo wycięcie wszystkiego.
  * NADPISANIE TIPU argmaxem modelu jest za flagą i domyślnie WYŁĄCZONE.

Gdy model zwróci coś, czego nie da się sparsować, surowy tekst musi zostać
w `_raw` — inaczej ślad po nieudanej analizie znika.
"""
from __future__ import annotations

import pytest

import footstats.ai.analyzer as an


@pytest.fixture
def rura(monkeypatch):
    """Podstawia wszystko wokół `ai_analiza_pewniaczki`; notuje wywołania bramek."""
    stan: dict = {
        "odpowiedz": '{"top3": []}',
        "prompty": [],
        "wywolane": [],
        "progi": [],
    }

    # `**kw` przyjmuje `schemat` dodany 31.08 — atrapa ma nie rozjezdzac sie
    # z sygnatura produkcyjna przy kazdym nowym parametrze.
    def fake_typer(prompt, max_tokens=1500, **kw):
        stan["prompty"].append(prompt)
        return stan["odpowiedz"]

    def notuj(nazwa):
        def _f(*a, **kw):
            stan["wywolane"].append(nazwa)
        return _f

    def fake_wymusz(dane, min_szansa):
        stan["wywolane"].append("_wymusz_40pct")
        stan["progi"].append(min_szansa)

    monkeypatch.setattr(an, "_zapytaj_typera", fake_typer)
    monkeypatch.setattr(an, "_wzbogac_forme", notuj("_wzbogac_forme"))
    monkeypatch.setattr(an, "_nadpisz_tip_modelem", notuj("_nadpisz_tip_modelem"))
    monkeypatch.setattr(an, "_nadpisz_pewnosc_modelem", notuj("_nadpisz_pewnosc_modelem"))
    monkeypatch.setattr(an, "_deduplikuj_kupony", notuj("_deduplikuj_kupony"))
    monkeypatch.setattr(an, "_auto_zapisz_backtest", notuj("_auto_zapisz_backtest"))
    monkeypatch.setattr(an, "_wymusz_40pct", fake_wymusz)
    monkeypatch.setattr(an, "_sygnaly_summary", lambda w: "sygnaly")
    monkeypatch.setattr(an, "_buduj_opis_meczu", lambda w: f"OPIS:{w.get('gospodarz')}")
    monkeypatch.setattr(an, "_pobierz_podobne_mecze", lambda h, a, n=3: "")
    monkeypatch.setattr(an, "get_match_context", lambda *a: "kontekst")
    return stan


def _mecz(gosp="Legia", gosc="Lech", liga="Ekstraklasa") -> dict:
    return {"gospodarz": gosp, "goscie": gosc, "liga": liga,
            "pw": 55, "pr": 25, "pp": 20, "typ_kuponu": "1"}


# ── wejście puste ───────────────────────────────────────────────────────────

def test_brak_pewniaczkow_nie_pyta_modelu(rura):
    """Zapytanie o pustą listę to koszt bez treści."""
    wynik = an.ai_analiza_pewniaczki([])

    assert "_raw" in wynik
    assert rura["prompty"] == []


# ── odpowiedź nie do sparsowania ────────────────────────────────────────────

def test_odpowiedz_bez_top3_zachowuje_surowy_tekst(rura):
    """Bez `_raw` ślad po nieudanej analizie znika bez śladu."""
    rura["odpowiedz"] = "Model napisał esej zamiast JSON-a"

    wynik = an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert wynik["_raw"] == "Model napisał esej zamiast JSON-a"


def test_nieudany_parse_nie_uruchamia_bramek(rura):
    """Bramki na pustym słowniku to praca na niczym.

    UWAGA — od A1 (08.2026) nieudany parse NIE oznacza już dnia bez typów:
    `ai_analiza_pewniaczki` buduje wtedy `top3` z samego modelu i przepuszcza je
    przez ten sam łańcuch bramek. Ten test opisuje przypadek, w którym awaryjna
    ścieżka nie ma z czego zbudować typu — `_mecz()` nie ma kursów, więc filtry
    selekcji wycinają go w całości. Zachowanie z kursami pilnuje
    `tests/test_typy_bez_llm.py`.
    """
    rura["odpowiedz"] = "nie-json"

    an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert "_wymusz_40pct" not in rura["wywolane"]
    assert "_auto_zapisz_backtest" not in rura["wywolane"]


# ── łańcuch bramek ──────────────────────────────────────────────────────────

def test_pewnosc_nadpisana_modelem(rura):
    """Cel B: bramki mają liczyć się na modelu, nie na deklaracji Groq."""
    an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert "_nadpisz_pewnosc_modelem" in rura["wywolane"]


def test_kolejnosc_bramek(rura):
    """Pewność musi zostać nadpisana PRZED dedupem i progiem szansy —
    inaczej bramki liczą się na liczbach, które Groq napisał sam o sobie."""
    an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    kolejnosc = [k for k in rura["wywolane"]
                 if k in ("_nadpisz_pewnosc_modelem", "_deduplikuj_kupony", "_wymusz_40pct")]
    assert kolejnosc == ["_nadpisz_pewnosc_modelem", "_deduplikuj_kupony", "_wymusz_40pct"]


def test_wynik_zapisany_do_backtestu(rura):
    an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert "_auto_zapisz_backtest" in rura["wywolane"]


# ── próg szansy zależny od celu wygranej ────────────────────────────────────

def test_bez_celu_prog_czterdziesci_procent(rura):
    an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert rura["progi"] == [40.0]


@pytest.mark.parametrize("cel_a,cel_b", [(50.0, None), (None, 100.0), (50.0, 100.0)])
def test_cel_wygranej_obniza_prog(rura, cel_a, cel_b):
    """Cel wygranej świadomie odblokowuje nogi o niskiej szansie."""
    an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False,
                             cel_wygrana_a=cel_a, cel_wygrana_b=cel_b)

    assert rura["progi"] == [5.0]


def test_cel_zero_to_nadal_cel(rura):
    """0.0 to podana wartość, nie jej brak — `is not None`, nie truthiness."""
    an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False, cel_wygrana_a=0.0)

    assert rura["progi"] == [5.0]


# ── nadpisanie tipu jest za flagą ───────────────────────────────────────────

def test_nadpisanie_tipu_domyslnie_wylaczone(rura, monkeypatch):
    import footstats.config as cfg
    monkeypatch.setattr(cfg, "GROQ_TIP_OVERRIDE", False)

    an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert "_nadpisz_tip_modelem" not in rura["wywolane"]


def test_nadpisanie_tipu_po_wlaczeniu_flagi(rura, monkeypatch):
    import footstats.config as cfg
    monkeypatch.setattr(cfg, "GROQ_TIP_OVERRIDE", True)

    an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert "_nadpisz_tip_modelem" in rura["wywolane"]


def test_tip_nadpisany_przed_pewnoscia(rura, monkeypatch):
    """Nadpisany tip musi wejść PRZED bramkami, żeby się na nim liczyły."""
    import footstats.config as cfg
    monkeypatch.setattr(cfg, "GROQ_TIP_OVERRIDE", True)

    an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert (rura["wywolane"].index("_nadpisz_tip_modelem")
            < rura["wywolane"].index("_nadpisz_pewnosc_modelem"))


# ── pobieranie formy ────────────────────────────────────────────────────────

def test_forma_nie_pobierana_na_zadanie(rura):
    """SofaScore to Playwright i minuty — musi dać się wyłączyć."""
    an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert "_wzbogac_forme" not in rura["wywolane"]


def test_forma_pobierana_domyslnie(rura):
    an.ai_analiza_pewniaczki([_mecz()])

    assert "_wzbogac_forme" in rura["wywolane"]


def test_awaria_kontekstu_nie_zatrzymuje_analizy(rura, monkeypatch):
    """Brak xG/tabeli to gorszy prompt, nie brak typów."""
    def wybucha(*a):
        raise OSError("scraper padl")

    monkeypatch.setattr(an, "get_match_context", wybucha)

    wynik = an.ai_analiza_pewniaczki([_mecz()])

    assert "_raw" not in wynik


# ── prompt ──────────────────────────────────────────────────────────────────

def test_do_promptu_trafia_najwyzej_piec_meczow(rura):
    """Limit jest po to, żeby prompt nie urósł ponad okno modelu."""
    mecze = [_mecz(gosp=f"Klub{i}") for i in range(9)]

    an.ai_analiza_pewniaczki(mecze, pobierz_forme=False)

    prompt = rura["prompty"][0]
    assert prompt.count("OPIS:") == 5
    assert "Klub5" not in prompt


def test_kontekst_rag_doklejony_do_promptu(rura, monkeypatch):
    monkeypatch.setattr(an, "_pobierz_podobne_mecze",
                        lambda h, a, n=3: "\nPODOBNE: Legia lubi remisowac\n")

    an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert "Legia lubi remisowac" in rura["prompty"][0]


def test_awaria_kalibracji_nie_zatrzymuje_analizy(rura, monkeypatch):
    import footstats.core.backtest as bt

    def wybucha():
        raise RuntimeError("brak bazy backtestu")

    monkeypatch.setattr(bt, "pobierz_kalibracje_backtest", wybucha)

    wynik = an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert "_raw" not in wynik


def test_awaria_feedbacku_nie_zatrzymuje_analizy(rura, monkeypatch):
    import footstats.ai.rag as rag

    def wybucha(*a, **kw):
        raise RuntimeError("brak embeddingow")

    monkeypatch.setattr(rag, "retrieve_relevant_lessons", wybucha)

    wynik = an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert "_raw" not in wynik
