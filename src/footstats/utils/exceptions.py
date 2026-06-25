"""
exceptions.py — wspólne wyjątki domenowe FootStats.

Wydzielone z `utils/logging.py` (dekompozycja grab-bag). Re-eksportowane przez
`utils/logging.py` dla kompatybilności (istniejące `from utils.logging import Blad*`
oraz `except logging.BladBudzetu` działają — to ten sam obiekt klasy).
"""


class BladPolaczenia(Exception):
    """Rzucany gdy HTTP request calkowicie sie nie powiodl."""
    pass


class BladBudzetu(Exception):
    """Rzucany gdy dzienny budzet API-Football < AF_BLOCK_THRESHOLD."""
    pass


class BladDanych(Exception):
    """Rzucany gdy dane z API maja nieznany format lub sa puste."""
    pass
