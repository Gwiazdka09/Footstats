"""test_ai_trainer.py — lekcje historyczne i blok kalibracji do promptu.

PO CO: modul mial 24%. `get_kalibracja_inject()` wstrzykuje tekst WPROST
do promptu Groqa (wolane z `analyzer._get_kalibracja_blok`). Jego komentarz
w kodzie opisuje realna awarie: format `:+d` wywalal ValueError przy
korekcie float i "crashowal CALY Groq -> 0 predykcji/kuponow, run padal
w KROK 3". Naprawa nie miala testu, wiec nic nie chronilo przed powrotem.

`ask_groq_trainer` ma dwie sciezki (SDK i surowe HTTP) i obie musza odsiac
markdown, ktorym Groq lubi opakowac JSON.
"""
from __future__ import annotations


import pytest

import footstats.ai.trainer as tr


@pytest.fixture(autouse=True)
def plik_lekcji(tmp_path, monkeypatch):
    """LESSONS_FILE na tmp — testy nie dotykaja data/groq_lessons.json."""
    sciezka = tmp_path / "lekcje" / "groq_lessons.json"
    monkeypatch.setattr(tr, "LESSONS_FILE", sciezka)
    return sciezka


# ── load_lessons / save_lessons ─────────────────────────────────────────────

def test_brak_pliku_daje_pusty_slownik():
    assert tr.load_lessons() == {}


def test_zapis_i_odczyt_w_obie_strony(plik_lekcji, capsys):
    tr.save_lessons({"n_matches": 32400, "groq_lessons": {"marchewki": []}})
    assert plik_lekcji.exists()
    assert tr.load_lessons()["n_matches"] == 32400
    assert "Zapisano lekcje" in capsys.readouterr().out


def test_zapis_tworzy_brakujacy_katalog(plik_lekcji):
    assert not plik_lekcji.parent.exists()
    tr.save_lessons({"x": 1})
    assert plik_lekcji.parent.exists()


def test_uszkodzony_plik_daje_pusty_slownik(plik_lekcji):
    """Zepsuty JSON nie moze wywalic calego analyzera przy starcie."""
    plik_lekcji.parent.mkdir(parents=True)
    plik_lekcji.write_text("{niepoprawny", encoding="utf-8")
    assert tr.load_lessons() == {}


def test_polskie_znaki_zapisywane_czytelnie(plik_lekcji):
    tr.save_lessons({"uwaga": "przewaga gospodarza rośnie"})
    assert "rośnie" in plik_lekcji.read_text(encoding="utf-8")


# ── get_kalibracja_inject ───────────────────────────────────────────────────

def _lekcje(**groq) -> dict:
    return {"updated_at": "2026-07-15T12:00:00", "n_matches": 32400,
            "groq_lessons": groq}


def test_brak_summary_daje_pusty_blok(plik_lekcji):
    tr.save_lessons(_lekcje())
    assert tr.get_kalibracja_inject() == ""


def test_blok_ma_date_liczbe_meczow_i_summary(plik_lekcji):
    tr.save_lessons(_lekcje(kalibracja_summary="Obniż pewność Over o 5pp."))
    blok = tr.get_kalibracja_inject()

    assert "KALIBRACJA HISTORYCZNA (2026-07-15" in blok
    assert "n=32,400" in blok
    assert "Obniż pewność Over o 5pp." in blok


def test_korekty_per_rynek_dopisane(plik_lekcji):
    tr.save_lessons(_lekcje(
        kalibracja_summary="x",
        kalibracja_per_rynek={"Over2.5": {"korekta_pewnosci": -5},
                              "BTTS": {"korekta_pewnosci": 3}},
    ))
    blok = tr.get_kalibracja_inject()
    assert "Over2.5:-5%" in blok
    assert "BTTS:+3%" in blok


def test_korekta_zero_pomijana(plik_lekcji):
    """Zerowa korekta to szum — nie zasmieca promptu."""
    tr.save_lessons(_lekcje(
        kalibracja_summary="x",
        kalibracja_per_rynek={"1X2": {"korekta_pewnosci": 0}},
    ))
    assert "Korekty:" not in tr.get_kalibracja_inject()


def test_korekta_float_nie_wywala_bloku(plik_lekcji):
    """REGRESJA: `:+d` na floacie rzucal ValueError i zabijal caly krok Groq.

    Komentarz w kodzie opisuje ten incydent — ten test go pilnuje.
    """
    tr.save_lessons(_lekcje(
        kalibracja_summary="x",
        kalibracja_per_rynek={"Over2.5": {"korekta_pewnosci": -4.7}},
    ))
    blok = tr.get_kalibracja_inject()          # nie rzuca
    assert "Over2.5:-5%" in blok               # zaokraglone przez :+.0f


def test_brak_pliku_lekcji_daje_pusty_blok():
    assert tr.get_kalibracja_inject() == ""


# ── _print_lessons ──────────────────────────────────────────────────────────

