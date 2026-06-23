"""
aggregator.py — agregacja i porównanie wyników z wielu źródeł ResultsSource.

compare(): grupuje mecze po znormalizowanym kluczu (home, away) ze WSZYSTKICH
źródeł i flaguje rozjazdy (FT/HT) między nimi — sygnał wiarygodności.
consensus_result(): wynik do settlement fallback gdy główne źródło (API-Football)
nie pokrywa meczu — preferuje źródło z danymi HT.
"""
from __future__ import annotations

from footstats.scrapers.sources.af_source import APIFootballSource
from footstats.scrapers.sources.footballdata_source import FootballDataSource
from footstats.scrapers.sources.base import MatchData, ResultsSource
from footstats.utils.normalize import normalize_team_name


def get_sources() -> list[ResultsSource]:
    """
    Rejestr aktywnych źródeł wyników. Dodawanie kolejnego źródła
    (Flashscore/Soccer24/Meczyki...) = dopisanie instancji do tej listy.
    - api-football: szerokie pokrycie (MŚ/ligi), kursy+HT, budżet 100/dzień.
    - football-data.co.uk: CSV top-ligi EU, FT+HT, bez anti-bot — kotwica cross-walidacji.
    """
    return [APIFootballSource(), FootballDataSource()]


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
    Wynik meczu do settlement fallback — z pierwszego dostępnego źródła,
    preferując źródło z danymi półczasu (HT) gdy dostępne.
    None gdy żadne źródło nie ma wyniku FT dla tego meczu.
    """
    dane = fetch_all(date)
    key = match_key(home, away)

    kandydaci: list[MatchData] = []
    for matches in dane.values():
        for m in matches:
            if match_key(m.home, m.away) == key and m.to_result_str() is not None:
                kandydaci.append(m)

    if not kandydaci:
        return None

    # Preferuj kandydata z HT, inaczej pierwszy dostępny.
    z_ht = [m for m in kandydaci if m.ht_home is not None and m.ht_away is not None]
    wybrany = z_ht[0] if z_ht else kandydaci[0]
    return wybrany.to_result_str()
