"""B5 — brakowało Content-Security-Policy. Reszta nagłówków była od dawna.

API serwuje NIE TYLKO JSON: `Dockerfile.api` buduje front (stage `gui-build`)
i kopiuje `gui/dist`, więc Cloud Run oddaje żywy SPA na `/`, `/app` i `/preview`,
do tego `/polityka-prywatnosci`, `/manifest.json` i `/sw.js`. CSP dotyczy więc
prawdziwych stron, a nie samych odpowiedzi JSON.

DECYZJA 1 — DOMYŚLNIE `Report-Only`, wymuszanie za flagą `CSP_ENFORCE=1`.
CSP, która psuje GUI, jest gorsza od jej braku: użytkownik widzi białą stronę,
a przyczyna siedzi w nagłówku, nie w kodzie. Nie mamy jeszcze ANI JEDNEGO pomiaru
naruszeń, więc wymuszanie od razu byłoby zgadywaniem. `Report-Only` zbiera dowody,
flaga pozwala przełączyć bez wdrożenia nowego obrazu.

DECYZJA 2 — `style-src` dopuszcza `'unsafe-inline'`. To ŚWIADOMY kompromis, nie
przeoczenie: front używa atrybutów `style={{...}}` (`HistoryCouponRow`, `StatsView`,
`ProgressChart` — to samo miejsce, które opisuje F9). Bez `'unsafe-inline'` te
komponenty tracą kolory. Sprzątnięcie F9 pozwoli ten człon usunąć — i wtedy CSP
realnie zacznie bronić przed wstrzyknięciem stylu, bo dziś ten człon to dziura.

DECYZJA 3 — Google Fonts wpisane jawnie. `gui/src/index.css` zaczyna się od
`@import url('https://fonts.googleapis.com/...')`, a fonty ciągną się z
`fonts.gstatic.com`. To JEDYNE zewnętrzne pochodzenie w zbudowanym pakiecie
(sprawdzone w `dist/assets/*.js`: absolutne adresy to wyłącznie linki w treści
komunikatów błędów Reacta/Reduksa, nic się z nich nie ładuje).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def klient() -> TestClient:
    from footstats.api.main import app

    return TestClient(app, raise_server_exceptions=False)


def _csp(odpowiedz) -> str:
    return (odpowiedz.headers.get("content-security-policy-report-only")
            or odpowiedz.headers.get("content-security-policy")
            or "")


# ── nagłówek w ogóle jest ────────────────────────────────────────────────────

def test_csp_obecne_na_zdrowiu(klient: TestClient):
    assert _csp(klient.get("/health")), "brak naglowka CSP"


def test_domyslnie_tryb_report_only(klient: TestClient):
    """Wymuszanie bez ani jednego pomiaru naruszen byloby zgadywaniem."""
    r = klient.get("/health")

    assert "content-security-policy-report-only" in r.headers
    assert "content-security-policy" not in r.headers, (
        "CSP wymuszane domyslnie — biala strona u uzytkownika przy pierwszym bledzie"
    )


# ── treść polityki ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("dyrektywa,wartosc", [
    ("default-src", "'self'"),
    ("object-src", "'none'"),
    ("base-uri", "'none'"),
    ("frame-ancestors", "'none'"),
    ("form-action", "'self'"),
])
def test_dyrektywy_domykajace(klient: TestClient, dyrektywa: str, wartosc: str):
    polityka = _csp(klient.get("/health"))

    assert f"{dyrektywa} {wartosc}" in polityka, (
        f"brak `{dyrektywa} {wartosc}` w: {polityka}"
    )


def test_skrypty_tylko_z_wlasnego_zrodla(klient: TestClient):
    """Sedno CSP. `'unsafe-inline'` w script-src kasowalby cala ochrone przed XSS,
    a zbudowany pakiet nie ma ANI JEDNEGO skryptu inline (sprawdzone w dist)."""
    polityka = _csp(klient.get("/health"))
    czlon = next(c.strip() for c in polityka.split(";") if c.strip().startswith("script-src"))

    assert "'unsafe-inline'" not in czlon, f"script-src z 'unsafe-inline': {czlon}"
    assert "'unsafe-eval'" not in czlon, f"script-src z 'unsafe-eval': {czlon}"


def test_fonty_google_dozwolone(klient: TestClient):
    """`gui/src/index.css` robi `@import` z fonts.googleapis.com — bez tego wpisu
    front traci kroje pisma zaraz po wymuszeniu polityki."""
    polityka = _csp(klient.get("/health"))

    assert "fonts.googleapis.com" in polityka
    assert "fonts.gstatic.com" in polityka


def test_style_inline_dozwolone_swiadomie(klient: TestClient):
    """Kompromis opisany w nagłówku pliku — front używa atrybutów `style={{...}}`.
    Test istnieje po to, żeby usunięcie tego członu było DECYZJĄ, a nie wypadkiem:
    gdy F9 posprząta style inline, ten test ma spaść i przypomnieć o zaostrzeniu."""
    polityka = _csp(klient.get("/health"))
    czlon = next(c.strip() for c in polityka.split(";") if c.strip().startswith("style-src"))

    assert "'unsafe-inline'" in czlon, (
        "style-src bez 'unsafe-inline' — jesli F9 posprzatal style inline, USUN ten "
        "test i zaostrz polityke; jesli nie, front wlasnie stracil kolory"
    )


# ── przełącznik na wymuszanie ────────────────────────────────────────────────

def test_flaga_przelacza_na_wymuszanie(monkeypatch):
    """Flip ma nie wymagać nowego obrazu — inaczej wycofanie złej polityki trwa
    tyle, co wdrożenie, a to jest właśnie moment, w którym GUI leży."""
    from footstats.api import main as _main

    monkeypatch.setattr(_main, "_CSP_ENFORCE", True)
    with TestClient(_main.app, raise_server_exceptions=False) as k:
        r = k.get("/health")

    assert "content-security-policy" in r.headers
    assert "content-security-policy-report-only" not in r.headers


def test_polityka_identyczna_w_obu_trybach(monkeypatch):
    """Gdyby tryby różniły się treścią, raporty z `Report-Only` nie mówiłyby nic
    o tym, co stanie się po wymuszeniu."""
    from footstats.api import main as _main

    with TestClient(_main.app, raise_server_exceptions=False) as k:
        raport = _csp(k.get("/health"))

    monkeypatch.setattr(_main, "_CSP_ENFORCE", True)
    with TestClient(_main.app, raise_server_exceptions=False) as k:
        wymuszone = _csp(k.get("/health"))

    assert raport == wymuszone


# ── nie psujemy tego, co już działało ───────────────────────────────────────

@pytest.mark.parametrize("naglowek", [
    "x-content-type-options", "x-frame-options",
    "referrer-policy", "strict-transport-security",
])
def test_stare_naglowki_zostaja(klient: TestClient, naglowek: str):
    assert naglowek in klient.get("/health").headers
