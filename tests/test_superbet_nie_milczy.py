"""J1 w scraperze Superbet: logowanie miało dziurę, przez którą szło dalej
z pustym hasłem.

`zaloguj()` składa się z pięciu pętli „próbuj selektory po kolei". Cisza WEWNĄTRZ
takiej pętli jest poprawna — nietrafiony selektor to stan normalny, a log przy
każdej próbie dawałby kilkanaście linii szumu na jedno logowanie. Głośny musi być
WYNIK pętli, i tego brakowało w trzech z pięciu:

  * pole hasła      — gdy żaden selektor nie zadziałał, kod **klikał submit
                      z pustym polem**; logowanie kończyło się porażką
                      „z nieznanego powodu";
  * przycisk submit — formularz wypełniony, ale nigdy niewysłany;
  * przycisk logowania — modal nieotwarty.

Osobno: `zalogowany = False` logowało się na INFO i szło dalej. Idziemy wtedy
dalej NIEZALOGOWANI, więc wszystko poniżej widzi treść publiczną i zwraca mniej
danych, wyglądając na sukces — to WARNING, nie INFO.

Testy chodzą po atrapie strony, bez przeglądarki: `zaloguj(page)` przyjmuje samo
`page`, a `_parsuj_element_kuponu` i `_parsuj_fallback` wołają tylko `inner_text`.
"""
from __future__ import annotations

import logging

import pytest

from footstats.scrapers import superbet as sb
from footstats.scrapers.base_playwright import PWError, PWTimeout


# Selektory są zdefiniowane WEWNĄTRZ `zaloguj`, więc nie da się ich zaimportować.
# Powtarzam tu tylko te, których potrzebuję, i pilnuję tego testem niżej.
SEL_MODAL   = "[data-cy='login-button']"          # tylko na liscie otwierajacej modal
SEL_FORM    = ("input[name='username'], input[id*='username'], "
               "input[placeholder*='użytkownika'], input[placeholder*='mail'], "
               "input[type='email'], input[type='password']")
SEL_EMAIL   = "input[name='username']"
SEL_HASLO   = "input[type='password']"
SEL_SUBMIT  = "button[type='submit']"
SEL_ZALOG   = "span:has-text('PLN')"


class _Strona:
    """Atrapa `page`. Dopasowanie DOKŁADNE, nie po fragmencie.

    Pierwsza wersja dopasowywała podciągiem i test na brak submitu przechodził
    fałszywie: `"button:has-text('Zaloguj')"` figuruje DOSŁOWNIE na obu listach —
    otwierającej modal i zatwierdzającej formularz. Włączenie jednej włączało drugą.
    """

    def __init__(self, dziala=(), widoczne=True):
        self.dziala = set(dziala)
        self.widoczne = widoczne
        self.wypelnione: dict[str, str] = {}
        self.klikniete: list[str] = []
        self.screenshoty: list[str] = []

    def _ok(self, sel: str) -> bool:
        return sel in self.dziala

    # ── API używane przez `zaloguj` ──────────────────────────────────────
    def goto(self, *a, **k): return None
    def screenshot(self, path="", **k): self.screenshoty.append(path)
    def evaluate(self, *a, **k): return []

    def wait_for_selector(self, sel, timeout=0):
        if not self._ok(sel):
            raise PWTimeout(f"brak {sel}")
        return object()

    def click(self, sel, **k):
        if not self._ok(sel):
            raise PWError(f"brak {sel}")
        self.klikniete.append(sel)

    def fill(self, sel, wartosc, timeout=0):
        if not self._ok(sel):
            raise PWError(f"brak {sel}")
        self.wypelnione[sel] = wartosc

    def query_selector(self, sel):
        if not self._ok(sel):
            return None
        strona, nazwa = self, sel

        class _El:
            def is_visible(_s): return strona.widoczne
            def click(_s): strona.klikniete.append(nazwa)
        return _El()


def test_selektory_w_tescie_zgadzaja_sie_z_produkcja():
    """Stałe wyżej są KOPIĄ — bez tej kotwicy zmiana selektora w `zaloguj`
    zostawiłaby testy zielone nad martwą atrapą."""
    import inspect

    zrodlo = inspect.getsource(sb.zaloguj)
    for sel in (SEL_MODAL, SEL_EMAIL, SEL_HASLO, SEL_SUBMIT, SEL_ZALOG):
        assert sel in zrodlo, f"selektor {sel!r} zniknal z `zaloguj` — atrapa klamie"


