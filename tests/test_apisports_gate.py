"""Bramka API-Football: jeden wyłącznik ruchu + zatrzask na blokadzie konta.

Kontekst (2026-09-02): konto zostało zawieszone DRUGI raz, po czym wykupiono plan
Pro (7500 req/dzień, 300/min, bez okna dat — zmierzone przez `/status`). Testy
pilnują dwóch rzeczy:

  * ubicie źródła to JEDNA zmiana, nie osiem zgodnych zmian w ośmiu plikach —
    jedno przeoczone miejsce dalej wysyłałoby ruch;
  * gdyby konto znów zostało zawieszone, ruch ustaje po PIERWSZEJ takiej
    odpowiedzi, bez czekania na człowieka.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from footstats.core import apisports_gate as gate

SRC = Path(__file__).resolve().parents[1] / "src" / "footstats"


@pytest.fixture(autouse=True)
def _czysta_bramka(monkeypatch):
    """Latch zawieszenia jest globalny w procesie — każdy test zaczyna od zera."""
    monkeypatch.setattr(gate, "_ZAWIESZONE", False, raising=False)
    monkeypatch.delenv(gate.ENV_WYLACZNIK, raising=False)
    monkeypatch.setenv("APISPORTS_KEY", "klucz-testowy")


def test_domyslnie_wlaczone():
    """Konto jest opłacone (Pro) — domyślne milczenie źródła byłoby pułapką."""
    assert gate.wlaczone() is True
    assert gate.klucz() == "klucz-testowy"


@pytest.mark.parametrize("wartosc", ["0", "false", "off", "NO", " 0 "])
def test_jawny_wylacznik_zamyka_bramke(monkeypatch, wartosc):
    monkeypatch.setenv(gate.ENV_WYLACZNIK, wartosc)
    assert gate.wlaczone() is False
    assert gate.klucz() is None


def test_wlaczone_bez_klucza_nie_wymysla_klucza(monkeypatch, tmp_path):
    # `_czytaj_wszystkie_klucze` dobiera braki z `.env`, więc samo skasowanie
    # zmiennej środowiskowej nie wystarcza do zasymulowania „brak klucza".
    from footstats import config

    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "brak.env")
    monkeypatch.delenv("APISPORTS_KEY", raising=False)
    assert gate.klucz() is None


def test_pusta_zmienna_nie_dobiera_klucza_z_pliku(monkeypatch, tmp_path):
    """`APISPORTS_KEY=""` znaczy „brak klucza", a nie „wez z .env".

    Regresja po realnym wycieku (2026-09-02): bramka dobrała wtedy prawdziwy klucz
    z `.env`, a pytest wypisał go w komunikacie asercji. Tu `.env` CELOWO zawiera
    wartość — test jest bez sensu, jeśli plik jest pusty.
    """
    from footstats import config

    plik = tmp_path / "pelny.env"
    plik.write_text('APISPORTS_KEY="klucz-z-pliku"\n', encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", plik)

    monkeypatch.setenv("APISPORTS_KEY", "")
    assert gate.klucz() is None

    # Kontrola, że plik realnie byłby czytany — inaczej test przechodzi z
    # niewłaściwego powodu (pusty plik zawsze daje None).
    monkeypatch.delenv("APISPORTS_KEY", raising=False)
    assert gate.klucz() == "klucz-z-pliku"


def test_zawieszenie_w_odpowiedzi_zatrzaskuje_bramke(monkeypatch):
    """Realna odpowiedź z 2026-09-02 rano: HTTP 200, konto zawieszone w `errors`."""
    assert gate.klucz() == "klucz-testowy"

    payload = {
        "errors": {"access": "Your account is suspended, check on https://dashboard.api-football.com."},
        "response": [],
    }
    assert gate.zglos_odpowiedz(payload) is True

    # Po zatrzaśnięciu domyślne „otwarte" już nie pomaga — to jest różnica
    # między „wyłączyliśmy" a „przestaliśmy wysyłać".
    assert gate.wlaczone() is False
    assert gate.klucz() is None


def test_limit_dzienny_nie_zatrzaskuje_bramki():
    """Wyczerpany limit to normalny stan doby, nie powód do trwałego wyłączenia."""
    payload = {"errors": {"requests": "You have reached the request limit for the day"}}
    assert gate.zglos_odpowiedz(payload) is False
    assert gate.klucz() == "klucz-testowy"


def test_poprawna_odpowiedz_nie_zatrzaskuje_bramki():
    assert gate.zglos_odpowiedz({"errors": [], "response": [{"fixture": {}}]}) is False
    assert gate.klucz() == "klucz-testowy"


def test_odpowiedz_nie_bedaca_jsonem_nie_zatrzaskuje():
    """Strona błędu proxy to awaria sieci, nie decyzja dostawcy o koncie."""
    assert gate.zglos_odpowiedz("<html>502</html>") is False
    assert gate.klucz() == "klucz-testowy"


# ── Audyt: nikt nie czyta klucza z pominięciem bramki ────────────────────────

# Surowy odczyt klucza poza bramką. Dopuszczone tylko w `config.py`
# (rejestr nazw zmiennych + interaktywny zapis w CLI) i w samej bramce.
_WZORCE_OMIJAJACE = (
    re.compile(r"""os\.getenv\(\s*["']APISPORTS_KEY["']"""),
    re.compile(r"""os\.environ\[\s*["']APISPORTS_KEY["']"""),
    re.compile(r"_czytaj_wszystkie_klucze\(\)[^\n]*ENV_APISPORTS"),
)

_DOZWOLONE = {"config.py", "apisports_gate.py"}


def test_klucz_apisports_czytany_tylko_przez_bramke():
    """Osiem kopii tej samej reguły to osiem szans na przeoczenie jednej.

    Dokładnie ten kształt błędu kosztował nas już raz (reguła singla w czterech
    miejscach). Tu stawka jest wyższa: przeoczone miejsce wysyła ruch z konta,
    które dostawca zawiesił.
    """
    winowajcy: list[str] = []
    for plik in SRC.rglob("*.py"):
        if plik.name in _DOZWOLONE:
            continue
        tekst = plik.read_text(encoding="utf-8", errors="ignore")
        for wzor in _WZORCE_OMIJAJACE:
            for m in wzor.finditer(tekst):
                nr = tekst[: m.start()].count("\n") + 1
                winowajcy.append(f"{plik.relative_to(SRC)}:{nr}: {m.group(0)}")
    assert not winowajcy, (
        "Klucz API-Football czytany z pominięciem `core.apisports_gate.klucz()`:\n  "
        + "\n  ".join(winowajcy)
    )


def test_kazde_zapytanie_do_api_football_ma_naglowek_z_bramki():
    """`x-apisports-key` wolno budować tylko z wartości oddanej przez bramkę.

    Ratchet: liczba miejsc wysyłających ruch do api-sports.io ma MALEĆ. Każde
    z nich musi mieć klucz od `klucz()` — inaczej wyłącznik jest dziurawy.
    """
    pliki_z_naglowkiem = sorted(
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if "x-apisports-key" in p.read_text(encoding="utf-8", errors="ignore")
    )
    bez_bramki = [
        p
        for p in pliki_z_naglowkiem
        if "apisports_gate" not in (SRC / p).read_text(encoding="utf-8", errors="ignore")
    ]
    assert not bez_bramki, (
        "Pliki wysyłają zapytania do API-Football bez importu bramki "
        f"`core.apisports_gate`: {bez_bramki}"
    )
