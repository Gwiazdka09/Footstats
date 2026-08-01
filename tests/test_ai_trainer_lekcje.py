"""test_ai_trainer_lekcje.py — pętla uczenia: lekcje z historii do promptu Groq.

PO CO: trainer zamienia wyniki historyczne na „lekcje", które wracają do promptu
przy każdej kolejnej predykcji. Awaria tutaj nie wywala predykcji — po prostu
model przestaje się uczyć i nikt tego nie widzi.

Jedna rzecz ma tu historię: `korekta_pewnosci` bywa floatem, bo tak zwraca ją
Groq. Formatowanie przez `:+d` rzucało wtedy `ValueError` i wywalało CAŁY krok
Groq — run kończył się zerem predykcji i kuponów. Poprawka to `:+.0f`, które
działa dla int i float. Ręcznego znaku nie ma, bo `:+` sam go dokleja —
wcześniejsza wersja dawała „++5%".

`load_lessons` musi być całkowite: uszkodzony plik lekcji ma dać pusty słownik,
a nie zatrzymać predykcję. Lekcje to wzbogacenie, nie warunek działania.
"""
from __future__ import annotations


import pytest

import footstats.ai.trainer as tr


@pytest.fixture(autouse=True)
def plik_lekcji(tmp_path, monkeypatch):
    """Przekierowuje plik lekcji na tmp — testy nie ruszają prawdziwego."""
    p = tmp_path / "lessons.json"
    monkeypatch.setattr(tr, "LESSONS_FILE", p)
    return p


# ── load_lessons / save_lessons ────────────────────────────────────────────

def test_brak_pliku_to_pusty_slownik():
    """Pierwsze uruchomienie nie ma jeszcze czego wczytać."""
    assert tr.load_lessons() == {}


@pytest.mark.parametrize("smiec", ["{niedomkniety", "", "nie-json"])
def test_uszkodzony_plik_to_pusty_slownik(plik_lekcji, smiec):
    """Lekcje to wzbogacenie, nie warunek działania — awaria nie może
    zatrzymać predykcji."""
    plik_lekcji.write_text(smiec, encoding="utf-8")

    assert tr.load_lessons() == {}


def test_zapis_i_odczyt_w_obie_strony(plik_lekcji, capsys):
    tr.save_lessons({"n_matches": 500, "groq_lessons": {"kalibracja_summary": "blok"}})

    assert tr.load_lessons()["n_matches"] == 500


def test_zapis_tworzy_katalog(tmp_path, monkeypatch, capsys):
    """Pierwszy zapis na czystej maszynie nie może paść na braku katalogu."""
    monkeypatch.setattr(tr, "LESSONS_FILE", tmp_path / "glebiej" / "lessons.json")

    tr.save_lessons({"x": 1})

    assert (tmp_path / "glebiej" / "lessons.json").exists()


def test_polskie_znaki_zapisane_czytelnie(plik_lekcji, capsys):
    """Lekcje są czytane przez człowieka i wstrzykiwane do promptu."""
    tr.save_lessons({"uwaga": "Gospodarze wygrywają częściej"})

    assert "wygrywają" in plik_lekcji.read_text(encoding="utf-8")


# ── get_kalibracja_inject: blok wstrzykiwany do promptu ────────────────────

def _lekcje(**nadpisz) -> dict:
    d = {
        "updated_at": "2026-07-15T10:00:00Z",
        "n_matches": 12345,
        "groq_lessons": {
            "kalibracja_summary": "Over 2.5 przeszacowany o 6pp",
            "kalibracja_per_rynek": {},
        },
    }
    d.update(nadpisz)
    return d


def test_brak_lekcji_to_pusty_blok():
    """Bez treningu prompt ma zostać nietknięty, a nie dostać pusty nagłówek."""
    assert tr.get_kalibracja_inject() == ""


def test_brak_podsumowania_to_pusty_blok(plik_lekcji, capsys):
    tr.save_lessons({"groq_lessons": {"kalibracja_summary": ""}})

    assert tr.get_kalibracja_inject() == ""


def test_blok_zawiera_podsumowanie(plik_lekcji, capsys):
    tr.save_lessons(_lekcje())

    assert "Over 2.5 przeszacowany o 6pp" in tr.get_kalibracja_inject()


def test_blok_podaje_date_i_liczbe_meczow(plik_lekcji, capsys):
    """Lekcja z 12 meczów znaczy co innego niż z 12 tysięcy — model musi wiedzieć."""
    tr.save_lessons(_lekcje())

    blok = tr.get_kalibracja_inject()

    assert "2026-07-15" in blok
    assert "12,345" in blok


def test_korekta_float_nie_wywala_bloku(plik_lekcji, capsys):
    """REGRESJA: `:+d` na floacie rzucało ValueError i wywalało CAŁY krok Groq —
    run kończył się zerem predykcji i kuponów."""
    tr.save_lessons(_lekcje(groq_lessons={
        "kalibracja_summary": "blok",
        "kalibracja_per_rynek": {"Over 2.5": {"korekta_pewnosci": -7.5}},
    }))

    blok = tr.get_kalibracja_inject()

    assert "Over 2.5" in blok


def test_korekta_ma_pojedynczy_znak(plik_lekcji, capsys):
    """`:+` sam dokleja znak — ręczne dodanie dawało "++5%"."""
    tr.save_lessons(_lekcje(groq_lessons={
        "kalibracja_summary": "blok",
        "kalibracja_per_rynek": {"BTTS": {"korekta_pewnosci": 5}},
    }))

    blok = tr.get_kalibracja_inject()

    assert "++" not in blok
    assert "+5%" in blok


