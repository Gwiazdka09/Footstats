"""
daily_filters.py – Pre-filtry kandydatów wydzielone z daily_agent.py.
Uruchamiane przed wywołaniem Groq aby oszczędzać tokeny i poprawiać jakość.
"""

import logging
import os

logger = logging.getLogger(__name__)


def _gating_lig_on() -> bool:
    """M1 lever #2 — czy gating słabych lig włączony (env LEAGUE_GATING, default OFF)."""
    return os.getenv("LEAGUE_GATING", "0").strip().lower() in ("1", "true", "yes")


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
    from footstats.config import (
        LIGI_WHITELIST, LIGI_BLACKLIST_KEYWORDS, LIGA_WHITELIST_ENFORCE, LIGI_SLABE,
    )
    whitelist_norm = {_norm_liga(l) for l in LIGI_WHITELIST}
    gating = _gating_lig_on()
    slabe_norm = {_norm_liga(l) for l in LIGI_SLABE} if gating else set()
    wynik = []
    odrzucone_liga = 0
    odrzucone_slabe = 0
    nazwy_odrzuconych: dict[str, int] = {}
    for k in kandydaci:
        liga = (k.get("liga") or "").strip()
        liga_lower = liga.lower()
        if any(kw.lower() in liga_lower for kw in LIGI_BLACKLIST_KEYWORDS):
            # Ta gałąź milczała całkowicie — bez licznika i bez nazwy. Przebieg
            # `footstats-final-5dpcn` (13.08): `kandydaci=5, po filtrach=0`, a w
            # logu ANI JEDNEJ ligi, bo komplet wyciął tu blacklist keywordów,
            # nie whitelist niżej. Dokładnie ta cicha awaria, przed którą miała
            # chronić diagnostyka whitelisty.
            odrzucone_liga += 1
            nazwy_odrzuconych[liga or "(bez nazwy)"] = (
                nazwy_odrzuconych.get(liga or "(bez nazwy)", 0) + 1
            )
            continue
        # Kandydaci bez nazwy ligi (np. API-Football) — zawsze zachowywani.
        if liga and LIGA_WHITELIST_ENFORCE and _norm_liga(liga) not in whitelist_norm:
            odrzucone_liga += 1
            nazwy_odrzuconych[liga] = nazwy_odrzuconych.get(liga, 0) + 1
            continue
        # M1 lever #2: gating słabych lig (<50% offline) — tylko gdy LEAGUE_GATING=1.
        if liga and gating and _norm_liga(liga) in slabe_norm:
            odrzucone_slabe += 1
            continue
        wynik.append(k)
    if odrzucone_liga:
        # NAZWY, nie sama liczba. 10-12.08.2026 job konczyl sie sukcesem przez trzy
        # dni z rzedu, produkujac ZERO predykcji: whitelist wycinala komplet 44
        # kandydatow, bo w polowie sierpnia kalendarz wypelniaja puchary europejskie
        # (Conference/Europa/Champions League, Copa Libertadores), ktorych na liscie
        # nie ma. Log podawal tylko liczbe, wiec diagnoza wymagala grzebania w bazie.
        szczyt = sorted(nazwy_odrzuconych.items(), key=lambda kv: -kv[1])[:5]
        opis = ", ".join(f"{liga} ({ile})" for liga, ile in szczyt)
        reszta = len(nazwy_odrzuconych) - len(szczyt)
        if reszta > 0:
            opis += f" i {reszta} innych"
        if kandydaci and not wynik:
            # Filtr wyciol WSZYSTKO — to zdarzenie warte krzyku, nie notatki.
            # Cisza na INFO wyglada dokladnie tak samo jak "nie bylo meczow".
            logger.warning(
                "Filtr lig wyciął WSZYSTKICH %d kandydatów — zero predykcji. Ligi: %s",
                odrzucone_liga, opis,
            )
        else:
            logger.info("Filtr lig (blacklist + whitelist): odrzucono %d kandydatów (%s)",
                        odrzucone_liga, opis)
    if odrzucone_slabe:
        logger.info("Gating słabych lig: odrzucono %d kandydatów (POL/ESP/FRA <50%%)", odrzucone_slabe)
    return wynik
