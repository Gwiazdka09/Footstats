"""test_auth_konto.py — zarządzanie kontem: usunięcie, zmiana loginu, Telegram.

PO CO: to endpointy, które zmieniają tożsamość konta albo je kasują. Każdy z nich
wymaga potwierdzenia HASŁEM, bo sam token nie wystarcza — token da się ukraść,
a wtedy przejęcie sesji zamieniłoby się w trwałe przejęcie konta.

`delete_account` realizuje RODO przez ANONIMIZACJĘ, nie przez DELETE: historyczne
kupony i predykcje muszą zostać (rozliczenia, statystyki), tylko z odwołaniem do
zanonimizowanego użytkownika. Skasowanie wiersza zabrałoby ze sobą historię
zakładów.

`set_telegram_chat_id` jest świadomie oznaczony w kodzie jako DEPRECATED —
użytkownik deklaruje dowolny chat_id bez dowodu, że jest jego. Bezpieczna ścieżka
to nonce z `telegram_link_start`, weryfikowany przez webhook bota.
"""
from __future__ import annotations

import os

import bcrypt
import pytest

os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")

from fastapi.testclient import TestClient  # noqa: E402

import footstats.utils.db as dbmod  # noqa: E402
from footstats.api.auth import _make_token  # noqa: E402
from footstats.api.main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)

HASLO = "poprawne-haslo"
HASH = bcrypt.hashpw(HASLO.encode(), bcrypt.gensalt()).decode()


class _Kursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Conn:
    """Atrapa połączenia — notuje zapytania, oddaje ustalony wiersz users."""

    def __init__(self, row):
        self.row = row
        self.zapytania: list[tuple] = []
        self.blad: Exception | None = None

    def execute(self, sql, params=()):
        plaski = " ".join(sql.split())
        self.zapytania.append((plaski, params))
        if self.blad is not None and plaski.upper().startswith("UPDATE"):
            raise self.blad
        if plaski.upper().startswith("SELECT"):
            return _Kursor(self.row)
        return _Kursor(None)

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def zawierajace(self, fragment: str) -> list[tuple]:
        return [z for z in self.zapytania if fragment.upper() in z[0].upper()]


@pytest.fixture
def baza(monkeypatch):
    stan = {"conn": _Conn({"password_hash": HASH, "is_admin": False})}
    monkeypatch.setattr(dbmod, "connect", lambda *a, **k: stan["conn"])
    return stan


@pytest.fixture
def naglowki() -> dict:
    return {"Authorization": f"Bearer {_make_token('user', 42, is_admin=False)}"}


# ── delete_account: RODO przez anonimizację ─────────────────────────────────

def test_usuniecie_konta_wymaga_hasla(baza, naglowki):
    """Sam token nie wystarcza — skradziona sesja skasowałaby konto."""
    r = client.request("DELETE", "/api/auth/me", headers=naglowki,
                       json={"password": "zle-haslo"})

    assert r.status_code == 401
    assert baza["conn"].zawierajace("UPDATE users") == []


def test_usuniecie_konta_bez_tokenu_odrzucone(baza):
    r = client.request("DELETE", "/api/auth/me", json={"password": HASLO})

    assert r.status_code in (401, 403)
    assert baza["conn"].zawierajace("UPDATE users") == []


def test_admin_nie_usuwa_sie_ta_droga(baza, naglowki):
    """Utrata jedynego admina zablokowałaby rozliczenia i panel."""
    baza["conn"].row = {"password_hash": HASH, "is_admin": True}

    r = client.request("DELETE", "/api/auth/me", headers=naglowki,
                       json={"password": HASLO})

    assert r.status_code == 400
    assert baza["conn"].zawierajace("UPDATE users") == []


def test_nieistniejace_konto_to_404(baza, naglowki):
    baza["conn"].row = None

    r = client.request("DELETE", "/api/auth/me", headers=naglowki,
                       json={"password": HASLO})

    assert r.status_code == 404


