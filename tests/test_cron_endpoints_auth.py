"""test_cron_endpoints_auth.py — bramka `CRON_SECRET` i autoryzacja rozliczeń.

PO CO: cztery endpointy `/cron/*` uruchamiają pracę produkcyjną — rozliczają
kupony, generują draft, kasują cache — a jedyne, co je chroni, to porównanie
nagłówka `X-Cron-Secret`. Nie ma tu tokenu, użytkownika ani sesji.

Krytyczny przypadek: PUSTY `CRON_SECRET` w środowisku. `hmac.compare_digest("", "")`
zwraca True, więc jedynym bezpiecznikiem jest warunek `not expected`. Bez niego
deploy, który zgubi zmienne środowiskowe, zamienia te endpointy w publiczne
przyciski do produkcji. To nie jest teoria — 27.07 redeploy Cloud Run zgubił
JWT_SECRET i login zaczął zwracać 500 udające "złe hasło".

Drugi wątek: `/coupons/settle` rozlicza kupony WSZYSTKICH userów (brak filtra
user_id), więc musi być admin-only. Wcześniej wystarczyło być zalogowanym —
każdy mógł wymusić rozliczenie/VOID cudzych kuponów i przy okazji zdenerwować
FlashScore/API-Football wektorem DoS.

Wszystkie testy sprawdzają nie tylko kod odpowiedzi, ale i to, że przy odmowie
funkcja robocza NIE ZOSTAŁA WYWOŁANA. Sam 401 nic nie znaczy, jeśli robota
poszła przed odrzuceniem.
"""
from __future__ import annotations

import logging
import os

import pytest

os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")

from fastapi.testclient import TestClient  # noqa: E402

import footstats.core.cloud_draft as cd  # noqa: E402
import footstats.core.coupon_settlement as cs  # noqa: E402
import footstats.core.response_cache as rc  # noqa: E402
import footstats.utils.cache_evict as ce  # noqa: E402
from footstats.api.auth import _make_token  # noqa: E402
from footstats.api.main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)

SEKRET = "prawdziwy-sekret-crona-0123456789"


class Szpieg:
    """Atrapa funkcji roboczej — notuje wywołania i oddaje ustalony wynik."""

    def __init__(self, wynik=None):
        self.wynik = wynik if wynik is not None else {}
        self.wywolania: list[tuple] = []

    def __call__(self, *a, **kw):
        self.wywolania.append((a, kw))
        return self.wynik

    @property
    def wywolana(self) -> bool:
        return bool(self.wywolania)


# Każdy wpis: ścieżka, moduł z funkcją roboczą, nazwa funkcji, jej wynik.
CRONY = [
    ("/api/cron/settle", cs, "settle_active_coupons", {"settled": 2, "partial": 0, "errors": 0}),
    ("/api/cron/settle-manual", cs, "settle_manual_coupons", {"settled": 1, "skipped": 0, "errors": 0}),
    ("/api/cron/draft", cd, "generuj_system_draft", {"ok": True, "created": 3, "legs": []}),
    ("/api/cron/evict-cache", ce, "evict_old_cache", 5),
]
IDS = [c[0] for c in CRONY]


@pytest.fixture
def czysty_cache(monkeypatch):
    monkeypatch.setattr(rc, "clear_response_cache", lambda: None, raising=False)


@pytest.fixture(params=CRONY, ids=IDS)
def cron(request, monkeypatch, czysty_cache):
    """Podstawia atrapę pod funkcję roboczą danego crona."""
    sciezka, modul, nazwa, wynik = request.param
    szpieg = Szpieg(wynik)
    monkeypatch.setattr(modul, nazwa, szpieg)
    monkeypatch.setenv("CRON_SECRET", SEKRET)
    return sciezka, szpieg


# ── bramka CRON_SECRET ──────────────────────────────────────────────────────

