"""
safe_http.py — bezpieczne HTTP + wielokrokowe pobieranie (logowanie/retry).

Wydzielone z `utils/logging.py` (dekompozycja grab-bag):
- BezpiecznyHTTP: GET z retry/backoff i pełnym logowaniem statusów.
- BezpiecznePobieranie: context manager wielu źródeł ligi (graceful per-krok).

Re-eksportowane przez `utils/logging.py` dla kompatybilności importów.
Logger: ten sam singleton "footstats" (`logging.getLogger`) — bez importu z
`utils.logging`, żeby uniknąć cyklu importów.
"""
import logging as _logging
import time
from typing import Any, Callable

from footstats.utils.exceptions import BladPolaczenia, BladBudzetu

logger = _logging.getLogger("footstats")


# ── HTTP GET – z logowaniem i retry ────────────────────────────────

class BezpiecznyHTTP:
    """
    Context manager / helper do bezpiecznych zapytan HTTP.

    Uzycie zamiast nagiega requests.get():
        wynik = BezpiecznyHTTP.get(url, params, headers, retries=2)
    """

    @staticmethod
    def get(url: str,
            params: dict = None,
            headers: dict = None,
            timeout: int = 15,
            retries: int = 2) -> dict | None:
        """
        Bezpieczne GET z retry i pelnym logowaniem.

        Returns:
            Slownik JSON lub None przy bledzie.

        Raises:
            BladPolaczenia – gdy wszystkie retry sie nie powiodly
        """
        import requests

        for prob in range(retries + 1):
            try:
                logger.debug("HTTP GET [proba %d/%d]: %s | params=%s",
                             prob + 1, retries + 1, url, params)

                r = requests.get(url, headers=headers, params=params, timeout=timeout)
                logger.debug("HTTP %d <- %s (%.2fs)",
                             r.status_code, url, r.elapsed.total_seconds())

                if r.status_code == 200:
                    dane = r.json()
                    logger.info("OK: %s | %d bajtow", url, len(r.content))
                    return dane

                elif r.status_code == 429:
                    czekaj = 62
                    logger.warning("429 Rate Limit: %s | czekam %ds...", url, czekaj)
                    time.sleep(czekaj)
                    continue  # retry po oczekiwaniu

                elif r.status_code == 401:
                    logger.error("401 Unauthorized: %s | sprawdz klucz API", url)
                    return None

                elif r.status_code == 403:
                    logger.error("403 Forbidden: %s | zly klucz lub plan", url)
                    return None

                elif r.status_code == 404:
                    logger.warning("404 Not Found: %s", url)
                    return None

                elif r.status_code >= 500:
                    logger.error("Blad serwera %d: %s", r.status_code, url)
                    if prob < retries:
                        time.sleep(5 * (prob + 1))
                        continue
                    return None

                else:
                    logger.warning("Nieoczekiwany HTTP %d: %s", r.status_code, url)
                    return None

            except requests.exceptions.ConnectionError as e:
                logger.error("Brak polaczenia z internetem (proba %d/%d): %s",
                             prob + 1, retries + 1, e)
                if prob < retries:
                    time.sleep(3)
                    continue
                raise BladPolaczenia(f"Brak polaczenia: {url}") from e

            except requests.exceptions.Timeout:
                logger.warning("Timeout %ds (proba %d/%d): %s",
                               timeout, prob + 1, retries + 1, url)
                if prob < retries:
                    continue
                return None

            except requests.exceptions.JSONDecodeError as e:
                logger.error("Blad parsowania JSON: %s | %s", url, e)
                return None

            except (requests.exceptions.RequestException, OSError) as e:
                logger.critical("Nieoczekiwany blad HTTP: %s | %s",
                                url, e, exc_info=True)
                return None

        return None


# ── Pobieranie danych ligi – z obsługa błędów ─────────────────────

class BezpiecznePobieranie:
    """
    Context manager dla wielokrokowego pobierania danych ligi.
    Zapewnia ze nawet przy bledzie jednego zrodla program nie crashuje.

    Uzycie:
        with BezpiecznePobieranie("Serie A") as bp:
            tabela = bp.wykonaj(api.tabela, "SA", fallback=None)
            wyniki = bp.wykonaj(api.wyniki, "SA", 100, fallback=pd.DataFrame())
        if bp.ma_bledy:
            print(f"Ostrzezenia: {bp.bledy}")
    """

    def __init__(self, nazwa_ligi: str):
        self.nazwa  = nazwa_ligi
        self.bledy  = []
        self._start = time.perf_counter()

    def __enter__(self):
        logger.info("Rozpoczynam pobieranie danych: %s", self.nazwa)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        dt = time.perf_counter() - self._start
        if exc_type is not None:
            logger.error("Krytyczny blad pobierania [%s] po %.1fs: %s",
                         self.nazwa, dt, exc_val, exc_info=True)
            return False  # nie tlumimy wyjatku
        if self.bledy:
            logger.warning("Pobieranie [%s] zakonczone z %d ostrzezeniami (%.1fs): %s",
                           self.nazwa, len(self.bledy), dt, "; ".join(self.bledy[:3]))
        else:
            logger.info("Pobieranie [%s] zakonczone pomyslnie (%.1fs)", self.nazwa, dt)
        return False

    def wykonaj(self, func: Callable, *args, fallback=None, opis: str = "") -> Any:
        """
        Wykonuje func(*args) bezpiecznie.
        Przy bledzie zapisuje go do self.bledy i zwraca fallback.
        """
        nazwa_f = opis or getattr(func, "__name__", str(func))
        try:
            wynik = func(*args)
            if wynik is None:
                self.bledy.append(f"{nazwa_f}: zwrocilo None")
                logger.warning("[%s] %s zwrocilo None", self.nazwa, nazwa_f)
                return fallback
            return wynik
        except BladPolaczenia as e:
            self.bledy.append(f"{nazwa_f}: brak polaczenia")
            logger.error("[%s] Brak polaczenia przy %s: %s", self.nazwa, nazwa_f, e)
            return fallback
        except BladBudzetu as e:
            self.bledy.append(f"{nazwa_f}: wyczerpany budzet AF")
            logger.critical("[%s] Wyczerpany budzet: %s", self.nazwa, e)
            raise  # budzet = krytyczny, nie tlumimy
        except Exception as e:  # noqa: broad-except — API client fallback for arbitrary errors
            self.bledy.append(f"{nazwa_f}: {type(e).__name__}")
            logger.error("[%s] Blad %s: %s", self.nazwa, nazwa_f, e, exc_info=True)
            return fallback

    @property
    def ma_bledy(self) -> bool:
        return bool(self.bledy)
