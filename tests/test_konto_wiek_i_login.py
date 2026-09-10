"""Rejestracja z miesiącem urodzenia, zgoda na ranking, prośba o wiek dla starych
kont i jedna walidacja loginu we WSZYSTKICH trzech wejściach.

Atrapa DB zapisuje każde zapytanie — sprawdzamy, CO poszło do bazy (albo że
nic nie poszło), a nie tylko kod odpowiedzi.
"""
from __future__ import annotations

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_SEKRET = "sekret-testowy-do-jwt-min-32-znaki-xx"
_HASLO = "bezpieczne-haslo-123"


class _Kursor:
    def __init__(self, wiersz=None, rowcount: int = 1):
        self._w = wiersz
        self.rowcount = rowcount

    def fetchone(self):
        return self._w


class _Baza:
    """Jedna atrapa na wszystkie `connect()` w handlerze."""

    def __init__(self, *, birth_ym=None, token_version: int = 0, opt_in: bool = False):
        self.zapytania: list[tuple[str, tuple]] = []
        self.birth_ym = birth_ym
        self.token_version = token_version
        self.opt_in = opt_in

    def execute(self, sql, params=()):
        plaski = " ".join(sql.split())
        self.zapytania.append((plaski, tuple(params)))
        gorny = plaski.upper()
        if gorny.startswith("INSERT INTO USERS"):
            return _Kursor({"id": 41, "username": params[0], "is_admin": False,
                            "is_active": True})
        if gorny.startswith("UPDATE USERS SET BIRTH_YM"):
            zapisane = self.birth_ym is None
            if zapisane:
                self.birth_ym = params[0]
            return _Kursor(rowcount=1 if zapisane else 0)
        if gorny.startswith("SELECT PASSWORD_HASH"):
            import bcrypt
            h = bcrypt.hashpw(_HASLO.encode(), bcrypt.gensalt(4)).decode()
            return _Kursor({"password_hash": h, "is_admin": False,
                            "token_version": self.token_version})
        if gorny.startswith("SELECT ID, USERNAME, EMAIL"):
            return _Kursor({"id": 41, "username": "ktos", "email": "k@x.pl",
                            "is_admin": False, "telegram_chat_id": None,
                            "leaderboard_opt_in": self.opt_in, "birth_ym": self.birth_ym})
        if gorny.startswith("SELECT COALESCE(TOKEN_VERSION"):
            return _Kursor({"wersja": self.token_version, "is_active": True})
        return _Kursor(None)

    def zapisy(self, poczatek: str) -> list[tuple[str, tuple]]:
        return [(s, p) for s, p in self.zapytania if s.upper().startswith(poczatek.upper())]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def baza(monkeypatch):
    b = _Baza()
    monkeypatch.setattr("footstats.utils.db.connect", lambda *a, **k: b)
    monkeypatch.setattr("footstats.utils.mailer.send_welcome_email", lambda *a, **k: True)
    monkeypatch.setenv("JWT_SECRET", _SEKRET)
    return b


@pytest.fixture
def klient(baza):
    from footstats.api.auth import require_admin, require_auth, router
    from footstats.api.limiter import limiter
    from footstats.api.routes.admin_users import router as admin_router

    app = FastAPI()
    app.include_router(router)
    app.include_router(admin_router)
    app.dependency_overrides[require_auth] = lambda: 41
    app.dependency_overrides[require_admin] = lambda: 1
    limiter.enabled = False
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        limiter.enabled = True


def _rejestracja(**zmiany) -> dict:
    dane = {"username": "nowy_kibic", "email": "nowy@example.com",
            "password": _HASLO, "birth_ym": "1995-04"}
    dane.update(zmiany)
    return {k: v for k, v in dane.items() if v is not None}


def _komunikat(r) -> str:
    return " ".join(d.get("msg", "") for d in r.json().get("detail", []))


# ── rejestracja ─────────────────────────────────────────────────────────────

def test_rejestracja_zapisuje_miesiac_urodzenia_i_brak_zgody_domyslnie(klient, baza):
    r = klient.post("/api/auth/register", json=_rejestracja())

    assert r.status_code == 201, r.text
    [(sql, params)] = baza.zapisy("INSERT INTO users")
    assert "birth_ym" in sql and "leaderboard_opt_in" in sql
    assert "1995-04" in params
    assert params[-1] is False, "zgoda na ranking ma być domyślnie WYŁĄCZONA"


def test_rejestracja_ze_zgoda_na_ranking(klient, baza):
    r = klient.post("/api/auth/register", json=_rejestracja(leaderboard_opt_in=True))

    assert r.status_code == 201, r.text
    [(_, params)] = baza.zapisy("INSERT INTO users")
    assert params[-1] is True


