"""Prompt nie moze podsuwac rynkow, ktorych nie umiemy wycenic.

ZMIERZONE NA PRODUKCJI 01.09 (`footstats-final-bdqxq`, obraz z naprawa kursow):

    Usunieto 4 halucynowanych nog:
      USUNIETE HALUCYNACJE: Bromley vs Leyton Orient [Handicap +1 Gosc]
        — brak realnego kursu w Bzzoiro (kurs Groq niezweryfikowany)
    Uzgodniono kursy dla 1 zweryfikowanych nog
    Faza final: 1 typow powstalo (...) kupon NIE zostal zapisany

Model oddal nogi kuponu. Skasowala je NASZA weryfikacja, bo `Handicap +1` nie ma
wpisu w mapie `TYP_DO_ODDS_KEY` — a wiec nie ma kursu i nie da sie go rozliczyc.
Skad model wzial handicap: z promptu systemowego, ktory sam go proponuje
("alternatywy o wyzszym kursie (1.65-2.20): Over 2.5, BTTS, lub Handicap -1.5").
Ta sama sekcja zachwalala rynek kartek i BetBuilder — rowniez bez wyceny.

Lista dozwolonych rynkow jest GENEROWANA z mapy weryfikacji, nie przepisana.
Przepisana rozjechalaby sie przy pierwszej zmianie mapy — a rozjazd dwoch kopii
tej samej reguly to bug, ktory w tym promptcie wystapil juz trzykrotnie.
"""
from __future__ import annotations

import pytest

from footstats.ai.prompts import SYSTEM_TYPER_BAZA, build_pewniaczki_prompt
from footstats.core.rynki import TYP_DO_ODDS_KEY, rynki_dla_promptu


def _prompt(n_mecze: int = 3) -> str:
    return build_pewniaczki_prompt(
        n_mecze=n_mecze, sygnaly="", kalibracja_str="", feedback_str="",
        mecze_opisy_text="<MECZE>", cel_kuponow_text="<CEL>",
    )


@pytest.mark.parametrize("rynek", rynki_dla_promptu())
def test_prompt_wymienia_kazdy_dozwolony_rynek(rynek):
    assert rynek in _prompt(), f"model nie wie, ze wolno mu typowac {rynek!r}"


@pytest.mark.parametrize("zakazany", ["handicap", "kartk", "corner", "rzut rozny"])
def test_prompt_uzytkownika_nie_podsuwa_rynku_bez_wyceny(zakazany):
    assert zakazany.lower() not in _prompt().lower()


@pytest.mark.parametrize("zakazany", ["handicap", "kartk", "betbuilder", "bet builder"])
def test_prompt_SYSTEMOWY_tez_nie_podsuwa(zakazany):
    """Systemowy idzie przy KAZDYM wywolaniu — to on zaproponowal handicap."""
    assert zakazany.lower() not in SYSTEM_TYPER_BAZA.lower(), (
        f"prompt systemowy proponuje {zakazany!r}, rynek spoza TYP_DO_ODDS_KEY — "
        f"noga na nim zostanie skasowana przez weryfikacje jako halucynacja"
    )


def test_lista_jest_generowana_a_nie_przepisana(monkeypatch):
    """Kontrola anty-rozjazdowa: nowy rynek w mapie ma sam trafic do promptu.

    Bez tego testu lista w promptcie moglaby byc zwyklym literalem — zielonym
    dzis i nieaktualnym przy pierwszej zmianie mapy weryfikacji.
    """
    # Patchujemy nazwe W MODULE, KTORY JEJ UZYWA. `prompts.py` robi
    # `from ... import rynki_dla_promptu`, wiec trzyma wlasna referencje —
    # podmiana w module zrodlowym nie doszlaby do niego i test przechodzilby
    # nie mierzac niczego.
    monkeypatch.setattr("footstats.ai.prompts.rynki_dla_promptu",
                        lambda btts_two_way=False: ["1", "SZTUCZNY_RYNEK"])

    assert "SZTUCZNY_RYNEK" in _prompt(), (
        "lista rynkow w promptcie nie pochodzi z `rynki_dla_promptu` — jest "
        "przepisana i rozjedzie sie z mapa weryfikacji"
    )


def test_mapa_weryfikacji_dalej_zna_te_rynki():
    """Kontrola negatywna: prompt i weryfikacja czytaja TEN SAM slownik."""
    for rynek in rynki_dla_promptu():
        assert rynek.lower() in TYP_DO_ODDS_KEY, f"{rynek} nie przejdzie weryfikacji"
