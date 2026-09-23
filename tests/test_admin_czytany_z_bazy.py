"""Uprawnienie admina bierze się z BAZY, nie z claimu w tokenie.

ZNALEZISKO (audyt bezpieczeństwa 24.09.2026): `require_admin` sprawdzał wyłącznie
`payload["adm"]` — flagę zapisaną w tokenie w chwili logowania. Token żyje 24 h,
więc odebranie komuś uprawnień admina (`UPDATE users SET is_admin = FALSE`) nie
robiło NIC do końca doby: stary token dalej wchodził na `/api/admin/*`.

To ta sama klasa błędu co B1 (17.08), gdzie zmiana hasła nie odbierała sesji.
Tam naprawiono ją przez `token_version`; tu claim `adm` został pominięty, bo nie
ma jeszcze endpointu degradującego admina — degradacja to dziś ręczny UPDATE
w bazie, czyli dokładnie ta czynność, którą wykonuje się po incydencie i po
której chce się natychmiastowego skutku.

Koszt naprawy: jeden odczyt wiersza użytkownika na żądanie administracyjne.
Endpointów admina jest kilka i wołane są rzadko — to nie jest ścieżka gorąca.

AWARIA ODCZYTU PRZEPUSZCZA na podstawie claimu — tak samo jak `_sprawdz_wersje`.
Nie zamyka to żadnej realnej drogi: każdy endpoint administracyjny czyta bazę,
więc przy niedostępnej bazie i tak nic nie zwróci. Fail-closed wywracałby za to
panel przy każdym zakrztuszeniu poolera. Odrzucenie następuje wtedy, gdy baza
mówi WPROST `is_admin = FALSE`.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import footstats.api.auth as auth


@pytest.fixture(autouse=True)
def sekret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "testowy-sekret-1234567890abcdef")


def _cred(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _ustaw_stan(monkeypatch, *, wersja=0, aktywne=True, admin=True):
    monkeypatch.setattr(auth, "stan_sesji",
                        lambda uid: {"wersja": wersja, "aktywne": aktywne, "admin": admin})


def test_admin_z_bazy_przechodzi(monkeypatch):
    _ustaw_stan(monkeypatch, admin=True)
    token = auth._make_token("szef", 1, is_admin=True)
    assert auth.require_admin(_cred(token)) == 1


def test_odebrane_uprawnienie_dziala_od_razu(monkeypatch):
    """SEDNO: token nadal twierdzi `adm=true`, baza mówi inaczej — liczy się baza."""
    _ustaw_stan(monkeypatch, admin=False)
    token = auth._make_token("bylyszef", 1, is_admin=True)

    with pytest.raises(HTTPException) as exc:
        auth.require_admin(_cred(token))

    assert exc.value.status_code == 403


def test_token_bez_claimu_admina_dalej_odrzucany(monkeypatch):
    """Podniesienie uprawnień przez samą bazę też nie działa bez nowego tokenu —
    obie strony muszą się zgadzać, więc nadanie admina wymaga przelogowania.
    Ta asymetria jest zamierzona: token to deklaracja, baza to prawda."""
    _ustaw_stan(monkeypatch, admin=True)
    token = auth._make_token("zwykly", 2, is_admin=False)

    with pytest.raises(HTTPException) as exc:
        auth.require_admin(_cred(token))
    assert exc.value.status_code == 403


def test_nieczytelny_stan_konta_przepuszcza_claim(monkeypatch):
    """Awaria odczytu PRZEPUSZCZA — świadomie, spójnie z `_sprawdz_wersje`.

    Kuszące jest zamknąć bramkę, ale to nie zamyka żadnej realnej drogi: każdy
    endpoint administracyjny czyta bazę, więc przy niedostępnej bazie i tak nie
    zwróci ani nie zmieni niczego. Fail-closed wywracałby natomiast panel przy
    każdym zakrztuszeniu poolera. Odrzucamy tylko wtedy, gdy baza mówi WPROST,
    że to nie admin — patrz test wyżej.
    """
    monkeypatch.setattr(auth, "stan_sesji", lambda uid: None)
    token = auth._make_token("szef", 1, is_admin=True)

    assert auth.require_admin(_cred(token)) == 1


def test_stan_sesji_oddaje_flage_admina():
    """Kontrakt, na którym stoi cała reszta tego pliku: `stan_sesji` musi
    zwracać `admin`. Bez tego klucza `require_admin` nie ma czego porównać.

    """
    import inspect
    zrodlo = inspect.getsource(auth.stan_sesji)
    assert "is_admin" in zrodlo, "stan_sesji nie czyta is_admin z bazy"
    assert '"admin"' in zrodlo, "stan_sesji nie zwraca klucza `admin`"
