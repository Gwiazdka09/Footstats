"""Fixtures wspólne dla wszystkich testów FootStats."""
import os
import pandas as pd
import pytest
from datetime import datetime, timedelta

# Hosty baz PRODUKCYJNYCH. Suita nie ma prawa ich dotknąć.
_HOSTY_PROD = ("supabase.co", "supabase.com", "neon.tech")

# Świadome obejście — TYLKO gdy naprawdę chcesz uderzyć w prod (diagnostyka).
_ENV_OBEJSCIE = "FOOTSTATS_ALLOW_PROD_DB"


def _efektywny_database_url() -> str:
    """
    URL, którego REALNIE użyją testy — liczony tak samo jak w aplikacji.

    Nie wystarczy `os.environ`: przy starcie pytesta zmiennej jeszcze nie ma,
    bo wnosi ją dopiero `config.py` swoim `load_dotenv(ENV_FILE)` przy imporcie
    (czyli w fazie zbierania testów, JUŻ PO `pytest_configure`). Ten `load_dotenv`
    jest bez `override`, więc gdy klucz istnieje w środowisku — nawet pusty —
    to on wygrywa. Stąd `DATABASE_URL=""` skutecznie wyłącza bazę, a brak zmiennej
    oznacza, że wejdzie wartość z `.env`.
    """
    if "DATABASE_URL" in os.environ:
        return os.environ["DATABASE_URL"].strip()
    try:
        from pathlib import Path
        from dotenv import dotenv_values
        plik = Path(__file__).resolve().parents[1] / ".env"
        return (dotenv_values(plik).get("DATABASE_URL") or "").strip() if plik.exists() else ""
    except ImportError:
        return ""


def pytest_configure(config):
    """
    Przerywa CAŁĄ sesję, jeśli `DATABASE_URL` wskazuje produkcję.

    Incydent 2026-07-29: `pytest tests/` odpalone bez `DATABASE_URL=""` poszło na
    produkcyjne Supabase (`.env` wskazuje prod od tego dnia). Testy obciążyły
    papierowy bankroll Admin_JG o 2 PLN i dopisały wiersz do `bankroll_history`;
    trzeba to było ręcznie cofać. Reguła „testy nie dotykają proda" istniała
    w dokumentacji, ale NIC jej nie egzekwowało — sam guard sieciowy niżej działa
    wyłącznie gdy DATABASE_URL jest pusty, czyli dokładnie nie w tym przypadku.

    Testy integracyjne uruchamiaj przeciw OSOBNEJ bazie, nie przeciw prod.
    """
    if os.environ.get(_ENV_OBEJSCIE) == "1":
        return
    url = _efektywny_database_url()
    if not url:
        return
    trafiony = next((h for h in _HOSTY_PROD if h in url), None)
    if trafiony:
        raise pytest.UsageError(
            f"STOP: DATABASE_URL wskazuje produkcję ({trafiony}). Testy PISZĄ do bazy "
            f"(zakładają userów, zmieniają salda i statusy kuponów).\n"
            f"  Suita unit:        DATABASE_URL=\"\" pytest tests/\n"
            f"  Testy integracyjne: DATABASE_URL=<osobna baza testowa> pytest tests/\n"
            f"  Świadome obejście:  {_ENV_OBEJSCIE}=1 (tylko diagnostyka, na własną odpowiedzialność)"
        )


@pytest.fixture(autouse=True)
def _patch_auth_db_when_no_database_url(monkeypatch):
    """Patch get_user_by_username to use env vars when DATABASE_URL not set (CI)."""
    if os.environ.get("DATABASE_URL"):
        yield
        return

    import footstats.api.auth as _auth

    pw_hash = os.environ.get("FOOTSTATS_PASSWORD_HASH", "")
    admin_user = os.environ.get("FOOTSTATS_USER", "admin")

    def _fake_get_user(username: str):
        if username == admin_user and pw_hash:
            return {"id": 1, "username": username, "password_hash": pw_hash, "is_admin": True}
        return None

    monkeypatch.setattr(_auth, "get_user_by_username", _fake_get_user)
    yield


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    """Siatka bezpieczeństwa: w trybie unit (brak DATABASE_URL) blokuj REALNE
    połączenia sieciowe (poza localhost). Wymusza mockowanie zewnętrznych usług
    (Neon/Groq/API-Football/FlashScore) i chroni przed przypadkowym zapisem do
    prod / wywołaniem płatnego API. Gdy DATABASE_URL ustawiony → testy
    integracyjne celowo łączą się z bazą, więc guard wyłączony.
    """
    if os.environ.get("DATABASE_URL"):
        yield
        return

    import socket
    _LOCAL = {"127.0.0.1", "localhost", "::1", "0.0.0.0", ""}
    _real_connect = socket.socket.connect
    _real_connect_ex = socket.socket.connect_ex

    def _host(address):
        return address[0] if isinstance(address, (tuple, list)) else address

    def _guard(self, address, *a, **k):
        if _host(address) in _LOCAL:
            return _real_connect(self, address, *a, **k)
        raise RuntimeError(
            f"Test próbował połączyć się z siecią: {address!r}. Zamockuj zewnętrzną "
            "usługę (albo ustaw DATABASE_URL dla testu integracyjnego)."
        )

    def _guard_ex(self, address, *a, **k):
        if _host(address) in _LOCAL:
            return _real_connect_ex(self, address, *a, **k)
        raise RuntimeError(f"Test próbował połączyć się z siecią (connect_ex): {address!r}.")

    monkeypatch.setattr(socket.socket, "connect", _guard)
    monkeypatch.setattr(socket.socket, "connect_ex", _guard_ex)
    yield


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset slowapi in-memory limiter before each test to prevent cross-test contamination."""
    try:
        from footstats.api.main import limiter
        limiter._storage.reset()
    except Exception:
        pass
    yield


@pytest.fixture
def df_mecze_minimal():
    """Minimalne DataFrame meczów do testów (kolumny polskie: gospodarz/goscie/gole_g/gole_a)."""
    today = datetime.now()
    mecze = []
    druzyny = ["Arsenal", "Chelsea", "Liverpool", "Man Utd"]
    for i in range(20):
        g = druzyny[i % 4]
        a = druzyny[(i + 1) % 4]
        if g == a:
            a = druzyny[(i + 2) % 4]
        mecze.append({
            "gospodarz": g,
            "goscie": a,
            "gole_g": (i % 4),
            "gole_a": (i % 3),
            "data": (today - timedelta(days=i * 7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "faza": "REGULAR_SEASON",
        })
    return pd.DataFrame(mecze)


@pytest.fixture
def klucze_env():
    """Przykładowe klucze API (fake)."""
    return {
        "FOOTBALL_API_KEY": "test_fdb_key",
        "APISPORTS_KEY": "test_af_key",
        "BZZOIRO_KEY": "test_bzz_key",
    }