def test_konto_anonimizowane_a_nie_kasowane(baza, naglowki):
    """DELETE zabrałby ze sobą historię kuponów i rozliczeń."""
    r = client.request("DELETE", "/api/auth/me", headers=naglowki,
                       json={"password": HASLO})

    assert r.status_code == 200
    assert baza["conn"].zawierajace("DELETE FROM users") == []
    update = baza["conn"].zawierajace("UPDATE users")
    assert len(update) == 1


def test_anonimizacja_czysci_dane_osobowe(baza, naglowki):
    client.request("DELETE", "/api/auth/me", headers=naglowki, json={"password": HASLO})

    sql, params = baza["conn"].zawierajace("UPDATE users")[0]
    assert "email = NULL" in sql
    assert "is_active = FALSE" in sql
    assert params[0] == "deleted_user_42"


def test_anonimizacja_ustawia_losowy_hash(baza, naglowki):
    """Stały albo pusty hash pozwoliłby zalogować się na skasowane konto."""
    client.request("DELETE", "/api/auth/me", headers=naglowki, json={"password": HASLO})

    params = baza["conn"].zawierajace("UPDATE users")[0][1]
    nowy_hash = params[1]
    assert nowy_hash != HASH
    assert not bcrypt.checkpw(HASLO.encode(), nowy_hash.encode())


def test_anonimizacja_dotyczy_tylko_wlasnego_konta(baza, naglowki):
    client.request("DELETE", "/api/auth/me", headers=naglowki, json={"password": HASLO})

    sql, params = baza["conn"].zawierajace("UPDATE users")[0]
    assert "WHERE id = ?" in sql
    assert params[-1] == 42


# ── change_username ─────────────────────────────────────────────────────────

def test_zmiana_loginu_wymaga_hasla(baza, naglowki):
    """Bez tego przejęcie sesji pozwalałoby przejąć tożsamość na stałe."""
    r = client.post("/api/auth/change-username", headers=naglowki,
                    json={"current_password": "zle", "new_username": "nowy_login"})

    assert r.status_code == 401
    assert baza["conn"].zawierajace("UPDATE users") == []


def test_zmiana_loginu_zwraca_nowy_token(baza, naglowki):
    """Stary token nosi stary login — bez wymiany GUI pokazywałoby poprzedni."""
    r = client.post("/api/auth/change-username", headers=naglowki,
                    json={"current_password": HASLO, "new_username": "nowy_login"})

    assert r.status_code == 200
    assert r.json()["access_token"]


def test_zajety_login_to_konflikt(baza, naglowki):
    import psycopg2
    baza["conn"].blad = psycopg2.errors.UniqueViolation("duplicate key")

    r = client.post("/api/auth/change-username", headers=naglowki,
                    json={"current_password": HASLO, "new_username": "zajety"})

    assert r.status_code == 409


@pytest.mark.parametrize("krotki", ["", "a", "ab", "  ab  "])
def test_login_ponizej_trzech_znakow_odrzucony(baza, naglowki, krotki):
    r = client.post("/api/auth/change-username", headers=naglowki,
                    json={"current_password": HASLO, "new_username": krotki})

    assert r.status_code == 422
    assert baza["conn"].zawierajace("UPDATE users") == []


def test_login_przyciety_z_bialych_znakow(baza, naglowki):
    client.post("/api/auth/change-username", headers=naglowki,
                json={"current_password": HASLO, "new_username": "  nowy_login  "})

    params = baza["conn"].zawierajace("UPDATE users")[0][1]
    assert params[0] == "nowy_login"


def test_zmiana_loginu_nieistniejacego_konta(baza, naglowki):
    baza["conn"].row = None

    r = client.post("/api/auth/change-username", headers=naglowki,
                    json={"current_password": HASLO, "new_username": "nowy_login"})

    assert r.status_code == 404


# ── get_me ──────────────────────────────────────────────────────────────────

