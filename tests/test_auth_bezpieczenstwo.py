"""test_auth_bezpieczenstwo.py — warstwa logowania, tokenow i resetu hasla.

PO CO: to jedyne miejsce w projekcie, gdzie blad daje dostep do cudzego konta,
a nie zla predykcje. Modul mial 59% i brakowalo wlasnie sciezek bezpieczenstwa.

Trzy rzeczy pilnowane najmocniej:

  * `reset_password` MUSI odrzucic token logowania. Token resetu ma claim
    `purpose="reset"`; bez tego sprawdzenia zwykly token sesji pozwalalby zmienic
    haslo dowolnego konta, do ktorego sie ma dostep.
  * BRAK ENUMERACJI KONT. `/auth/login` oddaje ten sam komunikat dla nieznanego
    uzytkownika i zlego hasla; `/auth/forgot-password` ZAWSZE 200 z generycznym
    tekstem — nawet gdy padnie baza albo mailer.
  * `require_admin` oddaje 403 (nie 401) dla wazneho tokenu bez uprawnien —
    401 sugerowalby, ze token jest zly, i mylil klienta.

Kontekst incydentu: 2026-07-27 redeploy zgubil `JWT_SECRET` z env Cloud Run,
przez co logowanie zwracalo 500 udajace "zle haslo". Stad jawny test na to,
ze brak sekretu daje glosny blad, a nie ciche 401.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import jwt

import footstats.api.auth as auth

_HASLO = "tajne-haslo-123"
_HASH = bcrypt.hashpw(_HASLO.encode(), bcrypt.gensalt()).decode()


@pytest.fixture(autouse=True)
def sekret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "testowy-sekret-1234567890abcdef")


def _uzytkownik(uid=1, username="admin", is_admin=False, haslo_hash=_HASH) -> dict:
    return {"id": uid, "username": username,
            "password_hash": haslo_hash, "is_admin": is_admin}


def _cred(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


# ── _secret ─────────────────────────────────────────────────────────────────

def test_brak_sekretu_daje_glosny_blad(monkeypatch):
    """INCYDENT 2026-07-27: redeploy zgubil JWT_SECRET i logowanie oddawalo 500
    udajace "zle haslo". Blad ma byc GLOSNY, nie zamieniony na 401."""
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        auth._secret()


def test_pusty_sekret_tez_odrzucany(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "")
    with pytest.raises(RuntimeError):
        auth._secret()


# ── _verify_password ────────────────────────────────────────────────────────

def test_poprawne_haslo_akceptowane():
    assert auth._verify_password(_HASLO, _HASH) is True


def test_zle_haslo_odrzucone():
    assert auth._verify_password("nie-to-haslo", _HASH) is False


@pytest.mark.parametrize("uszkodzony", ["changeme", "", "nie-jest-hashem", "$2b$xx"])
def test_uszkodzony_hash_daje_false_a_nie_wyjatek(uszkodzony):
    """AUDYT 2026-07-27: zly salt rzucal ValueError -> logowanie konczylo sie 500
    zamiast 401. Seed placeholder 'changeme' z migracji to realny przypadek."""
    assert auth._verify_password(_HASLO, uszkodzony) is False


def test_hash_none_nie_wywala():
    assert auth._verify_password(_HASLO, None) is False


# ── _make_token ─────────────────────────────────────────────────────────────

def test_token_zawiera_komplet_claimow():
    token = auth._make_token("admin", 7, is_admin=True)
    dane = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[auth._ALGORITHM])

    assert dane["sub"] == "admin"
    assert dane["uid"] == 7
    assert dane["adm"] is True
    assert "exp" in dane


def test_token_domyslnie_bez_admina():
    token = auth._make_token("user", 2)
    dane = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[auth._ALGORITHM])
    assert dane["adm"] is False


def test_token_wygasa():
    token = auth._make_token("admin", 1)
    dane = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[auth._ALGORITHM])
    wygasa = datetime.fromtimestamp(dane["exp"], tz=timezone.utc)
    assert wygasa > datetime.now(timezone.utc)


# ── require_auth ────────────────────────────────────────────────────────────

def test_wazny_token_daje_user_id():
    assert auth.require_auth(_cred(auth._make_token("admin", 42))) == 42


def test_brak_tokenu_to_401():
    with pytest.raises(HTTPException) as exc:
        auth.require_auth(None)
    assert exc.value.status_code == 401


def test_uszkodzony_token_to_401():
    with pytest.raises(HTTPException) as exc:
        auth.require_auth(_cred("to-nie-jest-jwt"))
    assert exc.value.status_code == 401


def test_token_podpisany_innym_sekretem_odrzucony():
    """Podrobiony token nie moze przejsc — podpis jest jedyna gwarancja."""
    obcy = jwt.encode({"sub": "haker", "uid": 999,
                       "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                      "CUDZY-SEKRET", algorithm=auth._ALGORITHM)
    with pytest.raises(HTTPException) as exc:
        auth.require_auth(_cred(obcy))
    assert exc.value.status_code == 401


def test_wygasly_token_odrzucony():
    stary = jwt.encode({"sub": "admin", "uid": 1,
                        "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
                       os.environ["JWT_SECRET"], algorithm=auth._ALGORITHM)
    with pytest.raises(HTTPException) as exc:
        auth.require_auth(_cred(stary))
    assert exc.value.status_code == 401


def test_token_bez_uid_odrzucony():
    """Stary format tokenu (sam `sub`) nie moze dawac dostepu."""
    bez_uid = jwt.encode({"sub": "admin",
                          "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                         os.environ["JWT_SECRET"], algorithm=auth._ALGORITHM)
    with pytest.raises(HTTPException) as exc:
        auth.require_auth(_cred(bez_uid))
    assert exc.value.status_code == 401
    assert "re-login" in exc.value.detail


# ── require_admin ───────────────────────────────────────────────────────────

def test_admin_przechodzi():
    token = auth._make_token("admin", 1, is_admin=True)
    assert auth.require_admin(_cred(token)) == 1


def test_zwykly_user_dostaje_403_nie_401():
    """403 = "wiem kim jestes, ale nie wolno ci". 401 sugerowaloby zly token."""
    token = auth._make_token("user", 5, is_admin=False)
    with pytest.raises(HTTPException) as exc:
        auth.require_admin(_cred(token))
    assert exc.value.status_code == 403


def test_brak_claimu_adm_to_403():
    bez_adm = jwt.encode({"sub": "user", "uid": 5,
                          "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                         os.environ["JWT_SECRET"], algorithm=auth._ALGORITHM)
    with pytest.raises(HTTPException) as exc:
        auth.require_admin(_cred(bez_adm))
    assert exc.value.status_code == 403


def test_admin_bez_tokenu_to_401():
    with pytest.raises(HTTPException) as exc:
        auth.require_admin(None)
    assert exc.value.status_code == 401


def test_admin_z_podrobionym_tokenem_to_401():
    """Podrobiony token z adm=True nie moze dac uprawnien."""
    obcy = jwt.encode({"sub": "haker", "uid": 1, "adm": True,
                       "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                      "CUDZY-SEKRET", algorithm=auth._ALGORITHM)
    with pytest.raises(HTTPException) as exc:
        auth.require_admin(_cred(obcy))
    assert exc.value.status_code == 401


# ── login: brak enumeracji kont ─────────────────────────────────────────────

@pytest.fixture
def baza(monkeypatch):
    stan = {"po_nazwie": None, "po_mailu": None, "blad": None}

    def _po_nazwie(u):
        if stan["blad"]:
            raise stan["blad"]
        return stan["po_nazwie"]

    def _po_mailu(e):
        if stan["blad"]:
            raise stan["blad"]
        return stan["po_mailu"]

    monkeypatch.setattr(auth, "get_user_by_username", _po_nazwie)
    monkeypatch.setattr(auth, "get_user_by_email", _po_mailu)
    return stan


class _Req:
    """Atrapa Request wymagana przez limiter."""
    client = type("c", (), {"host": "127.0.0.1"})()
    headers: dict = {}
    url = type("u", (), {"path": "/api/auth/login"})()
    scope: dict = {}


def _login(username="admin", password=_HASLO):
    return auth.login.__wrapped__(
        _Req(), auth.LoginRequest(username=username, password=password)
    )


def test_udane_logowanie_zwraca_token(baza):
    baza["po_nazwie"] = _uzytkownik()
    odp = _login()
    dane = jwt.decode(odp.access_token, os.environ["JWT_SECRET"],
                      algorithms=[auth._ALGORITHM])
    assert dane["uid"] == 1


def test_ten_sam_komunikat_dla_nieznanego_i_zlego_hasla(baza):
    """Rozny komunikat = enumeracja kont (OWASP)."""
    baza["po_nazwie"] = None
    with pytest.raises(HTTPException) as nieznany:
        _login()

    baza["po_nazwie"] = _uzytkownik()
    with pytest.raises(HTTPException) as zle_haslo:
        _login(password="nie-to-haslo")

    assert nieznany.value.status_code == zle_haslo.value.status_code == 401
    assert nieznany.value.detail == zle_haslo.value.detail


def test_logowanie_mailem_gdy_brak_po_nazwie(baza):
    baza["po_nazwie"] = None
    baza["po_mailu"] = _uzytkownik(uid=3)
    assert _login(username="ktos@example.com") is not None


def test_bez_malpy_nie_szuka_po_mailu(baza):
    """Oszczedza zbedne zapytanie i nie ujawnia, ze pole bywa mailem."""
    baza["po_nazwie"] = None
    baza["po_mailu"] = _uzytkownik()
    with pytest.raises(HTTPException):
        _login(username="zwykla-nazwa")


def test_flaga_admina_trafia_do_tokenu(baza):
    baza["po_nazwie"] = _uzytkownik(is_admin=True)
    dane = jwt.decode(_login().access_token, os.environ["JWT_SECRET"],
                      algorithms=[auth._ALGORITHM])
    assert dane["adm"] is True


# ── reset hasla ─────────────────────────────────────────────────────────────

def test_token_resetu_ma_claim_purpose():
    token = auth._make_reset_token(7)
    dane = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[auth._ALGORITHM])
    assert dane["purpose"] == "reset"
    assert dane["uid"] == 7


def test_token_resetu_wygasa_szybciej_niz_login():
    reset = jwt.decode(auth._make_reset_token(1), os.environ["JWT_SECRET"],
                       algorithms=[auth._ALGORITHM])
    login = jwt.decode(auth._make_token("admin", 1), os.environ["JWT_SECRET"],
                       algorithms=[auth._ALGORITHM])
    assert reset["exp"] < login["exp"]


@pytest.fixture
def db_zapis(monkeypatch):
    """Przechwytuje UPDATE-y do users."""
    zapisy = []

    class _Conn:
        def execute(self, sql, params=()):
            zapisy.append((" ".join(sql.split()), params))
            return self

        def fetchone(self):
            return None

        def commit(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import footstats.utils.db as dbmod
    monkeypatch.setattr(dbmod, "connect", lambda *a, **k: _Conn())
    return zapisy


def _reset(token, nowe="nowe-haslo-1234"):
    return auth.reset_password.__wrapped__(
        _Req(), auth.ResetPasswordRequest(token=token, new_password=nowe)
    )


def test_reset_odrzuca_token_logowania(db_zapis):
    """KRYTYCZNE: bez sprawdzenia `purpose` zwykly token sesji pozwalalby
    zmienic haslo konta, do ktorego sie ma dostep."""
    token_logowania = auth._make_token("admin", 1, is_admin=True)
    with pytest.raises(HTTPException) as exc:
        _reset(token_logowania)

    assert exc.value.status_code == 400
    assert db_zapis == [], "haslo zmienione tokenem logowania"


def test_reset_odrzuca_uszkodzony_token(db_zapis):
    with pytest.raises(HTTPException) as exc:
        _reset("nie-jest-jwt")
    assert exc.value.status_code == 400
    assert db_zapis == []


def test_reset_odrzuca_wygasly_token(db_zapis):
    stary = jwt.encode({"uid": 1, "purpose": "reset",
                        "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                       os.environ["JWT_SECRET"], algorithm=auth._ALGORITHM)
    with pytest.raises(HTTPException):
        _reset(stary)
    assert db_zapis == []


def test_reset_odrzuca_token_podpisany_obcym_sekretem(db_zapis):
    obcy = jwt.encode({"uid": 1, "purpose": "reset",
                       "exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
                      "CUDZY-SEKRET", algorithm=auth._ALGORITHM)
    with pytest.raises(HTTPException):
        _reset(obcy)
    assert db_zapis == []


def test_reset_wazny_token_zmienia_haslo(db_zapis):
    """ZMIANA INTENCJI 17.08: reset robi teraz DWA zapisy, nie jeden.

    Drugi to podbicie `token_version`. Reset hasla to najczestsza reakcja na
    przejecie konta, wiec musi wyrzucic napastnika ze WSZYSTKICH urzadzen —
    wczesniej stary token dzialal dalej do konca doby (znalezisko B1).
    """
    _reset(auth._make_reset_token(7))
    update = [z for z in db_zapis if z[0].upper().startswith("UPDATE USERS")]
    assert len(update) == 2

    haslo = [u for u in update if "password_hash" in u[0]]
    assert len(haslo) == 1
    assert haslo[0][1][1] == 7                        # uid z tokenu
    assert bcrypt.checkpw(b"nowe-haslo-1234", haslo[0][1][0].encode())

    sesje = [u for u in update if "token_version" in u[0]]
    assert len(sesje) == 1, "reset hasla musi uniewazniac sesje"
    assert sesje[0][1][0] == 7


def test_reset_dotyczy_tylko_konta_aktywnego(db_zapis):
    _reset(auth._make_reset_token(7))
    sql = [z for z in db_zapis if z[0].upper().startswith("UPDATE USERS")][0][0]
    assert "is_active" in sql.lower()


# ── forgot-password: zawsze 200 ─────────────────────────────────────────────

def _forgot(email="ktos@example.com"):
    return auth.forgot_password.__wrapped__(
        _Req(), auth.ForgotPasswordRequest(email=email)
    )


def test_nieznany_mail_daje_ten_sam_komunikat(baza, monkeypatch):
    baza["po_mailu"] = None
    assert _forgot()["message"] == auth._GENERIC_RESET_MSG


def test_awaria_bazy_nie_wycieka(baza):
    """Padnieta baza nie moze zdradzic, ze konto istnieje — nadal 200."""
    baza["blad"] = RuntimeError("baza padla")
    assert _forgot()["message"] == auth._GENERIC_RESET_MSG


def test_awaria_mailera_nie_wycieka(baza, monkeypatch):
    baza["po_mailu"] = _uzytkownik()

    import footstats.utils.mailer as mailer

    def _wybuch(*a, **k):
        raise OSError("SMTP padl")

    monkeypatch.setattr(mailer, "send_password_reset_email", _wybuch, raising=False)
    assert _forgot()["message"] == auth._GENERIC_RESET_MSG


def test_link_resetu_zawiera_token(baza, monkeypatch):
    baza["po_mailu"] = _uzytkownik(uid=9)
    monkeypatch.setenv("FRONTEND_URL", "https://footstats.example/")

    wyslane = {}
    import footstats.utils.mailer as mailer
    monkeypatch.setattr(mailer, "send_password_reset_email",
                        lambda mail, link: wyslane.update(mail=mail, link=link),
                        raising=False)
    _forgot()

    assert wyslane["link"].startswith("https://footstats.example/reset-password?token=")
    token = wyslane["link"].split("token=")[1]
    dane = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[auth._ALGORITHM])
    assert dane["uid"] == 9 and dane["purpose"] == "reset"
