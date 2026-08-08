"""
aggregator.py — agregacja i porównanie wyników z wielu źródeł ResultsSource.

compare(): grupuje mecze po znormalizowanym kluczu (home, away) ze WSZYSTKICH
źródeł i flaguje rozjazdy (FT/HT) między nimi — sygnał wiarygodności.
consensus_result(): wynik do settlement fallback gdy główne źródło (API-Football)
nie pokrywa meczu — głosowanie źródeł, fail-closed przy remisie.
"""
from __future__ import annotations

import logging

from footstats.scrapers.sources.af_source import APIFootballSource
from footstats.scrapers.sources.footballdata_source import FootballDataSource
from footstats.scrapers.sources.flashscore_source import FlashScoreSource
from footstats.scrapers.sources.thesportsdb_source import TheSportsDBSource
from footstats.scrapers.sources.base import MatchData, ResultsSource
from footstats.utils.normalize import normalize_team_name

logger = logging.getLogger(__name__)


def get_sources() -> list[ResultsSource]:
    """
    Rejestr aktywnych źródeł wyników. Dodawanie kolejnego źródła
    (Soccer24/Meczyki/LiveScore...) = dopisanie instancji do tej listy.
    - api-football: szerokie pokrycie (MŚ/ligi), kursy+HT, budżet 100/dzień.
    - football-data.co.uk: CSV top-ligi EU, FT+HT, bez anti-bot — kotwica cross-walidacji.
    - flashscore: mobi (requests, bez anti-bot — live smoke 98 meczów), FT, szeroka redundancja.
    - thesportsdb: darmowe JSON API (bez anti-bot), FT — pokrycie reprezentacji/
      towarzyskich/turniejów, które ligowe źródła gubią (settlement orphan predykcji).
    """
    return [APIFootballSource(), FootballDataSource(), FlashScoreSource(), TheSportsDBSource()]


def fetch_all(date: str) -> dict[str, list[MatchData]]:
    """
    Pobiera mecze danego dnia z każdego zarejestrowanego źródła.
    Każde źródło jest graceful — błąd jednego nie blokuje innych.
    """
    wynik: dict[str, list[MatchData]] = {}
    for source in get_sources():
        try:
            wynik[source.name] = source.fetch(date)
        except (KeyError, TypeError, ValueError, AttributeError):
            # Dodatkowa siatka bezpieczeństwa — implementacje ResultsSource
            # powinny już być graceful (kontrakt Protocol), ale agregator
            # nie może paść przez błąd jednego źródła.
            wynik[source.name] = []
    return wynik


def match_key(home: str, away: str) -> tuple[str, str]:
    """
    Znormalizowany klucz meczu (home, away) do łączenia tego samego meczu
    między źródłami niezależnie od pisowni drużyn.
    """
    return (normalize_team_name(home), normalize_team_name(away))


def _grupuj_po_meczu(dane: dict[str, list[MatchData]]) -> dict[tuple[str, str], list[MatchData]]:
    """Grupuje MatchData ze wszystkich źródeł po znormalizowanym kluczu meczu."""
    grupy: dict[tuple[str, str], list[MatchData]] = {}
    for matches in dane.values():
        for m in matches:
            key = match_key(m.home, m.away)
            grupy.setdefault(key, []).append(m)
    return grupy


def compare(date: str) -> list[dict]:
    """
    Porównuje mecze danego dnia ze wszystkich źródeł.

    Zwraca listę dictów: {home, away, sources, ft_zgodne, ht_zgodne, rozjazdy}.
    ft_zgodne/ht_zgodne = False gdy źródła podają różne wyniki/HT.
    rozjazdy = lista opisów niezgodności (pusta gdy wszystko się zgadza).
    """
    dane = fetch_all(date)
    grupy = _grupuj_po_meczu(dane)

    wynik: list[dict] = []
    for matches in grupy.values():
        wynik.append(_porownaj_grupe(matches))
    return wynik