def test_me_zwraca_dane_konta(baza, naglowki):
    baza["conn"].row = {"id": 42, "username": "user", "email": "a@b.pl",
                        "is_admin": False, "telegram_chat_id": None}

    r = client.get("/api/auth/me", headers=naglowki)

    assert r.status_code == 200
    assert r.json()["username"] == "user"


def test_me_nie_wystawia_hasla(baza, naglowki):
    """Hash hasła nie ma prawa opuścić serwera."""
    baza["conn"].row = {"id": 42, "username": "user", "email": None,
                        "is_admin": False, "telegram_chat_id": None}

    r = client.get("/api/auth/me", headers=naglowki)

    assert "password" not in r.text.lower()


def test_me_konta_nieaktywnego_to_404(baza, naglowki):
    """Zapytanie filtruje po is_active — konto zanonimizowane nie istnieje."""
    baza["conn"].row = None

    r = client.get("/api/auth/me", headers=naglowki)

    assert r.status_code == 404
    assert "is_active = TRUE" in baza["conn"].zawierajace("SELECT")[0][0]


def test_me_bez_tokenu_odrzucone(baza):
    assert client.get("/api/auth/me").status_code in (401, 403)


# ── Telegram: ścieżka deprecated i ścieżka z nonce ──────────────────────────

@pytest.mark.parametrize("chat_id", ["12345", "-1001234567890"])
def test_poprawny_chat_id_zapisany(baza, naglowki, chat_id):
    r = client.post("/api/auth/telegram", headers=naglowki, json={"chat_id": chat_id})

    assert r.status_code == 200
    assert baza["conn"].zawierajace("UPDATE users")[0][1][0] == chat_id


@pytest.mark.parametrize("zly", ["abc", "12a45", "'; DROP TABLE users;--",
                                 "12345678901234567890123"])
def test_niepoprawny_chat_id_odrzucony(baza, naglowki, zly):
    """Pole trafia do bazy — musi być numeryczne, nie dowolny tekst."""
    r = client.post("/api/auth/telegram", headers=naglowki, json={"chat_id": zly})

    assert r.status_code == 422
    assert baza["conn"].zawierajace("UPDATE users") == []


def test_pusty_chat_id_odlacza_powiadomienia(baza, naglowki):
    r = client.post("/api/auth/telegram", headers=naglowki, json={"chat_id": ""})

    assert r.status_code == 200
    assert r.json()["telegram_chat_id"] is None
    assert baza["conn"].zawierajace("UPDATE users")[0][1][0] is None


def test_telegram_bez_tokenu_odrzucone(baza):
    r = client.post("/api/auth/telegram", json={"chat_id": "123"})

    assert r.status_code in (401, 403)
    assert baza["conn"].zawierajace("UPDATE users") == []


def test_nonce_zapisany_z_terminem_waznosci(baza, naglowki):
    """Nonce bez terminu ważności zostawałby aktywny na zawsze."""
    r = client.post("/api/telegram/link/start", headers=naglowki)

    assert r.status_code == 200
    sql, params = baza["conn"].zawierajace("UPDATE users")[0]
    assert "telegram_link_nonce_exp" in sql
    assert params[0] == r.json()["nonce"]
    assert params[1] > ""


def test_kazdy_nonce_jest_inny(baza, naglowki):
    """Powtarzalny nonce pozwoliłby podpiąć cudze konto."""
    a = client.post("/api/telegram/link/start", headers=naglowki).json()["nonce"]
    b = client.post("/api/telegram/link/start", headers=naglowki).json()["nonce"]

    assert a != b
    assert len(a) >= 8


def test_nonce_przypisany_do_wlasciciela(baza, naglowki):
    client.post("/api/telegram/link/start", headers=naglowki)

    sql, params = baza["conn"].zawierajace("UPDATE users")[0]
    assert "WHERE id = ?" in sql
    assert params[-1] == 42


def test_nonce_bez_tokenu_odrzucony(baza):
    r = client.post("/api/telegram/link/start")

    assert r.status_code in (401, 403)
    assert baza["conn"].zawierajace("UPDATE users") == []
