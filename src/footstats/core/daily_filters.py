"""
daily_filters.py – Pre-filtry kandydatów wydzielone z daily_agent.py.
Uruchamiane przed wywołaniem Groq aby oszczędzać tokeny i poprawiać jakość.
"""

import logging

logger = logging.getLogger(__name__)


def _pre_filtruj_kursy(kandydaci: list[dict]) -> list[dict]:
    """
    Pre-filtr kursów (przed Groq): odrzuca kandydatów bez żadnego kursu w 1.15–15.0.
    Cel: mniej tokenów do Groq, szybsze i tańsze uruchamianie.
    Kandydaci bez pola 'odds' (np. z API-Football) są zawsze zachowywani.
    """
    MIN_KURS, MAX_KURS = 1.15, 15.0
    wynik = []
    for k in kandydaci:
        odds_dict = k.get("odds") or {}
        if not odds_dict:
            wynik.append(k)
            continue
        wartosci = [v for v in odds_dict.values() if isinstance(v, (int, float)) and v > 0]
        if any(MIN_KURS <= v <= MAX_KURS for v in wartosci):
            wynik.append(k)
    return wynik


def _pre_filtruj_tokenow(kandydaci: list[dict]) -> list[dict]:
    """
    Walidacja zabezpieczająca tokeny: odrzuca mecze bez pełnej nazwy drużyny
    lub przypisanej ligi. Zapobiega to marnowaniu zapytań do gorszych lig/braków danych.
    """
    wynik = []
    for k in kandydaci:
        gospodarz = k.get("gospodarz") or k.get("home", "")
        goscie = k.get("goscie") or k.get("away", "")
        liga = k.get("liga", "")

        if (gospodarz and str(gospodarz).strip()
                and goscie and str(goscie).strip()
                and liga and str(liga).strip()):
            wynik.append(k)
    return wynik


def _pre_filtruj_value_bet(kandydaci: list[dict]) -> list[dict]:
    """Odrzuca kandydatów bez edge: EV < 3% lub Kelly < 1% (tylko gdy odds dostępne)."""
    from footstats.core.value_bet import filter_value_bets
    from footstats.core.probability_calibrator import calibrate_candidates
    calibrate_candidates(kandydaci)
    return filter_value_bets(kandydaci)


def _norm_liga(nazwa: str) -> str:
    """Normalizuje nazwę ligi: bez akcentów, bez prefiksu kraju (ENG-/ESP-), lowercase."""
    import unicodedata
    s = unicodedata.normalize("NFKD", nazwa).encode("ascii", "ignore").decode().lower().strip()
    # Usuń prefiks kraju typu "eng-", "esp-", "bra-"
    if len(s) > 4 and s[3] == "-":
        s = s[4:].strip()
    return s


def _pre_filtruj_ligi(kandydaci: list[dict]) -> list[dict]:
    """
    Odrzuca kandydatów z lig bez danych Poissona.
    FAZA 17.4: gdy LIGA_WHITELIST_ENFORCE=True — przepuszcza TYLKO ligi z whitelist
    (porównanie znormalizowane: akcenty, prefiks kraju, wielkość liter).
    Blacklista (friendly/CONCACAF/Afryka) odrzuca zawsze.
    """
    from footstats.config import LIGI_WHITELIST, LIGI_BLACKLIST_KEYWORDS, LIGA_WHITELIST_ENFORCE
    whitelist_norm = {_norm_liga(l) for l in LIGI_WHITELIST}
    wynik = []
    odrzucone_liga = 0
    for k in kandydaci:
        liga = (k.get("liga") or "").strip()
        liga_lower = liga.lower()
        if any(kw.lower() in liga_lower for kw in LIGI_BLACKLIST_KEYWORDS):
            continue
        # Kandydaci bez nazwy ligi (np. API-Football) — zawsze zachowywani.
        if liga and LIGA_WHITELIST_ENFORCE and _norm_liga(liga) not in whitelist_norm:
            odrzucone_liga += 1
            continue
        wynik.append(k)
    if odrzucone_liga:
        logger.info("Whitelist lig: odrzucono %d kandydatów spoza whitelist", odrzucone_liga)
    return wynik
