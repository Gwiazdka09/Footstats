"""A2/A3 — do `predictions` trafia to, co system NAPRAWDĘ wystawił.

Zapis szedł w KROKU 3 (wewnątrz analizy Groqa), a weryfikacja kursów dopiero
w KROKU 4. Kolejność miała dwie konsekwencje, obie zmierzone na produkcji 23.08:

  * **A2** — słownictwo modelu językowego lądowało w bazie nietknięte. Typ
    `2 (wygrana gościa)` to zwykła „2" z dopiskiem, ale `oblicz_tip_correct`
    zwraca dla niego `None` — taki wiersz NIE ROZLICZY SIĘ NIGDY.
  * **A3** — noga, która nie przeżyła weryfikacji, zostawała w bazie z kursem
    zaproponowanym przez LLM-a (`odds_verified=0`). Uzgodnienie z KROKU 4b nie
    miało czego poprawić, bo poprawia tylko nogi ocalałe.

Naprawa to odwrócenie kolejności: potok dzienny NIE zapisuje w KROKU 3, tylko po
weryfikacji. Weryfikacja jest równocześnie bramką słownikową — przepuszcza wyłącznie
rynki z `_TYP_DO_ODDS_KEY`, czyli te, dla których źródło podaje kurs i które
rozliczenie potrafi policzyć.

Konsekwencja dla A1: skoro typy Groqa mogą wyparować dopiero na weryfikacji, model
dostaje DRUGĄ szansę — już po niej. Bez tego dzień, w którym LLM wytypował same
rynki bez kursu, kończyłby się zerem predykcji mimo gotowych liczb modelu.

Inni wołający (`cli_commands`) nie mają kroku weryfikacji, więc dla nich zapis
w analizie zostaje domyślnie włączony.
"""
from __future__ import annotations

import pytest

import footstats.ai.analyzer as an
import footstats.daily_agent as da


def _mecz(gosp="Legia", gosc="Lech", **nadpisz) -> dict:
    w = {
        "gospodarz": gosp, "goscie": gosc, "liga": "Ekstraklasa",
        "data": "2026-08-23",
        "pw": 70.0, "pr": 20.0, "pp": 10.0, "o25": 30.0, "bt": 30.0,
        "pred": {"p_wygrana": 70.0, "p_remis": 20.0, "p_przegrana": 10.0,
                 "over25": 30.0, "btts": 30.0},
        "odds": {"home": 1.5, "draw": 4.2, "away": 6.0},
        "model_source": "poisson-dc",
    }
    w.update(nadpisz)
    return w


def _indeks(*mecze) -> dict:
    return {
        (da._norm(w["gospodarz"]), da._norm(w["goscie"])): {
            "odds": w.get("odds", {}), "gospodarz": w["gospodarz"],
            "goscie": w["goscie"], "liga": w.get("liga", ""),
            "pred": w.get("pred") or {}, "data": w.get("data", ""),
        }
        for w in mecze
    }


def _przez_potok(dane: dict, wyniki: list, indeks: dict) -> int:
    """Kolejność z `main()`: KROK 4 (weryfikacja) → KROK 4a (zapis).

    Testujemy je razem, bo dopiero para daje gwarancję, o którą chodzi: do bazy
    trafia wyłącznie to, co przeszło bramkę kursów.
    """
    da._weryfikuj_kupony(dane, indeks)
    return da._zapisz_predykcje_po_weryfikacji(dane, wyniki, indeks)


@pytest.fixture
def zapisy(monkeypatch):
    """Przechwytuje wiersze idące do `predictions`."""
    zapisane: list[dict] = []
    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "save_prediction",
                        lambda **kw: zapisane.append(kw) or 1)
    return zapisane


# ── analiza nie zapisuje, gdy woła ją potok dzienny ─────────────────────────

