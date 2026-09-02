"""Fixtures wspólne dla wszystkich testów FootStats."""
import atexit
import os
import shutil
import tempfile
import pandas as pd
import pytest
from datetime import datetime, timedelta
from pathlib import Path

# ── Katalog cache WŁASNY DLA TEGO PROCESU ────────────────────────────────────
#
# Do 28.08 każdy moduł liczył swój katalog cache sam, przy imporcie, jako stałą
# modułową (`Path("cache/kursy")` i 17 podobnych). Wartość powstawała, zanim
# cokolwiek zdążyło ją nadpisać, więc DWA RÓWNOLEGŁE PRZEBIEGI pytest — np. dwa
# agenty naraz — pisały i kasowały te same pliki. Nie jest to teoria: dokładnie
# ten objaw złapała 26.08 fikstura `clean_checkpoint_dir` w test_checkpoint.py,
# tyle że `CHECKPOINT_DIR` dało się przekierować, bo czyta env przy wywołaniu.
# Tutaj domykamy pozostałe 17 katalogów tym samym sposobem.
#
# MUSI stać PRZED pierwszym importem `footstats.*` — stałe modułowe czytają tę
# zmienną w momencie importu. Pilnuje tego `tests/test_izolacja_cache.py`.
_KORZEN_CACHE = os.environ.setdefault(
    "FOOTSTATS_CACHE_ROOT",
    str(Path(tempfile.gettempdir()) / f"footstats-cache-pid{os.getpid()}"),
)
atexit.register(shutil.rmtree, _KORZEN_CACHE, ignore_errors=True)

# ── Testowe dane logowania — USTAWIANE TU, NIE W POSZCZEGÓLNYCH PLIKACH ───────
#
# Dlaczego centralnie: dotąd każdy plik testowy robił u siebie
# `os.environ.setdefault("FOOTSTATS_PASSWORD_HASH", bcrypt(...))` PRZED importem
# `footstats.api.main`. Wystarczyło, że pierwszy zaimportowany plik tego NIE robił
# (test_analyses_endpoint, test_api_integration_cache) — wtedy `config.py` swoim
# `load_dotenv(.env)` wypełniał zmienną PRAWDZIWYM hashem, a późniejsze
# `setdefault` w test_auth/test_api_routes stawały się no-opem. Efekt: logowanie
# hasłem "testpass" dostawało 401 i 12 testów padało WYŁĄCZNIE w pełnej suicie,
# przechodząc w izolacji.
#
# conftest.py jest importowany przed modułami testowymi, więc `setdefault` tutaj
# wygrywa z `.env` (moduł ładuje je bez `override`), a jednocześnie NIE nadpisuje
# wartości podanych świadomie w środowisku.
os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")
os.environ.setdefault("FOOTSTATS_USER", "admin")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")
if "FOOTSTATS_PASSWORD_HASH" not in os.environ:
    import bcrypt as _bcrypt

    os.environ["FOOTSTATS_PASSWORD_HASH"] = _bcrypt.hashpw(
        b"testpass", _bcrypt.gensalt()
    ).decode()

# Znane hosty baz PRODUKCYJNYCH — służą już TYLKO do ostrzejszego komunikatu,
# nie do decyzji. Decyzję podejmuje `_powod_odmowy` na zasadzie ALLOWLISTY.
_HOSTY_PROD = ("supabase.co", "supabase.com", "neon.tech")

# Hosty, na których baza z definicji nie jest produkcją.
_HOSTY_LOKALNE = ("localhost", "127.0.0.1", "::1", "host.docker.internal", "db", "postgres")

# Znacznik, po którym poznajemy bazę przeznaczoną do testów.
_ZNACZNIK_TESTOWY = "test"


def _powod_odmowy(url: str) -> str | None:
    """Powód, dla którego suita NIE MOŻE użyć tej bazy, albo None gdy wolno.

    ALLOWLISTA, nie denylista — i to jest cała zmiana względem wersji z 29.07.
    Tamta wypisywała znane hosty produkcyjne i przepuszczała wszystko inne.
    Taka lista gnije w jedną stronę: przeprowadzka Neon → Supabase (18.07)
    zostawiłaby guard, który dalej wygląda na działający i nie chroni już przed
    niczym. Ten sam kształt błędu co reszta cichych degradacji w tym projekcie.

    Wolno: brak URL (tryb unit), host lokalny, baza z „test" w nazwie.
    Wszystko inne wymaga świadomej decyzji przez `FOOTSTATS_ALLOW_PROD_DB=1`.

    Komunikat NIE zawiera loginu ani hasła — wyłącznie host i nazwę bazy.
    """
    if not url:
        return None

    from urllib.parse import urlsplit

    try:
        czesci = urlsplit(url)
        host = (czesci.hostname or "").lower()
        baza = (czesci.path or "").lstrip("/").lower()
    except ValueError:
        return "nie da sie sparsowac DATABASE_URL"

    if host in _HOSTY_LOKALNE:
        return None
    if _ZNACZNIK_TESTOWY in baza or _ZNACZNIK_TESTOWY in host:
        return None

    znany_prod = next((h for h in _HOSTY_PROD if h in host), None)
    if znany_prod:
        return f"wskazuje ZNANA produkcje ({znany_prod})"
    return (f"wskazuje baze '{baza or '?'}' na hoscie '{host or '?'}', ktora nie jest"
            f" ani lokalna, ani oznaczona jako testowa")

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

    28.08: warunek odwrócony z denylisty na ALLOWLISTĘ — patrz `_powod_odmowy`.
    Lista znanych hostów prod przetrwała przeprowadzkę Neon → Supabase tylko
    dlatego, że ktoś ją dopisał ręcznie; następnej mogłaby nie przetrwać.
    """
    if os.environ.get(_ENV_OBEJSCIE) == "1":
        return
    powod = _powod_odmowy(_efektywny_database_url())
    if powod:
        raise pytest.UsageError(
            f"STOP: DATABASE_URL {powod}. Testy PISZĄ do bazy "
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
def reset_bramki_apisports():
    """Zeruje zatrzask `core.apisports_gate` przed każdym testem.

    Zatrzask jest globalny NA PROCES i celowo nie ma resetu w locie — produkcyjny
    job startuje czysty, a po blokadzie konta ma milczeć do końca przebiegu.
    pytest to jednak JEDEN proces grający tysiące takich przebiegów: bez tego
    resetu pierwszy test podający odpowiedź „account suspended" zamykał bramkę
    dla całej reszty suity. Objaw był mylący — 81 testów czerwonych w suicie,
    wszystkie zielone uruchamiane osobno.
    """
    from footstats.core import apisports_gate

    apisports_gate._ZAWIESZONE = False
    yield
    apisports_gate._ZAWIESZONE = False


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
