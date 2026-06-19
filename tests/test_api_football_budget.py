"""
Testy wpiecia bezpieczny_budget_use w klienta API-Football.

Sprawdza, ze metoda _get lapie BladBudzetu (rzucany przez
bezpieczny_budget_use przy wyczerpanym budzecie) i poprawnie
zwraca wygasle dane z dysku jako fallback.
"""
from unittest.mock import patch

from footstats.scrapers.api_football import APIFootball
from footstats.utils.logging import BladBudzetu


def test_get_zwraca_wygasle_dane_gdy_budzet_wyczerpany() -> None:
    """
    Gdy bezpieczny_budget_use rzuca BladBudzetu (budzet < block_threshold),
    _get powinna przechwycic wyjatek i zwrocic wygasle dane z cache na dysku
    (zamiast propagowac wyjatek lub zwracac None).
    """
    klient = APIFootball(api_key="dummy_key")
    endpoint = "/fixtures"
    params = {"id": 123}
    cache_key = f"af:{endpoint}:{params}"
    wygasle_dane = {"response": ["stare_dane"]}

    with patch(
        "footstats.scrapers.api_football._af_cache_get", return_value=None
    ), patch(
        "footstats.scrapers.api_football.af_budget_status",
        return_value={"krytyczny": False, "ostrzezenie": False,
                      "pozostalo": 50, "limit": 100, "uzyto": 50},
    ), patch(
        "footstats.scrapers.api_football.bezpieczny_budget_use",
        side_effect=BladBudzetu("Dzienny limit API-Football wyczerpany"),
    ), patch(
        "footstats.scrapers.api_football._af_load_disk_cache",
        return_value={cache_key: {"data": wygasle_dane}},
    ):
        wynik = klient._get(endpoint, params=params)

    assert wynik == wygasle_dane