@pytest.fixture
def rura(monkeypatch):
    stan = {"odpowiedz": '{"top3": []}'}
    monkeypatch.setattr(an, "_zapytaj_typera",
                        lambda prompt, max_tokens=1500: stan["odpowiedz"])
    monkeypatch.setattr(an, "_sygnaly_summary", lambda w: "sygnaly")
    monkeypatch.setattr(an, "_buduj_opis_meczu", lambda w: "OPIS")
    monkeypatch.setattr(an, "_pobierz_podobne_mecze", lambda h, a, n=3: "")
    import footstats.ai.rag as rag
    monkeypatch.setattr(rag, "retrieve_relevant_lessons",
                        lambda *a, **kw: [], raising=False)
    return stan


def test_analiza_moze_odroczyc_zapis(rura, zapisy):
    """Potok dzienny zapisuje sam, po weryfikacji — analiza ma tego nie robić."""
    rura["odpowiedz"] = '{"top3": [{"mecz": "Legia vs Lech", "typ": "1", "kurs": 9.9}]}'

    an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False, zapisz_predykcje=False)

    assert zapisy == []


def test_bez_odroczenia_zapis_dziala_jak_dotad(rura, zapisy):
    """`cli_commands` nie ma kroku weryfikacji — dla niego nic się nie zmienia."""
    rura["odpowiedz"] = '{"top3": [{"mecz": "Legia vs Lech", "typ": "1", "kurs": 9.9}]}'

    an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert len(zapisy) == 1


def test_potok_dzienny_odracza_zapis(rura, zapisy, monkeypatch):
    rura["odpowiedz"] = '{"top3": [{"mecz": "Legia vs Lech", "typ": "1", "kurs": 9.9}]}'
    monkeypatch.setattr(an, "ai_groq_dostepny", lambda: True)

    da._analizuj_groq([_mecz()])

    assert zapisy == [], "KROK 3 nie moze juz pisac do bazy"


# ── zapis po weryfikacji ────────────────────────────────────────────────────

def test_zapisuje_kurs_ZWERYFIKOWANY_nie_ten_od_llm(zapisy):
    """A3: w bazie ma wylądować kurs ze źródła, nie liczba wymyślona przez LLM-a."""
    w = _mecz()
    dane = {"top3": [{"mecz": "Legia vs Lech", "typ": "1", "kurs": 52.58}]}

    _przez_potok(dane, [w], _indeks(w))

    assert len(zapisy) == 1
    assert zapisy[0]["odds"] == 1.5


def test_typ_bez_pokrycia_w_kursach_NIE_trafia_do_bazy(zapisy):
    """A3: noga wycięta na weryfikacji nie ma prawa zostawić po sobie wiersza."""
    w = _mecz()
    dane = {"top3": [{"mecz": "Legia vs Lech", "typ": "Over 1.5", "kurs": 1.22}]}

    _przez_potok(dane, [w], _indeks(w))

    assert [z["ai_tip"] for z in zapisy] != ["Over 1.5"]


def test_typ_z_dopiskiem_llm_nigdy_nie_dotrze_do_bazy(zapisy):
    """A2, dokładny wiersz z produkcji 23.08.

    AKTUALIZACJA 27.08 (fix/tip-correct-backfill): `oblicz_tip_correct` umie już
    rozliczyć rozwlekłą rodzinę "N (opis)" (`2 (wygrana gościa)` → jak samo "2").
    To NIE zmienia sedna tego testu — filtr działa niezależnie, na poziomie
    weryfikacji kursów: `_TYP_DO_ODDS_KEY` zna wyłącznie krótkie klucze ("1",
    "2", "over 2.5"...), więc opisowy zapis nie ma tam pokrycia i nadal nie
    wejdzie do bazy, choć teraz — gdyby jednak wszedł — dałby się rozliczyć.
    """
    from footstats.utils.betting import oblicz_tip_correct
    assert oblicz_tip_correct("2 (wygrana gościa)", "1-2") == 1, "zalozenie testu zmienione 27.08"

    w = _mecz()
    dane = {"top3": [{"mecz": "Legia vs Lech", "typ": "2 (wygrana gościa)", "kurs": 6.0}]}

    _przez_potok(dane, [w], _indeks(w))

    assert all("(" not in z["ai_tip"] for z in zapisy)


