"""Nazwa modelu Groqa ma zyc w JEDNYM miejscu.

TRZECI RAZ TEN SAM KSZTALT BLEDU:

  16-22.08  Groq wycofal `llama-3.1-8b-instant`. Potok stal 6 dni przy exit=0,
            bo nazwa byla defaultem w kodzie, a job nie mial GROQ_MODEL.
  22.08     Naprawione — ale TYLKO w `ai/client.py`.
  31.08     Zmierzone na logach produkcji: `ai/analyzer.py` mial WLASNE, zaszyte
            `llama-3.1-8b-instant` w dwoch miejscach i codziennie dostawal 404:

              Wyspecjalizowany typer Groq zawiodl (NotFoundError: 404 - The model
              `llama-3.1-8b-instant` does not exist) - przechodze na fallback

            Fallback dzialal, wiec typy powstawaly (`predictions` dostawalo
            wiersze), ale kupon `kupon_a` juz nie — i faza final nie zapisala
            zadnego kuponu od 15.08.

Zaszyta nazwa modelu ma dwa niezalezne skutki i oba sa ciche: 404 pochlaniany
przez fallback ORAZ brak `reasoning_effort`, ktory dla `gpt-oss` spala caly
budzet wyjscia na rozumowanie (zmierzone 22.08: 330 z 400 tokenow).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from footstats.ai import analyzer as an
from footstats.ai import client as cl

_SRC = Path(__file__).resolve().parents[1] / "src" / "footstats"

# Nazwy modeli Groqa, ktore kiedykolwiek u nas byly. Kazda z nich poza
# `ai/client.py` to nawrot bledu.
_NAZWY_MODELI = re.compile(
    r"[\"'](?:llama-[\d.]+-\w+|openai/gpt-oss-\w+|groq/compound\w*|"
    r"llama-[\d.]+-\d+b-\w+)[\"']"
)

# Jedyne pliki, ktore maja prawo znac nazwy modeli.
_WOLNO = {
    Path("ai/client.py"),          # zrodlo prawdy: GROQ_MODEL + tabela TPM
}


def _pliki_zrodlowe():
    for p in _SRC.rglob("*.py"):
        wzgledna = p.relative_to(_SRC)
        if "__pycache__" in wzgledna.parts:
            continue
        yield wzgledna, p


def test_nazwa_modelu_nie_jest_zaszyta_poza_clientem():
    """Straznik na nawrot. Komentarz z nazwa jest OK — chodzi o kod."""
    winowajcy = []
    for wzgledna, sciezka in _pliki_zrodlowe():
        if wzgledna in _WOLNO:
            continue
        for nr, linia in enumerate(sciezka.read_text(encoding="utf-8").splitlines(), 1):
            bez_komentarza = linia.split("#", 1)[0]
            if _NAZWY_MODELI.search(bez_komentarza):
                winowajcy.append(f"{wzgledna}:{nr}: {linia.strip()[:90]}")

    assert not winowajcy, (
        "nazwa modelu Groqa zaszyta poza ai/client.py — dokladnie ten blad "
        "zatrzymal potok 16-22.08 i wrocil 31.08:\n" + "\n".join(winowajcy)
    )


# ── wywolania w analyzer ida przez wspolne parametry ────────────────────────

class _AtrapaOdpowiedzi:
    def __init__(self, tresc="{}", finish_reason="stop"):
        wybor = type("W", (), {})()
        wybor.message = type("M", (), {"content": tresc})()
        wybor.finish_reason = finish_reason
        self.choices = [wybor]


class _AtrapaKlienta:
    def __init__(self):
        self.wywolania = []
        self.chat = type("C", (), {})()
        self.chat.completions = type("K", (), {})()
        self.chat.completions.create = self._create

    def _create(self, **kw):
        self.wywolania.append(kw)
        return _AtrapaOdpowiedzi()


@pytest.fixture
def klient(monkeypatch):
    k = _AtrapaKlienta()
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(an, "_get_kalibracja_blok", lambda: "")
    monkeypatch.setattr(an, "_get_liga_statystyki_blok", lambda: "")

    class _Modul:
        Groq = staticmethod(lambda api_key: k)

    monkeypatch.setitem(__import__("sys").modules, "groq", _Modul)
    return k


def test_typer_uzywa_modelu_z_clienta(klient, monkeypatch):
    monkeypatch.setattr(cl, "GROQ_MODEL", "openai/gpt-oss-120b")
    an._zapytaj_typera("pytanie")
    assert klient.wywolania[0]["model"] == "openai/gpt-oss-120b"


def test_zmiana_GROQ_MODEL_przechodzi_do_typera(klient, monkeypatch):
    """Bez tego podmiana modelu przez env omija typera — tak powstal blad 31.08."""
    monkeypatch.setattr(cl, "GROQ_MODEL", "llama-3.3-70b-versatile")
    an._zapytaj_typera("pytanie")
    assert klient.wywolania[0]["model"] == "llama-3.3-70b-versatile"


def test_typer_ustawia_reasoning_effort_dla_gpt_oss(klient, monkeypatch):
    """Bez tego `gpt-oss` spala budzet wyjscia na rozumowanie i urywa JSON."""
    monkeypatch.setattr(cl, "GROQ_MODEL", "openai/gpt-oss-120b")
    an._zapytaj_typera("pytanie")
    assert klient.wywolania[0].get("reasoning_effort") == "low"


def test_reasoning_effort_NIE_leci_do_modelu_ktory_go_nie_zna(klient, monkeypatch):
    """Nieznane pole zostaloby odrzucone przez API."""
    monkeypatch.setattr(cl, "GROQ_MODEL", "llama-3.3-70b-versatile")
    an._zapytaj_typera("pytanie")
    assert "reasoning_effort" not in klient.wywolania[0]


def test_dokonczenie_ucietego_json_tez_uzywa_wspolnego_modelu(klient, monkeypatch):
    monkeypatch.setattr(cl, "GROQ_MODEL", "openai/gpt-oss-120b")
    an._kontynuuj_uciety_json(klient, [{"role": "user", "content": "x"}], "{")
    assert klient.wywolania[0]["model"] == "openai/gpt-oss-120b"
    assert klient.wywolania[0].get("reasoning_effort") == "low"


def test_budzet_tokenow_jest_skalowany_pod_model(klient, monkeypatch):
    """Reasoning placi za rozumowanie z tego samego budzetu co odpowiedz —
    `effective_max_tokens` to uwzglednia, goly max_tokens nie."""
    monkeypatch.setattr(cl, "GROQ_MODEL", "openai/gpt-oss-120b")
    an._zapytaj_typera("pytanie", max_tokens=900)
    assert klient.wywolania[0]["max_tokens"] > 900


def test_awaria_typera_nadal_jest_glosna(klient, monkeypatch, caplog):
    """Fallback pochlonal 404 przez 9 dni. Log jest jedynym sygnalem."""
    import logging

    def _wybuch(**kw):
        raise RuntimeError("model zniknal")

    monkeypatch.setattr(cl, "GROQ_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setattr(klient.chat.completions, "create", _wybuch)
    monkeypatch.setattr(an, "zapytaj_ai", lambda *a, **k: "{}")

    with caplog.at_level(logging.WARNING):
        an._zapytaj_typera("pytanie")

    assert "typer" in caplog.text.lower()
