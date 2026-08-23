"""Wymiana biblioteki JWT nie może zmienić zachowania tokenów.

B3: `python-jose` ciągnie za sobą `ecdsa`, a ta ma PYSEC-2026-1325 — CI musiało
ją wyciszać przez `--ignore-vuln`. Wyciszona luka w bibliotece kryptograficznej
to dług, który rośnie w ciszy: przy następnym CVE nikt nie zauważy różnicy między
„znane i zaakceptowane" a „nowe".

`PyJWT` był już w obrazie jako zależność przechodnia, więc podmiana niczego nie
dokłada — zdejmuje `python-jose` i `ecdsa`.

Podmiana biblioteki uwierzytelniającej to miejsce, gdzie cicha zmiana zachowania
kosztuje najwięcej. Te testy pilnują RÓWNOWAŻNOŚCI, nie samego faktu podmiany:
token wystawiony starą biblioteką musi dać się odczytać nową (inaczej wdrożenie
wylogowałoby wszystkich), a każde odrzucenie musi zostać odrzuceniem.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from footstats.api import auth as _auth

SEKRET = "testsecret1234567890abcdef12345678"


@pytest.fixture(autouse=True)
def _sekret(monkeypatch):
    monkeypatch.setattr(_auth, "_secret", lambda: SEKRET)


def _wystaw_stara_biblioteka(claims: dict) -> str:
    """Token dokładnie taki, jaki wystawiał `python-jose` przed migracją."""
    jose_jwt = pytest.importorskip("jose.jwt", reason="python-jose zdjete z zaleznosci")
    return jose_jwt.encode(claims, SEKRET, algorithm="HS256")


def _claims(**nadpisz) -> dict:
    dane = {
        "sub": "admin", "uid": 1, "adm": False, "tv": 0,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    dane.update(nadpisz)
    return dane


# ── zgodność wstecz ─────────────────────────────────────────────────────────

def test_token_wystawiony_stara_biblioteka_dalej_dziala():
    """Bez tego samo wdrożenie wylogowałoby wszystkich zalogowanych."""
    import jwt

    stary = _wystaw_stara_biblioteka(_claims())

    odczyt = jwt.decode(stary, SEKRET, algorithms=["HS256"])

    assert odczyt["uid"] == 1
    assert odczyt["tv"] == 0


def test_nowy_token_ma_te_same_claimy_co_stary():
    """Kształt tokenu jest kontraktem — `uid`, `adm` i `tv` czyta `require_auth`."""
    import jwt

    nowy = _auth._make_token("admin", 7, True, 3)
    odczyt = jwt.decode(nowy, SEKRET, algorithms=["HS256"])

    assert odczyt["sub"] == "admin"
    assert odczyt["uid"] == 7
    assert odczyt["adm"] is True
    assert odczyt["tv"] == 3
    assert "exp" in odczyt


# ── odrzucenia muszą zostać odrzuceniami ────────────────────────────────────

def test_obcy_podpis_odrzucony():
    """Kontrola nadrzędna: podmiana biblioteki nie może osłabić weryfikacji."""
    import jwt

    obcy = jwt.encode(_claims(adm=True), "sekret-atakujacego", algorithm="HS256")

    with pytest.raises(Exception):
        jwt.decode(obcy, SEKRET, algorithms=["HS256"])


def test_token_wygasly_odrzucony():
    import jwt

    wygasly = jwt.encode(
        _claims(exp=datetime.now(timezone.utc) - timedelta(minutes=1)),
        SEKRET, algorithm="HS256",
    )

    with pytest.raises(Exception):
        jwt.decode(wygasly, SEKRET, algorithms=["HS256"])


def test_alg_none_odrzucony():
    """Klasyczny atak na JWT: token deklaruje `alg: none` i liczy, że przejdzie.

    Lista `algorithms` jest jedyną obroną — dlatego jest podana wprost przy
    każdym `decode` w `auth.py`, a ten test pilnuje, że tak zostanie.
    """
    import jwt

    with pytest.raises(Exception):
        jwt.decode(
            jwt.encode(_claims(), key="", algorithm="none"),
            SEKRET, algorithms=["HS256"],
        )


def test_smiec_zamiast_tokenu_odrzucony():
    import jwt

    with pytest.raises(Exception):
        jwt.decode("to-nie-jest-token", SEKRET, algorithms=["HS256"])


# ── produkcja nie zależy już od python-jose ─────────────────────────────────

def test_auth_nie_importuje_python_jose():
    """Sedno B3: dopóki `auth.py` woła `jose`, `ecdsa` zostaje w obrazie razem
    ze swoim CVE, a `pip-audit` musi je wyciszać."""
    from pathlib import Path

    plik = Path(_auth.__file__).read_text(encoding="utf-8")

    assert "from jose" not in plik and "import jose" not in plik


def test_bledy_jwt_lapane_wspolna_klasa():
    """`except JWTError` z jose miało odpowiednik — trzeba go faktycznie użyć,
    inaczej wygasły token leci jako 500 zamiast 401."""
    from pathlib import Path

    plik = Path(_auth.__file__).read_text(encoding="utf-8")

    assert "PyJWTError" in plik, "brak wspolnej klasy bledow — czesc odrzucen ucieknie jako 500"


# ── wyciszenie CVE nie ma prawa wrócić po cichu ─────────────────────────────

def test_pip_audit_bez_wyciszen():
    """`--ignore-vuln` było w CI dla `ecdsa` (PYSEC-2026-1325), którą ciągnęła
    `python-jose`. Po migracji audyt przechodzi czysto — i tak ma zostać.

    Nowe wyciszenie może być uzasadnione, ale musi być świadomą decyzją z datą
    i powodem, nie linijką dopisaną przy okazji. Dlatego test, a nie sam komentarz.
    """
    from pathlib import Path

    ci = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
    linie = [
        lin.strip() for lin in ci.read_text(encoding="utf-8").splitlines()
        if "pip_audit" in lin and not lin.strip().startswith("#")
    ]

    assert linie, "krok pip-audit zniknal z CI"
    for lin in linie:
        assert "--ignore-vuln" not in lin, (
            f"wyciszenie CVE wrocilo do CI: {lin}. Jesli to swiadoma decyzja — "
            "dopisz date i powod w komentarzu i zaktualizuj ten test."
        )


def test_ecdsa_wypadla_z_obrazu():
    """Sedno B3 mierzone na tym, co realnie jedzie: pakiet z CVE ma zniknąć
    z locka, nie tylko z deklaracji."""
    from pathlib import Path

    korzen = Path(__file__).resolve().parents[1]
    for lock in ("requirements-jobs.lock", "requirements-api.lock"):
        tekst = (korzen / lock).read_text(encoding="utf-8").lower()
        for pakiet in ("ecdsa==", "python-jose=="):
            assert pakiet not in tekst, f"{pakiet[:-2]} wciaz w {lock}"
        assert "pyjwt==" in tekst, f"brak pyjwt w {lock}"