def test_korekta_ujemna_zachowuje_minus(plik_lekcji, capsys):
    tr.save_lessons(_lekcje(groq_lessons={
        "kalibracja_summary": "blok",
        "kalibracja_per_rynek": {"Over 2.5": {"korekta_pewnosci": -8}},
    }))

    assert "-8%" in tr.get_kalibracja_inject()


def test_zerowa_korekta_pomijana(plik_lekcji, capsys):
    """Rynek bez korekty to szum w prompcie, nie informacja."""
    tr.save_lessons(_lekcje(groq_lessons={
        "kalibracja_summary": "blok",
        "kalibracja_per_rynek": {"BTTS": {"korekta_pewnosci": 0}},
    }))

    assert "BTTS" not in tr.get_kalibracja_inject()


# ── _print_lessons: podgląd `--show` ───────────────────────────────────────

def test_podglad_pustych_lekcji_nie_wywala(capsys):
    tr._print_lessons({})

    assert "WYNIKI TRENINGU" in capsys.readouterr().out


def test_podglad_pokazuje_marchewki(capsys):
    tr._print_lessons({"marchewki": [
        {"sila": "wysoka", "regula": "Gospodarz faworyt", "uzasadnienie": "62% trafien",
         "rynki": ["1X2", "Over 2.5"]}]})

    out = capsys.readouterr().out
    assert "WYSOKA" in out
    assert "Gospodarz faworyt" in out
    assert "1X2, Over 2.5" in out


def test_podglad_pokazuje_kije(capsys):
    tr._print_lessons({"kije": [
        {"mit": "Beniaminek zawsze przegrywa", "dowod": "38% wygranych",
         "uwaga": "Sprawdzaj forme"}]})

    out = capsys.readouterr().out
    assert "Beniaminek zawsze przegrywa" in out
    assert "38% wygranych" in out


def test_podglad_korekty_float_nie_wywala(capsys):
    """REGRESJA: ten sam `:+d` co w get_kalibracja_inject, ale w `--show`.
    Naprawiono tam wcześniej, tutaj bug został i wysypywał podgląd."""
    tr._print_lessons({"kalibracja_per_rynek": {
        "Over 2.5": {"korekta_pewnosci": -7.5, "komentarz": "przeszacowany"}}})

    assert "-8%" in capsys.readouterr().out or "-7%" in capsys.readouterr().out


def test_podglad_korekty_ma_pojedynczy_znak(capsys):
    tr._print_lessons({"kalibracja_per_rynek": {"BTTS": {"korekta_pewnosci": 5}}})

    assert "++" not in capsys.readouterr().out


def test_podglad_pokazuje_nowe_zasady(capsys):
    tr._print_lessons({"nowe_zasady_kuponow": ["Maks 3 nogi", "Kotwica ponizej 1.35"]})

    out = capsys.readouterr().out
    assert "Maks 3 nogi" in out
    assert "Kotwica ponizej 1.35" in out


def test_podglad_pokazuje_blok_promptu(capsys):
    tr._print_lessons({"kalibracja_summary": "Over 2.5 przeszacowany"})

    assert "Over 2.5 przeszacowany" in capsys.readouterr().out


def test_podglad_braku_pola_nie_wywala(capsys):
    """Groq bywa niekompletny — brak pola nie może wysypać podglądu."""
    tr._print_lessons({"marchewki": [{}], "kije": [{}]})

    assert "WYNIKI TRENINGU" in capsys.readouterr().out


# ── ask_groq_trainer: parsowanie odpowiedzi ────────────────────────────────

def test_brak_klucza_to_none(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setattr(tr, "_HAS_GROQ_SDK", False)

    assert tr.ask_groq_trainer("raport", 100) is None


class _Msg:
    def __init__(self, tresc):
        self.content = tresc


class _Wybor:
    def __init__(self, tresc):
        self.message = _Msg(tresc)


class _Odp:
    def __init__(self, tresc):
        self.choices = [_Wybor(tresc)]


@pytest.fixture
def sdk(monkeypatch):
    stan = {"odpowiedz": '{"marchewki": []}'}

    class _Completions:
        @staticmethod
        def create(**kw):
            o = stan["odpowiedz"]
            if isinstance(o, Exception):
                raise o
            return _Odp(o)

    class _Klient:
        def __init__(self, api_key):
            self.chat = type("_C", (), {"completions": _Completions})()

    monkeypatch.setattr(tr, "_HAS_GROQ_SDK", True)
    monkeypatch.setattr(tr, "_GroqSDK", _Klient)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x")
    return stan


def test_czysty_json_sparsowany(sdk):
    sdk["odpowiedz"] = '{"marchewki": [{"regula": "x"}]}'

    assert tr.ask_groq_trainer("raport", 100)["marchewki"][0]["regula"] == "x"


def test_json_w_bloku_kodu_sparsowany(sdk):
    """Groq lubi opakowywać odpowiedź w ```json mimo instrukcji."""
    sdk["odpowiedz"] = 'Oto wynik:\n```json\n{"kije": [1]}\n```\nGotowe.'

    assert tr.ask_groq_trainer("raport", 100) == {"kije": [1]}


def test_json_w_zwyklym_bloku_sparsowany(sdk):
    sdk["odpowiedz"] = '```\n{"kije": [2]}\n```'

    assert tr.ask_groq_trainer("raport", 100) == {"kije": [2]}


def test_odpowiedz_nie_do_sparsowania_to_none(sdk):
    """Śmieć zamiast JSON-a nie może nadpisać lekcji połowicznymi danymi."""
    sdk["odpowiedz"] = "Model napisal esej zamiast JSON-a"

    assert tr.ask_groq_trainer("raport", 100) is None


def test_awaria_sdk_to_none(sdk):
    sdk["odpowiedz"] = RuntimeError("503 service unavailable")

    assert tr.ask_groq_trainer("raport", 100) is None