def _porownaj_grupe(matches: list[MatchData]) -> dict:
    """Porównuje listę MatchData (ten sam mecz, różne źródła) — wykrywa rozjazdy."""
    pierwszy = matches[0]
    rozjazdy: list[str] = []

    ft_pary = {(m.source, m.ft_home, m.ft_away) for m in matches if m.ft_home is not None}
    ft_wartosci = {(h, a) for (_, h, a) in ft_pary}
    ft_zgodne = len(ft_wartosci) <= 1
    if not ft_zgodne:
        rozjazdy.append(f"FT: {sorted(ft_pary)}")

    ht_pary = {(m.source, m.ht_home, m.ht_away) for m in matches if m.ht_home is not None}
    ht_wartosci = {(h, a) for (_, h, a) in ht_pary}
    ht_zgodne = len(ht_wartosci) <= 1
    if not ht_zgodne:
        rozjazdy.append(f"HT: {sorted(ht_pary)}")

    return {
        "home": pierwszy.home,
        "away": pierwszy.away,
        "sources": matches,
        "ft_zgodne": ft_zgodne,
        "ht_zgodne": ht_zgodne,
        "rozjazdy": rozjazdy,
    }


def consensus_result(home: str, away: str, date: str) -> str | None:
    """
    Wynik meczu do settlement fallback — REALNY konsensus źródeł.

    Wcześniej brany był po prostu pierwszy kandydat z listy, więc gdy dwa
    źródła podawały różne wyniki tego samego meczu, wygrywało to, które akurat
    było wcześniej — i nikt się o rozbieżności nie dowiadywał. Kupon rozliczony
    cudzym wynikiem wyglada identycznie jak rozliczony poprawnie.

    Teraz głosowanie po wyniku FT:
      * większość wygrywa, ale rozjazd i tak trafia do logu;
      * remis głosów → None, czyli kupon zostaje ACTIVE. Fail-closed, ta sama
        zasada co przy dopasowywaniu nazw: lepiej nie rozliczyć i zauważyć,
        niż rozliczyć źle.

    Rozjazd samego HT nie blokuje — wynik FT jest wtedy i tak jednoznaczny.
    """
    dane = fetch_all(date)
    key = match_key(home, away)

    kandydaci: list[MatchData] = [
        m
        for matches in dane.values()
        for m in matches
        if match_key(m.home, m.away) == key and m.to_result_str() is not None
    ]
    if not kandydaci:
        return None

    # Głosy po samym FT — HT to szczegół, nie powód do odrzucenia meczu.
    glosy: dict[tuple[int, int], list[MatchData]] = {}
    for m in kandydaci:
        glosy.setdefault((m.ft_home, m.ft_away), []).append(m)  # type: ignore[arg-type]

    if len(glosy) > 1:
        opis = " vs ".join(
            f"{ft[0]}-{ft[1]} ({', '.join(sorted(x.source for x in grupa))})"
            for ft, grupa in sorted(glosy.items(), key=lambda p: -len(p[1]))
        )
        logger.warning("Rozjazd zrodel dla %s vs %s (%s): %s", home, away, date, opis)

        najliczniejsze = sorted(glosy.values(), key=len, reverse=True)
        if len(najliczniejsze[0]) == len(najliczniejsze[1]):
            logger.warning(
                "Rozjazd nierozstrzygniety dla %s vs %s — nie rozliczam, "
                "kupon zostaje otwarty", home, away,
            )
            return None
        zwyciezcy = najliczniejsze[0]
    else:
        zwyciezcy = next(iter(glosy.values()))

    # W obrębie zwycięskiego wyniku preferuj wariant z półczasem.
    z_ht = [m for m in zwyciezcy if m.ht_home is not None and m.ht_away is not None]
    return (z_ht[0] if z_ht else zwyciezcy[0]).to_result_str()