def test_zly_sekret_odrzucony_i_nic_sie_nie_dzieje(cron):
    sciezka, szpieg = cron
    r = client.post(sciezka, headers={"X-Cron-Secret": "zly-sekret"})

    assert r.status_code == 401
    assert not szpieg.wywolana, "robota poszła mimo odrzucenia"


def test_brak_naglowka_odrzucony(cron):
    sciezka, szpieg = cron
    r = client.post(sciezka)

    assert r.status_code == 401
    assert not szpieg.wywolana


def test_prefiks_sekretu_nie_wystarcza(cron):
    """Zabezpiecza przed regresją na `startswith` / porównanie częściowe."""
    sciezka, szpieg = cron
    r = client.post(sciezka, headers={"X-Cron-Secret": SEKRET[:-1]})

    assert r.status_code == 401
    assert not szpieg.wywolana


def test_sekret_z_doklejonym_ogonem_nie_wystarcza(cron):
    sciezka, szpieg = cron
    r = client.post(sciezka, headers={"X-Cron-Secret": SEKRET + "x"})

    assert r.status_code == 401
    assert not szpieg.wywolana


def test_pusty_sekret_w_srodowisku_zamyka_endpoint(cron, monkeypatch):
    """NAJWAŻNIEJSZY: hmac.compare_digest("", "") == True.

    Gdyby zabrakło warunku `not expected`, deploy bez zmiennej CRON_SECRET
    otwierałby te endpointy dla każdego, kto wyśle pusty nagłówek.
    """
    sciezka, szpieg = cron
    monkeypatch.setenv("CRON_SECRET", "")

    r = client.post(sciezka, headers={"X-Cron-Secret": ""})

    assert r.status_code == 401
    assert not szpieg.wywolana


def test_brak_zmiennej_srodowiskowej_zamyka_endpoint(cron, monkeypatch):
    """Zmienna nieustawiona w ogóle — nie tylko pusta."""
    sciezka, szpieg = cron
    monkeypatch.delenv("CRON_SECRET", raising=False)

    r = client.post(sciezka, headers={"X-Cron-Secret": "cokolwiek"})

    assert r.status_code == 401
    assert not szpieg.wywolana


def test_poprawny_sekret_uruchamia_robote(cron):
    sciezka, szpieg = cron
    r = client.post(sciezka, headers={"X-Cron-Secret": SEKRET})

    assert r.status_code == 200, r.text
    assert szpieg.wywolana


# ── /cron/settle: cron rozlicza NA ŻYWO ─────────────────────────────────────

def test_cron_settle_nie_jest_dry_run(monkeypatch, czysty_cache):
    """Scheduler ma rozliczać naprawdę — dry_run tu byłoby cichą awarią."""
    szpieg = Szpieg({"settled": 1, "partial": 0, "errors": 0})
    monkeypatch.setattr(cs, "settle_active_coupons", szpieg)
    monkeypatch.setenv("CRON_SECRET", SEKRET)

    client.post("/api/cron/settle", headers={"X-Cron-Secret": SEKRET})

    assert szpieg.wywolania[0][1]["dry_run"] is False


def test_cron_settle_czysci_cache(monkeypatch):
    """Bez tego GUI pokazuje rozliczone kupony wciąż jako ACTIVE."""
    monkeypatch.setattr(cs, "settle_active_coupons", Szpieg({"settled": 1}))
    monkeypatch.setenv("CRON_SECRET", SEKRET)
    wyczyszczono = []
    monkeypatch.setattr(rc, "clear_response_cache", lambda: wyczyszczono.append(True))

    client.post("/api/cron/settle", headers={"X-Cron-Secret": SEKRET})

    assert wyczyszczono == [True]


def test_cron_settle_przekazuje_days_back(monkeypatch, czysty_cache):
    szpieg = Szpieg({"settled": 0})
    monkeypatch.setattr(cs, "settle_active_coupons", szpieg)
    monkeypatch.setenv("CRON_SECRET", SEKRET)

    client.post("/api/cron/settle?days_back=7", headers={"X-Cron-Secret": SEKRET})

    assert szpieg.wywolania[0][1]["days_back"] == 7


