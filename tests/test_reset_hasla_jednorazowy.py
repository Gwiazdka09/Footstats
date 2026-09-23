"""Link resetu hasła ma działać RAZ, nie przez godzinę.

ZNALEZISKO (audyt bezpieczeństwa 24.09.2026): `_make_reset_token` wystawiał JWT
z jednym claimem tożsamości — `uid` — i ważnością 60 minut. `reset_password`
sprawdzał wyłącznie podpis, `purpose` i `exp`. Nic nie zużywało tokenu, więc
ten sam link ustawiał hasło dowolną liczbę razy aż do wygaśnięcia.

DLACZEGO TO NIE JEST TEORIA: linki resetu wyciekają inaczej niż hasła — zostają
w skrzynce (także po przejęciu jej później), w historii przeglądarki, w logach
proxy i w kopii maila na innym urządzeniu. Realny scenariusz jest taki: ofiara
resetuje hasło, myśli, że odzyskała kontrolę, a napastnik z tym samym linkiem
ustawia własne hasło w ciągu następnej godziny. Podbicie `token_version` przy
resecie (B1, 17.08) wyrzucało wtedy z sesji WŁAŚCICIELA, nie napastnika.

JAK JEST NAPRAWIONE: token niesie `tv` — wersję sesji z chwili wystawienia.
`reset_password` porównuje ją z wersją w bazie, a udany reset tę wersję podbija,
więc drugie użycie tego samego tokenu trafia na niezgodność. Zero nowej tabeli
i zero nowego stanu: mechanizm unieważniania już istniał, brakowało tylko
związania z nim tokenu resetu.

FAIL CLOSED: gdy wersji nie da się odczytać (baza nieosiągalna), reset jest
odrzucany. Odwrotny wybór — „nie wiem, więc przepuszczam" — znosiłby całą
ochronę dokładnie w momencie awarii, a użytkownik po prostu powtarza reset.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

import footstats.api.auth as auth


@pytest.fixture(autouse=True)
def sekret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "testowy-sekret-1234567890abcdef")


class _Req:
    """Atrapa `Request` — `@limiter.limit` wymaga jej w sygnaturze."""
    client = type("C", (), {"host": "127.0.0.1"})()
    headers: dict = {}
    url = type("U", (), {"path": "/api/auth/reset-password"})()
    method = "POST"
    state = type("S", (), {})()
    scope: dict = {"type": "http"}


class _ConnZWersja:
    """Fałszywa baza: pamięta `token_version` i podbija je przy UPDATE.

    Odwzorowuje dokładnie ten fragment produkcji, o który chodzi — resztę
    (hash hasła) tylko zapisuje, żeby test mógł sprawdzić, czy w ogóle doszło
    do zmiany.
    """

    def __init__(self, wersja: int = 0, aktywne: bool = True) -> None:
        self.wersja = wersja
        self.aktywne = aktywne
        self.zapisy: list[tuple[str, tuple]] = []
        self._ostatni_select = False

    def execute(self, sql: str, params: tuple = ()):
        plaski = " ".join(sql.split())
        self.zapisy.append((plaski, params))
        gora = plaski.upper()
        self._ostatni_select = gora.startswith("SELECT")
        if gora.startswith("UPDATE USERS") and "token_version" in plaski:
            self.wersja += 1
        return self

    def fetchone(self):
        if not self._ostatni_select:
            return None
        return {"wersja": self.wersja, "is_active": self.aktywne}

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def baza(monkeypatch):
    conn = _ConnZWersja()
    import footstats.utils.db as dbmod
    monkeypatch.setattr(dbmod, "connect", lambda *a, **k: conn)
    return conn


def _reset(token: str, nowe: str = "nowe-haslo-1234"):
    return auth.reset_password.__wrapped__(
        _Req(), auth.ResetPasswordRequest(token=token, new_password=nowe)
    )


def _zapisy_hasla(conn: _ConnZWersja) -> list[tuple[str, tuple]]:
    return [z for z in conn.zapisy if "password_hash" in z[0]]


def test_token_resetu_niesie_wersje_sesji():
    """Bez claimu `tv` nie ma czego porównać — cała reszta ochrony na nim stoi."""
    dane = jwt.decode(auth._make_reset_token(7, 3), os.environ["JWT_SECRET"],
                      algorithms=[auth._ALGORITHM])
    assert dane["tv"] == 3
    assert dane["uid"] == 7
    assert dane["purpose"] == "reset"


def test_pierwsze_uzycie_zmienia_haslo(baza):
    _reset(auth._make_reset_token(7, baza.wersja))
    assert len(_zapisy_hasla(baza)) == 1


def test_drugie_uzycie_tego_samego_linku_odrzucone(baza):
    """SEDNO: napastnik z wyciekniętym linkiem nie ustawi hasła po ofierze."""
    token = auth._make_reset_token(7, baza.wersja)
    _reset(token)
    assert len(_zapisy_hasla(baza)) == 1

    with pytest.raises(HTTPException) as exc:
        _reset(token, nowe="haslo-napastnika-999")

    assert exc.value.status_code == 400
    assert len(_zapisy_hasla(baza)) == 1, "drugie użycie zmieniło hasło"


def test_token_wystawiony_przed_zmiana_hasla_jest_martwy(baza):
    """Użytkownik zmienił hasło samodzielnie — stary link resetu ma przestać działać.

    To ta sama niezgodność wersji, ale inna droga dojścia: sesje unieważnia
    zmiana hasła, a nie reset.
    """
    stary = auth._make_reset_token(7, baza.wersja)
    baza.wersja += 1                                   # zmiana hasła gdzie indziej

    with pytest.raises(HTTPException) as exc:
        _reset(stary)

    assert exc.value.status_code == 400
    assert _zapisy_hasla(baza) == []


def test_token_bez_claimu_tv_odrzucony(baza):
    """Tokeny wystawione przed tą zmianą nie mają `tv`. Wpuszczenie ich
    zostawiałoby otwartą furtkę na godzinę po wdrożeniu — a koszt to jedno
    ponowne kliknięcie „nie pamiętam hasła"."""
    bez_tv = jwt.encode(
        {"uid": 7, "purpose": "reset",
         "exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
        os.environ["JWT_SECRET"], algorithm=auth._ALGORITHM)

    with pytest.raises(HTTPException) as exc:
        _reset(bez_tv)

    assert exc.value.status_code == 400
    assert _zapisy_hasla(baza) == []


def test_gdy_wersji_nie_da_sie_odczytac_reset_odmawia(monkeypatch):
    """FAIL CLOSED — awaria bazy nie może znosić jednorazowości tokenu."""
    class _Martwa:
        def execute(self, sql, params=()):
            raise RuntimeError("baza nieosiągalna")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import footstats.utils.db as dbmod
    monkeypatch.setattr(dbmod, "connect", lambda *a, **k: _Martwa())

    with pytest.raises(HTTPException) as exc:
        _reset(auth._make_reset_token(7, 0))

    assert exc.value.status_code == 400


def test_forgot_password_wystawia_token_z_biezaca_wersja(monkeypatch):
    """Ogniwo między jednym a drugim: gdyby `forgot_password` wystawiał token
    ze stałą zerową wersją, każdy reset po pierwszej zmianie hasła byłby
    odrzucany i funkcja przestałaby działać w ogóle."""
    wyslane: dict = {}

    monkeypatch.setattr(auth, "get_user_by_email",
                        lambda email: {"id": 7, "token_version": 5})
    monkeypatch.setenv("FRONTEND_URL", "https://footstats.example")
    import footstats.utils.mailer as mailer
    monkeypatch.setattr(mailer, "send_password_reset_email",
                        lambda email, link: wyslane.update(email=email, link=link))

    auth.forgot_password.__wrapped__(
        _Req(), auth.ForgotPasswordRequest(email="ktos@example.com"))

    token = wyslane["link"].split("token=")[1]
    dane = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[auth._ALGORITHM])
    assert dane["tv"] == 5
