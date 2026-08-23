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


def _czlon(polityka: str, nazwa: str) -> str:
    return next(c.strip() for c in polityka.split(";")
                if c.strip().split(" ")[0] == nazwa)


def test_style_inline_dozwolone_swiadomie(klient: TestClient):
    """Kompromis opisany w nagłówku pliku — front używa atrybutów `style={{...}}`
    (zmierzone: **79 wystąpień w 8 plikach**, nie 3 jak twierdziło F9).
    Ten człon jest ZAPASOWY dla Firefoksa, który nie zna `style-src-elem/attr`."""
    czlon = _czlon(_csp(klient.get("/health")), "style-src")

    assert "'unsafe-inline'" in czlon, (
        "style-src bez 'unsafe-inline' — Firefox spada wlasnie na ten czlon "
        "i front straci tam kolory"
    )


def test_wstrzykniety_element_style_zablokowany(klient: TestClient):
    """Zysk osiągalny BEZ ruszania 79 stylów inline: `<style>` wstrzyknięty przez
    XSS jest blokowany, bo `style-src-elem` nie ma `'unsafe-inline'`. Sprawdzone,
    że nic w `gui/src` nie tworzy elementu `<style>` w czasie działania."""
    czlon = _czlon(_csp(klient.get("/health")), "style-src-elem")

    assert "'unsafe-inline'" not in czlon, f"style-src-elem rozluzniony: {czlon}"
    assert "'self'" in czlon


def test_atrybuty_style_dalej_dzialaja(klient: TestClient):
    """Bez tego React traci kolory w Chrome i Safari — a `style-src-attr` jest
    bardziej szczegółowy niż `style-src`, więc BIJE go tam, gdzie jest znany."""
    czlon = _czlon(_csp(klient.get("/health")), "style-src-attr")

    assert "'unsafe-inline'" in czlon


# ── strony statyczne muszą przeżyć zacisk ───────────────────────────────────

@pytest.mark.parametrize("plik", [
    "polityka_prywatnosci.html", "regulamin.html", "preview.html",
])
def test_strony_statyczne_bez_blokow_style(plik: str):
    """`style-src-elem 'self'` blokuje KAŻDY blok `<style>`, także nasz własny.

    Zmierzone 23.08 przy zaciskaniu: `/polityka-prywatnosci` traciła cały wygląd,
    font spadał z `ui-sans-serif` na `Times New Roman`. Style mieszkają teraz
    w `static/*.css`. Ten test istnieje, bo regresja byłaby CICHA — strona dalej
    zwraca 200, tylko wygląda jak dokument z lat 90.
    """
    from pathlib import Path

    sciezka = Path(__file__).resolve().parents[1] / "src" / "footstats" / "api" / plik
    if not sciezka.exists():
        pytest.skip(f"brak {plik}")

    tresc = sciezka.read_text(encoding="utf-8")

    assert "<style" not in tresc.lower(), (
        f"{plik} ma blok <style> — CSP go zablokuje i strona straci wyglad. "
        "Przenies styl do src/footstats/api/static/"
    )
    assert "/static/" in tresc, f"{plik} nie linkuje zadnego arkusza z /static/"


def test_arkusze_statyczne_istnieja():
    """Link do nieistniejącego arkusza to ta sama cicha regresja, tylko z 404."""
    from pathlib import Path

    statyczne = Path(__file__).resolve().parents[1] / "src" / "footstats" / "api" / "static"

    assert (statyczne / "legal.css").exists()
    assert (statyczne / "preview.css").exists()


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
