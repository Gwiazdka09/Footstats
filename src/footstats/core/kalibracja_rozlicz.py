"""kalibracja_rozlicz.py — dopisuje wyniki do dziennika kalibracji.

PO CO OSOBNO OD ROZLICZANIA KUPONÓW:
  * kupony ścigają się z czasem (bankroll, wypłaty) i mają wąskie okno 2-3 dni;
  * dziennik nie ściga się z niczym — może spokojnie nadrabiać zaległości.

Predykcja #8 (Athletico vs Internacional) leżała z gotowym wynikiem "2-0" od
26.07 i nigdy się nie rozliczyła właśnie dlatego, że wypadła z okna kuponów
i nikt jej już nie odwiedził. Dziennik nie może powtórzyć tego błędu.

Źródła wyników są WSPÓŁDZIELONE z rozliczaniem kuponów, więc dziedziczą całą
ochronę przed dopasowaniem cudzego meczu (`min` zamiast średniej, znaczniki
rezerw) — patrz `tests/test_dopasowanie_nazw_audyt.py`.
"""
from __future__ import annotations

import logging

import psycopg2

from footstats.core.kalibracja_log import pobierz_nierozliczone, zapisz_wynik

log = logging.getLogger(__name__)

# Okno szersze niż kuponowe (2-3 dni) — patrz docstring modułu.
_DNI_WSTECZ = 14

# Awarie POJEDYNCZEGO wpisu, po których przebieg ma lecieć dalej: padnięte
# źródło wyników, śmieć w danych, chwilowy błąd bazy. Następnym razem spróbujemy
# ponownie — wpis zostaje w kolejce, bo nie zapisujemy mu trafności.
_AWARIE_WPISU = (psycopg2.Error, RuntimeError, OSError, ValueError, TypeError, KeyError)


def _znajdz_wynik_meczu(home: str, away: str, data: str) -> str | None:
    """Szuka wyniku meczu w źródłach współdzielonych z rozliczaniem kuponów.

    Kolejność: football-data.org (darmowy, duże ligi) → FlashScore (scraping,
    pokrywa ligi spoza fdb: POL/AUT/BEL/SCO). API-Football świadomie pominięte —
    darmowy plan nie ma dostępu do potrzebnych endpointów (stan 2026-08-05).
    """
    try:
        from footstats.scrapers.flashscore_results import get_match_result
        wynik = get_match_result(home, away, data)
        if wynik:
            return wynik
    except _AWARIE_WPISU as e:
        log.debug("kalibracja: FlashScore nie dal wyniku (%s vs %s): %s", home, away, e)
    return None


def rozlicz_dziennik(dni_wstecz: int = _DNI_WSTECZ, dry_run: bool = False) -> dict:
    """Dopisuje wyniki do ocen bez `tip_correct`.

    `dry_run` pokazuje, co BY się stało, bez zapisu — ta sama zasada co przy
    rozliczaniu kuponów.

    Rozróżnia dwie sytuacje, bo znaczą co innego:
      * `bez_wyniku` — mecz jeszcze nierozegrany albo źródło go nie zna (normalne);
      * `bledy` — źródło padło (wymaga reakcji).
    """
    wpisy = pobierz_nierozliczone(dni_wstecz=dni_wstecz)
    raport = {"sprawdzone": len(wpisy), "rozliczone": 0, "bez_wyniku": 0, "bledy": 0}

    for w in wpisy:
        try:
            wynik = _znajdz_wynik_meczu(
                w["team_home"], w["team_away"], str(w["match_date"])[:10]
            )
        except _AWARIE_WPISU as e:
            log.warning("kalibracja: blad zrodla dla #%s: %s", w.get("id"), e)
            raport["bledy"] += 1
            continue

        if not wynik:
            raport["bez_wyniku"] += 1
            continue

        if dry_run:
            raport["rozliczone"] += 1
            continue

        try:
            if zapisz_wynik(w["id"], wynik, w["model_tip"]):
                raport["rozliczone"] += 1
            else:
                # Wynik jest, ale typ nierozliczalny — wpis zostaje w kolejce,
                # bo "nie wiemy" to nie to samo co "model sie pomylil".
                raport["bez_wyniku"] += 1
        except _AWARIE_WPISU as e:
            log.warning("kalibracja: blad zapisu dla #%s: %s", w.get("id"), e)
            raport["bledy"] += 1

    log.info("kalibracja_rozlicz: %s", raport)
    return raport