def test_drukuje_marchewki(capsys):
    tr._print_lessons({"marchewki": [
        {"sila": "wysoka", "regula": "Over 2.5 w Bundeslidze",
         "uzasadnienie": "58% trafien", "rynki": ["Over2.5", "BTTS"]},
    ]})
    out = capsys.readouterr().out
    assert "MARCHEWKI (1)" in out
    assert "[WYSOKA]" in out
    assert "Over 2.5 w Bundeslidze" in out
    assert "Over2.5, BTTS" in out


def test_drukuje_kije(capsys):
    tr._print_lessons({"kije": [
        {"mit": "faworyt zawsze wygrywa", "dowod": "44% w POL", "uwaga": "sprawdzaj formę"},
    ]})
    out = capsys.readouterr().out
    assert "KIJE (1)" in out
    assert "faworyt zawsze wygrywa" in out
    assert "sprawdzaj formę" in out


def test_drukuje_nowe_zasady_i_summary(capsys):
    tr._print_lessons({"nowe_zasady_kuponow": ["max 4 nogi"],
                       "kalibracja_summary": "obniż Over o 5pp"})
    out = capsys.readouterr().out
    assert "max 4 nogi" in out
    assert "obniż Over o 5pp" in out


def test_puste_lekcje_nie_wywalaja_druku(capsys):
    tr._print_lessons({})
    assert "WYNIKI TRENINGU" in capsys.readouterr().out


def test_kalibracja_int_drukowana_bez_podwojnego_znaku(capsys):
    """Regresja formatowania: `{sign}{kor:+d}` dawalo '++5%'."""
    tr._print_lessons({"kalibracja_per_rynek": {
        "Over2.5": {"korekta_pewnosci": 5, "komentarz": "za wysoko"},
    }})
    out = capsys.readouterr().out
    assert "++" not in out, "podwójny znak w korekcie"
    assert "+5%" in out


def test_kalibracja_float_nie_wywala_druku(capsys):
    """Ta sama klasa bledu co w get_kalibracja_inject — `:+d` nie przyjmuje floata."""
    tr._print_lessons({"kalibracja_per_rynek": {
        "Over2.5": {"korekta_pewnosci": -4.7, "komentarz": "koryguj"},
    }})
    assert "Over2.5" in capsys.readouterr().out


# ── ask_groq_trainer ────────────────────────────────────────────────────────

@pytest.fixture
def bez_sdk(monkeypatch):
    """Wymusza sciezke surowego HTTP (SDK niedostepne)."""
    monkeypatch.setattr(tr, "_HAS_GROQ_SDK", False)


class _Odp:
    def __init__(self, tresc: str, status: int = 200):
        self._tresc = tresc
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError(f"HTTP {self.status_code}")

    def json(self):
        return {"choices": [{"message": {"content": self._tresc}}]}


def test_http_zwraca_sparsowany_json(bez_sdk, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Odp('{"marchewki": []}'))

    assert tr.ask_groq_trainer("raport", 100) == {"marchewki": []}


def test_http_odsiewa_blok_markdown_json(bez_sdk, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    import requests
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: _Odp('```json\n{"kije": [1]}\n```'))

    assert tr.ask_groq_trainer("raport", 100) == {"kije": [1]}


def test_http_odsiewa_goly_blok_kodu(bez_sdk, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Odp('```\n{"x": 1}\n```'))

    assert tr.ask_groq_trainer("raport", 100) == {"x": 1}


def test_brak_klucza_zwraca_none(bez_sdk, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    assert tr.ask_groq_trainer("raport", 100) is None


def test_niepoprawny_json_zwraca_none(bez_sdk, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Odp("to nie jest JSON"))

    assert tr.ask_groq_trainer("raport", 100) is None


def test_blad_http_zwraca_none(bez_sdk, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    import requests

    def _padnij(*a, **k):
        raise OSError("brak sieci")

    monkeypatch.setattr(requests, "post", _padnij)
    assert tr.ask_groq_trainer("raport", 100) is None


def test_sdk_zwraca_sparsowany_json(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(tr, "_HAS_GROQ_SDK", True)

    class _Msg:
        content = '  {"marchewki": ["a"]}  '

    class _Wybor:
        message = _Msg()

    class _Resp:
        choices = [_Wybor()]

    class _SDK:
        def __init__(self, api_key=None):
            self.chat = self

        @property
        def completions(self):
            return self

        def create(self, **kw):
            return _Resp()

    monkeypatch.setattr(tr, "_GroqSDK", _SDK)
    assert tr.ask_groq_trainer("raport", 100) == {"marchewki": ["a"]}


def test_sdk_blad_zwraca_none_zamiast_wysypki(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(tr, "_HAS_GROQ_SDK", True)

    class _SDK:
        def __init__(self, api_key=None):
            raise RuntimeError("SDK padl")

    monkeypatch.setattr(tr, "_GroqSDK", _SDK)
    with pytest.raises(RuntimeError):
        tr.ask_groq_trainer("raport", 100)