def test_cron_settle_blad_rozliczenia_to_500(monkeypatch, czysty_cache):
    """Błąd nie może przejść jako HTTP 200 — scheduler nie zauważyłby awarii."""
    def wybucha(*a, **kw):
        raise ValueError("brak wyników")

    monkeypatch.setattr(cs, "settle_active_coupons", wybucha)
    monkeypatch.setenv("CRON_SECRET", SEKRET)

    r = client.post("/api/cron/settle", headers={"X-Cron-Secret": SEKRET})

    assert r.status_code == 500


# ── /cron/settle-manual: kupony z dziennika ─────────────────────────────────

def test_cron_settle_manual_domyslnie_na_zywo(monkeypatch, czysty_cache):
    szpieg = Szpieg({"settled": 1, "skipped": 0, "errors": 0})
    monkeypatch.setattr(cs, "settle_manual_coupons", szpieg)
    monkeypatch.setenv("CRON_SECRET", SEKRET)

    client.post("/api/cron/settle-manual", headers={"X-Cron-Secret": SEKRET})

    assert szpieg.wywolania[0][1]["dry_run"] is False


def test_cron_settle_manual_respektuje_dry_run(monkeypatch, czysty_cache):
    szpieg = Szpieg({"settled": 0, "skipped": 2, "errors": 0})
    monkeypatch.setattr(cs, "settle_manual_coupons", szpieg)
    monkeypatch.setenv("CRON_SECRET", SEKRET)

    client.post("/api/cron/settle-manual?dry_run=true", headers={"X-Cron-Secret": SEKRET})

    assert szpieg.wywolania[0][1]["dry_run"] is True


# ── /cron/draft: dry-run to DOMYŚLNY tryb ───────────────────────────────────

def test_draft_domyslnie_dry_run(monkeypatch):
    """Wywołanie bez parametrów NIE MOŻE pisać do produkcji.

    Draft generuje kupony System paper-trading; live zbieranie danych to
    świadoma decyzja (`dry_run=false`), nie efekt uboczny pustego POST-a.
    """
    szpieg = Szpieg({"ok": True, "created": 0, "legs": []})
    monkeypatch.setattr(cd, "generuj_system_draft", szpieg)
    monkeypatch.setenv("CRON_SECRET", SEKRET)

    client.post("/api/cron/draft", headers={"X-Cron-Secret": SEKRET})

    assert szpieg.wywolania[0][1]["dry_run"] is True


def test_draft_live_wymaga_jawnego_wylaczenia(monkeypatch):
    szpieg = Szpieg({"ok": True, "created": 2, "legs": []})
    monkeypatch.setattr(cd, "generuj_system_draft", szpieg)
    monkeypatch.setenv("CRON_SECRET", SEKRET)

    client.post("/api/cron/draft?dry_run=false", headers={"X-Cron-Secret": SEKRET})

    assert szpieg.wywolania[0][1]["dry_run"] is False


def test_draft_nieudany_loguje_blad(monkeypatch, caplog):
    """REGRESJA: wszystko szło na INFO, więc {'ok': False} przy HTTP 200 nie
    rzucało się w oczy — System paper-trading stał 9 dni (20-29.07)."""
    monkeypatch.setattr(cd, "generuj_system_draft",
                        Szpieg({"ok": False, "error": "brak BZZOIRO_KEY", "legs": []}))
    monkeypatch.setenv("CRON_SECRET", SEKRET)

    with caplog.at_level(logging.INFO, logger="footstats.api.routes.coupons"):
        r = client.post("/api/cron/draft", headers={"X-Cron-Secret": SEKRET})

    assert r.status_code == 200
    poziomy = [x.levelno for x in caplog.records if "cron_draft" in x.getMessage()]
    assert logging.ERROR in poziomy, "nieudany draft nie trafił na poziom ERROR"


