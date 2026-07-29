"""
fixtures_fallback.py — awaryjne źródło nadchodzących meczów (API-Football).

Po co: Bzzoiro był single point of failure dziennego draftu — brak klucza albo
503 i `cloud_draft.generuj_system_draft` zwracało `{"ok": False}`, więc cały dzień
przepadał (zero predykcji, zero settled → pętla uczenia stoi).

Ten klient jest duck-type'em `BzzoiroClient` w zakresie, którego używa
`quick_picks.szybkie_pewniaczki_2dni`: `_valid`, `waliduj()`, `predykcje_tygodnia()`.
Dzięki temu wpina się bez dotykania pętli predykcji.

Czego NIE robi: nie ma ramienia ML ani kursów — zwracane mecze są bez `pred_ml`,
więc prawdopodobieństwa musi policzyć Poisson (`quick_picks` ma ścieżkę Poisson-only).
Bez historii (parquet) fallback nie wyprodukuje typów — to świadome: lepiej zero
kuponów niż kupony zgadywane.

Koszt budżetu API-Football: 1 request na dzień horyzontu (domyślnie 2), cache'owany
przez mechanizm `APIFootball._get`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from footstats.config import ENV_APISPORTS, _czytaj_wszystkie_klucze
from footstats.scrapers.api_football import APIFootball
from footstats.utils.helpers import _s

log = logging.getLogger(__name__)

# Statusy API-Football oznaczające mecz jeszcze nierozegrany.
_STATUSY_ZAPLANOWANE = ("NS", "TBD")

# Strefa czasowa zapytania — `quick_picks` porównuje godzinę meczu z `datetime.now()`,
# więc AF musi zwrócić czas lokalny, nie UTC.
_TIMEZONE = "Europe/Warsaw"


class FixturesFallbackClient:
    """Nadchodzące mecze z API-Football w schemacie oczekiwanym przez quick_picks."""

    name: str = "api-football-fallback"

    def __init__(
        self,
        klient_af: APIFootball | None = None,
        klucz_af: str | None = None,
        dni: int = 2,
    ) -> None:
        if klient_af is None:
            klucz = klucz_af if klucz_af is not None else (
                _czytaj_wszystkie_klucze().get(ENV_APISPORTS) or ""
            )
            klient_af = APIFootball(klucz) if klucz else None
        self._klient = klient_af
        self._dni = max(1, dni)
        self._valid = klient_af is not None

    def waliduj(self) -> tuple[bool, str]:
        """Czy fallback ma czym pobierać dane. Nie bije po sieci — sam brak klucza wystarczy."""
        if self._klient is None:
            self._valid = False
            return False, f"brak klucza {ENV_APISPORTS} — fallback nieaktywny"
        self._valid = True
        return True, "API-Football fallback gotowy"

    def predykcje_tygodnia(self, liga_kod: str | None = None) -> list[dict]:
        """
        Mecze na najbliższe `dni` dni w schemacie Bzzoiro (bez `pred_ml`).

        Graceful: brak klienta / błąd sieci / śmieciowa odpowiedź → pusta lista.
        `liga_kod` przyjmowany dla zgodności interfejsu — AF filtruje po dacie.
        """
        if self._klient is None:
            return []

        mecze: list[dict] = []
        dzis = datetime.now()
        for offset in range(self._dni):
            data = (dzis + timedelta(days=offset)).strftime("%Y-%m-%d")
            mecze.extend(self._mecze_dnia(data))
        return mecze

    def _mecze_dnia(self, data: str) -> list[dict]:
        """Pojedyncze zapytanie /fixtures. Błąd jednego dnia nie psuje pozostałych."""
        klient = self._klient
        if klient is None:
            return []
        try:
            dane = klient._get("/fixtures", {"date": data, "timezone": _TIMEZONE})
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            log.warning("fallback fixtures %s nieosiągalne: %s", data, e)
            return []

        if not dane:
            return []

        wynik: list[dict] = []
        for fixture in dane.get("response", []) or []:
            mecz = self._mapuj(fixture)
            if mecz is not None:
                wynik.append(mecz)
        return wynik

    def _mapuj(self, fixture: dict) -> dict | None:
        """Fixture AF → dict quick_picks. None gdy brak drużyn lub mecz już się zaczął."""
        try:
            teams = fixture.get("teams") or {}
            # UWAGA: `_s` podmienia pustą wartość na "-", więc walidujemy PRZED nim,
            # inaczej mecz bez nazwy drużyny przeszedłby jako "- vs B".
            gosp = str((teams.get("home") or {}).get("name") or "").strip()
            gosc = str((teams.get("away") or {}).get("name") or "").strip()
            if not gosp or not gosc:
                return None

            info = fixture.get("fixture") or {}
            status_short = ((info.get("status") or {}).get("short") or "").strip()
            if status_short not in _STATUSY_ZAPLANOWANE:
                return None

            data_iso = str(info.get("date") or "")
            if "T" not in data_iso:
                return None
            data, reszta = data_iso.split("T", 1)
            godzina = reszta[:5]

            return {
                "gosp": gosp,
                "gosc": gosc,
                "liga": _s((fixture.get("league") or {}).get("name", "")) or "?",
                "data": data,
                "godzina": godzina,
                "status": "notstarted",
                # Świadomie bez `pred_ml` i `odds` — fallback nie ma modelu ani kursów.
            }
        except (AttributeError, TypeError, ValueError):
            return None