@pytest.fixture(autouse=True)
def _dane_logowania(monkeypatch):
    monkeypatch.setenv("SUPERBET_LOGIN", "user@example.com")
    monkeypatch.setenv("SUPERBET_PASSWORD", "tajne")
    monkeypatch.setattr(sb.time, "sleep", lambda *_: None)
    monkeypatch.setattr(sb, "_akceptuj_cookies", lambda *_: None)


# ── dziura, przez którą szło puste hasło ────────────────────────────────────

def test_brak_pola_hasla_przerywa_zamiast_wysylac_pusty_formularz(caplog):
    """SEDNO. Do 29.08 kod leciał dalej i klikał submit — formularz szedł
    z pustym hasłem, a przyczyna porażki nie była nigdzie zapisana."""
    page = _Strona(dziala=(SEL_MODAL, SEL_FORM, SEL_EMAIL, SEL_SUBMIT))

    with caplog.at_level(logging.WARNING):
        assert sb.zaloguj(page) is False

    assert "nie znaleziono pola hasla" in caplog.text.lower()
    assert not page.klikniete or all("submit" not in k for k in page.klikniete), (
        "formularz zostal WYSLANY mimo braku hasla"
    )


def test_brak_przycisku_submit_jest_bledem_a_nie_cisza(caplog):
    """Formularz wypełniony, ale nigdy niewysłany — bez logu wygląda to
    identycznie jak złe hasło."""
    page = _Strona(dziala=(SEL_MODAL, SEL_FORM, SEL_EMAIL, SEL_HASLO))

    with caplog.at_level(logging.WARNING):
        assert sb.zaloguj(page) is False

    assert "nie wyslany" in caplog.text.lower()


def test_niepotwierdzone_logowanie_to_WARNING_nie_INFO(caplog):
    """Idziemy dalej NIEZALOGOWANI. Na INFO ta linia ginie, a wszystko poniżej
    zwraca niepełne dane wyglądające na sukces."""
    page = _Strona(dziala=(SEL_MODAL, SEL_FORM, SEL_EMAIL, SEL_HASLO, SEL_SUBMIT))

    with caplog.at_level(logging.WARNING):
        assert sb.zaloguj(page) is True

    assert "NIEZALOGOWANY" in caplog.text


def test_pelna_sciezka_logowania_nie_generuje_ostrzezen(caplog):
    """Kontrola: gdy wszystkie selektory działają, nie ma prawa paść ani jedno
    ostrzeżenie — inaczej te wyżej przestaną cokolwiek znaczyć."""
    page = _Strona(dziala=(SEL_MODAL, SEL_FORM, SEL_EMAIL, SEL_HASLO,
                           SEL_SUBMIT, SEL_ZALOG))

    with caplog.at_level(logging.WARNING):
        assert sb.zaloguj(page) is True

    assert caplog.text == ""
    assert page.wypelnione, "haslo i login mialy zostac wpisane"


# ── utrata danych przy parsowaniu ───────────────────────────────────────────

class _Element:
    def __init__(self, tekst): self._t = tekst
    def inner_text(self): return self._t


def test_kupon_bez_kursu_i_stawki_nie_halasuje(caplog):
    """Skan po liniach kuponu ma prawo nie trafić — to nie jest awaria."""
    el = _Element("Typer XYZ\nMecz A - B\njakis tekst\ninny tekst\nkolejna linia")

    with caplog.at_level(logging.WARNING):
        sb._parsuj_element_kuponu(el, "nick")

    assert caplog.text == ""


def test_fallback_ktory_padl_mowi_ze_profil_przepadl(caplog):
    """`return None` znaczyło tu: z tego profilu nie będzie ŻADNEGO kuponu."""
    class _ZlaStrona:
        def inner_text(self, _sel):
            raise AttributeError("brak body")

    with caplog.at_level(logging.WARNING):
        assert sb._parsuj_fallback(_ZlaStrona(), "nick", "http://x") is None

    assert "ZADNEGO kuponu" in caplog.text
    assert "nick" in caplog.text