def test_rejestracja_bez_miesiaca_urodzenia_odrzucona(klient, baza):
    r = klient.post("/api/auth/register", json=_rejestracja(birth_ym=None))

    assert r.status_code == 422
    assert baza.zapisy("INSERT INTO users") == []


def test_rejestracja_niepelnoletniego_odrzucona_bez_zapisu(klient, baza):
    r = klient.post("/api/auth/register", json=_rejestracja(birth_ym="2012-01"))

    assert r.status_code == 422
    assert "18 lat" in _komunikat(r)
    assert baza.zapisy("INSERT INTO users") == []


# ── jedna walidacja loginu w trzech wejściach ───────────────────────────────

_ZLY_LOGIN = "kurwa_mac"


def test_rejestracja_z_wulgarnym_loginem_odrzucona(klient, baza):
    r = klient.post("/api/auth/register", json=_rejestracja(username=_ZLY_LOGIN))

    assert r.status_code == 422
    assert "niedozwolone" in _komunikat(r)
    assert baza.zapisy("INSERT INTO users") == []


def test_zmiana_loginu_na_wulgarny_odrzucona(klient, baza):
    r = klient.post("/api/auth/change-username",
                    json={"current_password": _HASLO, "new_username": _ZLY_LOGIN})

    assert r.status_code == 422
    assert "niedozwolone" in _komunikat(r)
    assert baza.zapisy("UPDATE users SET username") == []


def test_admin_nie_zalozy_konta_z_wulgarnym_loginem(klient, baza):
    r = klient.post("/api/admin/users", json={"username": _ZLY_LOGIN, "password": _HASLO})

    assert r.status_code == 422
    assert "niedozwolone" in _komunikat(r)
    assert baza.zapisy("INSERT INTO users") == []


def test_zmiana_loginu_oddaje_token_z_aktualna_wersja_sesji(klient, baza):
    """Po zmianie hasła token_version > 0. Token wydany przy zmianie loginu z tv=0
    byłby odrzucony przy następnym żądaniu — user wylogowany zaraz po zmianie."""
    baza.token_version = 3

    r = klient.post("/api/auth/change-username",
                    json={"current_password": _HASLO, "new_username": "nowa_nazwa"})

    assert r.status_code == 200, r.text
    payload = jwt.decode(r.json()["access_token"], _SEKRET, algorithms=["HS256"])
    assert payload["tv"] == 3
    assert payload["sub"] == "nowa_nazwa"


# ── prośba o wiek dla istniejących kont ─────────────────────────────────────

def test_me_zwraca_brak_miesiaca_urodzenia(klient, baza):
    r = klient.get("/api/auth/me")

    assert r.status_code == 200
    assert r.json()["birth_ym"] is None


def test_uzupelnienie_miesiaca_urodzenia(klient, baza):
    r = klient.post("/api/auth/birth", json={"birth_ym": "1988-11"})

    assert r.status_code == 200, r.text
    [(sql, params)] = baza.zapisy("UPDATE users SET birth_ym")
    assert "birth_ym IS NULL" in sql, "raz wpisanej daty nie da się nadpisać"
    assert params == ("1988-11", 41)


def test_uzupelnienie_niepelnoletni_nie_zapisuje(klient, baza):
    r = klient.post("/api/auth/birth", json={"birth_ym": "2010-06"})

    assert r.status_code == 422
    assert "18 lat" in _komunikat(r)
    assert baza.zapisy("UPDATE users SET birth_ym") == []


def test_uzupelnienie_gdy_juz_wpisane_409(klient, baza):
    baza.birth_ym = "1990-01"

    r = klient.post("/api/auth/birth", json={"birth_ym": "1980-01"})

    assert r.status_code == 409
    assert baza.birth_ym == "1990-01"


def test_usuniecie_konta_kasuje_miesiac_urodzenia(klient, baza):
    klient.request("DELETE", "/api/auth/me", json={"password": _HASLO})

    [(sql, _)] = baza.zapisy("UPDATE users SET username")
    assert "birth_ym = NULL" in sql


# ── migracja ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("dialekt", ["sqlite", "postgresql"])
def test_migracja_18_dodaje_birth_ym(dialekt):
    from footstats.db.migrations import _get_migrations_for_dialect

    [m18] = [m for m in _get_migrations_for_dialect(dialekt) if m[0] == 18]
    sql = " ".join(m18[2]).lower()
    assert "alter table users" in sql and "birth_ym" in sql