def test_kazdy_zapisany_typ_da_sie_rozliczyc(zapisy):
    """Bramka ogólna, nie jeden przypadek: cokolwiek wejdzie do bazy, musi mieć
    rozstrzygnięcie przy jakimkolwiek wyniku meczu."""
    from footstats.utils.betting import oblicz_tip_correct

    w = _mecz()
    dane = {"top3": [
        {"mecz": "Legia vs Lech", "typ": "1", "kurs": 1.5},
        {"mecz": "Legia vs Lech", "typ": "2 (wygrana gościa)", "kurs": 6.0},
        {"mecz": "Legia vs Lech", "typ": "Handicap +1 Gość", "kurs": 1.3},
    ]}

    _przez_potok(dane, [w], _indeks(w))

    assert zapisy, "cos musi zostac zapisane"
    for z in zapisy:
        assert oblicz_tip_correct(z["ai_tip"], "1-2") is not None, \
            f"typ {z['ai_tip']!r} nie rozliczy sie nigdy"


def test_licznik_zapisanych_liczy_stan_PO_weryfikacji(zapisy):
    w = _mecz()
    dane = {"top3": [{"mecz": "Legia vs Lech", "typ": "1", "kurs": 52.58},
                     {"mecz": "Legia vs Lech", "typ": "Over 1.5", "kurs": 1.22}]}

    _przez_potok(dane, [w], _indeks(w))

    assert dane["_zapisanych"] == 1


# ── druga szansa dla modelu ─────────────────────────────────────────────────

def test_gdy_weryfikacja_wytnie_wszystko_model_dostaje_druga_szanse(zapisy):
    """Dzień z produkcji 23.08: Groq wytypował trzy rynki bez pokrycia w kursach.

    Do tej pory zostawałyby po nich trzy martwe wiersze. Teraz nie zostaje żaden,
    a typ i tak powstaje — z modelu, na rynku, który źródło wycenia.
    """
    w = _mecz()
    dane = {"top3": [{"mecz": "Legia vs Lech", "typ": "Over 1.5", "kurs": 1.22}]}

    _przez_potok(dane, [w], _indeks(w))

    assert len(zapisy) == 1
    assert zapisy[0]["kupon_type"] == "model"
    assert zapisy[0]["odds"] == 1.5
    assert dane["_top3_z_modelu"] is True


def test_druga_szansa_nie_rusza_gdy_typy_przezyly(zapisy):
    """Model nie dopisuje się do dnia, w którym LLM podał sensowne typy."""
    w = _mecz()
    dane = {"top3": [{"mecz": "Legia vs Lech", "typ": "1", "kurs": 1.5}]}

    _przez_potok(dane, [w], _indeks(w))

    assert [z["kupon_type"] for z in zapisy] == ["top3"]
    assert "_top3_z_modelu" not in dane


def test_typy_z_drugiej_szansy_tez_przechodza_weryfikacje(zapisy):
    """Model nie jest zwolniony z bramki — mecz bez kursu w indeksie odpada."""
    w = _mecz()
    dane = {"top3": [{"mecz": "Legia vs Lech", "typ": "Over 1.5", "kurs": 1.22}]}

    # Indeks bez tego meczu — nie ma czym potwierdzic zadnego kursu.
    _przez_potok(dane, [w], {})

    assert zapisy == []
    assert dane["_zapisanych"] == 0


def test_brak_typow_i_brak_kursow_konczy_sie_cisza(zapisy):
    w = _mecz(odds={})
    dane: dict = {"top3": []}

    _przez_potok(dane, [w], _indeks(w))

    assert zapisy == []
    assert dane["_zapisanych"] == 0
