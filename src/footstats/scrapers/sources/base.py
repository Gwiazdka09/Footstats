"""
base.py — wspólny interfejs dla multi-source scraperów wyników/kursów.

MatchData: znormalizowany DTO meczu z jednego źródła (FT/HT/kursy).
ResultsSource: Protocol implementowany przez każdy adapter źródła
(API-Football, Flashscore, Soccer24, Meczyki, ...) — zawsze graceful,
nigdy nie rzuca wyjątku (błąd → pusta lista).
"""
from __future__ import annotations

import typing
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MatchData:
    """
    Znormalizowane dane meczu z jednego źródła.

    odds: słownik kursów (klucze: home/draw/away/over_2_5/under_2_5/btts
    -> float|None), domyślnie pusty — tylko realnie znalezione rynki.
    """
    source: str
    home: str
    away: str
    date: str  # YYYY-MM-DD
    status: str  # "finished" / "scheduled" / "unknown"
    ft_home: int | None
    ft_away: int | None
    ht_home: int | None
    ht_away: int | None
    odds: dict[str, float | None] = field(default_factory=dict)

    def to_result_str(self) -> str | None:
        """
        Format wyniku zgodny z `oblicz_tip_correct` (utils/betting.py):
        "HG-AG" + opcjonalny sufiks ";HT:hh-ha" gdy dane półczasu dostępne.
        None gdy mecz nie ma jeszcze wyniku FT.
        """
        if self.ft_home is None or self.ft_away is None:
            return None
        wynik = f"{self.ft_home}-{self.ft_away}"
        if self.ht_home is not None and self.ht_away is not None:
            wynik += f";HT:{self.ht_home}-{self.ht_away}"
        return wynik


@typing.runtime_checkable
class ResultsSource(typing.Protocol):
    """
    Wspólny interfejs adaptera źródła wyników/kursów.

    Implementacje muszą być graceful: błąd sieci/parsowania → [] (nigdy
    nie rzucają wyjątku), żeby agregator mógł kontynuować z innymi źródłami.
    """
    name: str

    def fetch(self, date: str) -> list[MatchData]:
        """Zwraca mecze danego dnia (YYYY-MM-DD) z tego źródła."""
        ...
