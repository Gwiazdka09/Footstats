"""Jedno zrodlo prawdy o rynkach, ktore umiemy wycenic i rozliczyc.

Mapa zyla w `daily_agent._TYP_DO_ODDS_KEY` i byla bramka slownikowa weryfikacji:
noga na rynku spoza niej jest kasowana jako halucynacja. Prompt tej listy NIE
znal, wiec model typowal rynki, ktorych nie mamy — a prompt systemowy wrecz mu
je podsuwal ("alternatywy o wyzszym kursie: (...) Handicap -1.5", cala sekcja
o kartkach).

Zmierzone na produkcji 01.09 (`footstats-final-bdqxq`):

    Usunieto 4 halucynowanych nog:
      USUNIETE HALUCYNACJE: Bromley vs Leyton Orient [Handicap +1 Gosc]
        — brak realnego kursu w Bzzoiro (kurs Groq niezweryfikowany)
    Uzgodniono kursy dla 1 zweryfikowanych nog

LLM oddal nogi kuponu, nasza weryfikacja je skasowala, a log raportowal to jako
"warstwa LLM nie oddala struktury kuponu" — jeden komunikat na dwa rozne stany.

Modul jest celowo bez zaleznosci: importuja go i `daily_agent`, i `ai.prompts`,
wiec cokolwiek ciezszego zrobiloby cykl.
"""
from __future__ import annotations

# Slownictwo LLM-a -> klucz w slowniku `odds` zrodla. Klucze po lewej sa
# porownywane po `.strip().lower()`.
TYP_DO_ODDS_KEY: dict[str, str] = {
    "1":           "home",
    "2":           "away",
    "x":           "draw",
    "over 2.5":    "over_2_5",
    "over":        "over_2_5",
    "o2.5":        "over_2_5",
    "under 2.5":   "under_2_5",
    "under":       "under_2_5",
    "btts":        "btts",
    "obie strzelą": "btts",
    # Strona NIE — model potrafil ja wytypowac (`koryguj_tip_ou_btts`), ale bez
    # wpisu w tej mapie noga byla kasowana i podpisywana jako halucynacja Groqa.
    "btts no":     "btts_no",
    "no btts":     "btts_no",
    "btts nie":    "btts_no",
    "nie btts":    "btts_no",
    "ng":          "btts_no",
}

# Typy, ktore graja tylko przy wlaczonym BTTS_TWO_WAY (patrz config).
TYPY_BTTS_NIE = frozenset({"btts no", "no btts", "btts nie", "nie btts", "ng"})


def rynki_dla_promptu(btts_two_way: bool = False) -> list[str]:
    """Kanoniczne nazwy rynkow do wpisania w prompt — wprost z mapy weryfikacji.

    Jedna nazwa na rynek (mapa ma po kilka aliasow na ten sam `odds_key`), w
    kolejnosci stalej, zeby prompt nie zmienial sie od iteracji slownika.
    Strona NIE wchodzi tylko wtedy, gdy flaga ja dopuszcza — inaczej podsuwalibysmy
    modelowi typ, ktory weryfikacja i tak skasuje.
    """
    kanoniczne = [("1", "home"), ("X", "draw"), ("2", "away"),
                  ("Over 2.5", "over_2_5"), ("Under 2.5", "under_2_5"),
                  ("BTTS", "btts")]
    if btts_two_way:
        kanoniczne.append(("BTTS NIE", "btts_no"))
    dostepne = set(TYP_DO_ODDS_KEY.values())
    return [nazwa for nazwa, klucz in kanoniczne if klucz in dostepne]