def test_draft_zero_kuponow_na_zywo_to_ostrzezenie(monkeypatch, caplog):
    """Zero kuponów live bywa normalne (off-season), ale utrzymujące się zero
    znaczy, że pętla zbierania danych nie żyje — musi być widoczne."""
    monkeypatch.setattr(cd, "generuj_system_draft", Szpieg({"ok": True, "created": 0, "legs": []}))
    monkeypatch.setenv("CRON_SECRET", SEKRET)

    with caplog.at_level(logging.INFO, logger="footstats.api.routes.coupons"):
        client.post("/api/cron/draft?dry_run=false", headers={"X-Cron-Secret": SEKRET})

    poziomy = [x.levelno for x in caplog.records if "cron_draft" in x.getMessage()]
    assert logging.WARNING in poziomy


def test_draft_nogi_nie_ida_do_logu_ale_wracaja_w_odpowiedzi(monkeypatch, caplog):
    """Log ma zostać czytelny; pełna lista nóg należy do odpowiedzi HTTP."""
    nogi = [{"home": "Legia", "away": "Lech", "tip": "1"}]
    monkeypatch.setattr(cd, "generuj_system_draft",
                        Szpieg({"ok": True, "created": 1, "legs": nogi}))
    monkeypatch.setenv("CRON_SECRET", SEKRET)

    with caplog.at_level(logging.INFO, logger="footstats.api.routes.coupons"):
        r = client.post("/api/cron/draft", headers={"X-Cron-Secret": SEKRET})

    assert r.json()["legs"] == nogi
    for zapis in caplog.records:
        assert "Legia" not in zapis.getMessage()


# ── /coupons/settle: rozliczanie cudzych kuponów = tylko admin ──────────────

@pytest.fixture
def settle_szpieg(monkeypatch):
    szpieg = Szpieg({"settled": 3, "partial": 1, "voided": 0, "errors": 0})
    monkeypatch.setattr(cs, "settle_active_coupons", szpieg)
    return szpieg


def test_settle_bez_tokenu_odrzucone(settle_szpieg):
    r = client.post("/api/coupons/settle", json={})

    assert r.status_code in (401, 403)
    assert not settle_szpieg.wywolana


def test_settle_zwyklym_userem_odrzucone(settle_szpieg):
    """REGRESJA: settle_active_coupons nie filtruje po user_id — każdy zalogowany
    mógł wymusić rozliczenie/VOID CUDZYCH kuponów (+ wektor DoS na FlashScore)."""
    token = _make_token("zwykly", 42, is_admin=False)
    r = client.post("/api/coupons/settle", json={},
                    headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 403
    assert not settle_szpieg.wywolana


def test_settle_podrobionym_tokenem_odrzucone(settle_szpieg):
    r = client.post("/api/coupons/settle", json={},
                    headers={"Authorization": "Bearer nie.jest.tokenem"})

    assert r.status_code == 401
    assert not settle_szpieg.wywolana


def test_settle_adminem_dziala(settle_szpieg):
    token = _make_token("admin", 1, is_admin=True)
    r = client.post("/api/coupons/settle", json={},
                    headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200, r.text
    dane = r.json()
    assert dane["settled"] == 3
    assert dane["partial"] == 1


def test_settle_przekazuje_parametry(settle_szpieg):
    token = _make_token("admin", 1, is_admin=True)
    client.post("/api/coupons/settle", json={"days_back": 10, "dry_run": True},
                headers={"Authorization": f"Bearer {token}"})

    kw = settle_szpieg.wywolania[0][1]
    assert kw["days_back"] == 10
    assert kw["dry_run"] is True


def test_settle_domyslnie_trzy_dni_wstecz(settle_szpieg):
    token = _make_token("admin", 1, is_admin=True)
    client.post("/api/coupons/settle", json={},
                headers={"Authorization": f"Bearer {token}"})

    assert settle_szpieg.wywolania[0][1]["days_back"] == 3
