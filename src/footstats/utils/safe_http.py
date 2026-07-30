"""
safe_http.py — bezpieczne HTTP + wielokrokowe pobieranie (logowanie/retry).

Wydzielone z `utils/logging.py` (dekompozycja grab-bag):
- BezpiecznyHTTP: GET z retry/backoff i pełnym logowaniem statusów.

Re-eksportowane przez `utils/logging.py` dla kompatybilności importów.
Logger: ten sam singleton "footstats" (`logging.getLogger`) — bez importu z
`utils.logging`, żeby uniknąć cyklu importów.
"""
import logging as _logging
import time

from footstats.utils.exceptions import BladPolaczenia

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

# Klasa BezpiecznePobieranie usunieta 2026-07-30 — nigdy nie instancjonowana.
# Byla re-eksportowana z utils/logging.py (kompatybilnosc wstecz) i to jedyne
# odwolanie utrzymywalo ja przy zyciu w statystykach. Jej metoda wykonaj()
# lapala `except Exception` i zwracala fallback — usuniecie kasuje jedno
# z ostatnich szerokich lapan wyjatkow w projekcie.
