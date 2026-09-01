"""Odpowiedz LLM-a musi zmiescic sie w budzecie wyjscia.

ZMIERZONE NA PRODUKCJI 01.09 (`footstats-final-pqgt7`, prog 50%):

    [AI] Budzet TPM: wejscie 5160 tok zjada limit 8000 — wyjscie sciete do 2640
    [AI] Nie udalo sie sparsowac JSON z odpowiedzi modelu. Poczatek odpowiedzi:
      {"top3": [{"mecz": "FC Zurich vs BSC Young Boys", "typ": "Over 2.5",
       "kurs": 1.85, "pewnosc_pct": 73, "ev_netto": 5.2, "uzasadnienie": ...
    [AI] Model jezykowy nie zwrocil typow — 3 typow zbudowanych z modelu

Model NIE odmowil i nie byl zepsuty: prog 50% zadzialal, wystawil typ
z pewnoscia 73%. Odpowiedz sie URWALA, bo na wyjscie zostalo 2640 tokenow.

Zrodlo rozdecia: prompt zadal CZTERECH kuponow ("Fill all four") niezaleznie
od tego, ile jest meczow. Przy trzech kandydatach czwarty jest niemozliwy —
`Each slip = a DIFFERENT match` — a model i tak probowal go wypisac. Placilismy
tokenami wyjscia za pola, ktorych nie da sie wypelnic.

To ta sama sprzecznosc, ktora naprawiono w bloku ABSOLUTE BANS, tyle ze druga
jej kopia siedziala w opisie schematu i zostala przeoczona. Dwie kopie tej samej
reguly rozjezdzaja sie po cichu.
"""
from __future__ import annotations

import pytest

from footstats.ai.prompts import build_pewniaczki_prompt


def _prompt(n_mecze: int) -> str:
    return build_pewniaczki_prompt(
        n_mecze=n_mecze, sygnaly="", kalibracja_str="", feedback_str="",
        mecze_opisy_text="MECZ", cel_kuponow_text="CEL",
    )


def test_nie_zada_juz_czterech_kuponow_na_sztywno():
    assert "Fill all four" not in _prompt(3)


@pytest.mark.parametrize("ile", [1, 2, 3])
def test_zada_tylu_kuponow_ile_jest_meczow(ile):
    """Kupon na mecz, ktorego nie ma, to tokeny wyjscia wydane na nic."""
    tekst = _prompt(ile)

    assert f"Fill {ile}" in tekst or f"first {ile}" in tekst, (
        f"prompt nie mowi modelowi, ze ma wypelnic {ile} kuponow: "
        f"{[l for l in tekst.splitlines() if 'kupon_b' in l]}"
    )


def test_przy_piatce_dalej_cztery():
    """Cztery to gorny limit struktury (kupon_a..d), nie liczba do przebicia."""
    tekst = _prompt(5)

    assert "Fill 4" in tekst or "Fill four" in tekst


def test_struktura_kuponow_zostaje_w_schemacie():
    """Kontrola: skracamy ZADANIE, nie kontrakt JSON. Parser czyta kupon_a."""
    tekst = _prompt(1)

    for klucz in ("top3", "kupon_a", "zdarzenia", "kurs_laczny", "ostrzezenia"):
        assert klucz in tekst


def test_zakaz_akumulatorow_nietkniety():
    tekst = _prompt(2)

    assert "EXACTLY 1 leg" in tekst
    assert "No accumulators" in tekst


# ── siec ratunkowa dla ucietego JSON tez musi miescic sie w budzecie ─────────
#
# `_kontynuuj_uciety_json` wysyla CALA rozmowe plus urwany fragment — czyli
# wiecej niz pierwotne zapytanie, ktore juz balansowalo na granicy. Liczyla
# jednak budzet przez `effective_max_tokens(max_tokens)` BEZ rozmiaru wejscia,
# wiec sama wpadala w 413. A `except` lapal tylko AttributeError/IndexError,
# wiec 413 wypadal na zewnatrz i kasowal uratowany fragment.

class _Odp:
    def __init__(self, tresc):
        w = type("W", (), {})()
        w.message = type("M", (), {"content": tresc})()
        w.finish_reason = "stop"
        self.choices = [w]


def _klient(create):
    k = type("K", (), {})()
    k.chat = type("C", (), {})()
    k.chat.completions = type("KK", (), {})()
    k.chat.completions.create = create
    return k


# Rozmiar realny, nie symboliczny: na produkcji 01.09 samo wejscie pierwszego
# zapytania wazylo 5160 tok, a kontynuacja dokłada do niego urwany fragment.
# Mniejsza atrapa NIE dotyka limitu i test przechodzi nie sprawdzajac niczego.
# Wieksza tez nie dziala: wejscie ponad CALY limit nie da sie naprawic
# skracaniem wyjscia, wiec test zadalby rzeczy niemozliwej. Cel: ~7000 tok.
_ROZMOWA = [
    {"role": "system", "content": "instrukcja " * 3000},
    {"role": "user", "content": "mecze " * 150},
]
_URWANY = '{"top3": [{"mecz": "A vs B", "typ": "1"' + ", x" * 400


def test_kontynuacja_miesci_sie_w_limicie(monkeypatch):
    from footstats.ai import analyzer as an
    from footstats.ai import client as cl
    from footstats.ai.client import AI_TPM_LIMIT, szacuj_tokeny

    monkeypatch.setattr(cl, "GROQ_MODEL", "openai/gpt-oss-120b")
    widziane = {}

    def _create(**kw):
        widziane.update(kw)
        return _Odp('}]}')

    an._kontynuuj_uciety_json(_klient(_create), _ROZMOWA, _URWANY)

    wejscie = sum(szacuj_tokeny(m["content"]) for m in widziane["messages"])
    assert wejscie + widziane["max_tokens"] <= AI_TPM_LIMIT, (
        f"kontynuacja prosi o {wejscie} + {widziane['max_tokens']} przy limicie "
        f"{AI_TPM_LIMIT} — to jest 413 na ratunku przed urwaniem"
    )


def test_awaria_kontynuacji_ZOSTAWIA_uratowany_fragment(monkeypatch):
    """Fragment jest wszystkim, co mamy. Wyjatek nie moze go wyrzucic."""
    from footstats.ai import analyzer as an
    from footstats.ai import client as cl

    monkeypatch.setattr(cl, "GROQ_MODEL", "openai/gpt-oss-120b")

    def _wybuch(**kw):
        raise RuntimeError("413 - Request too large")

    wynik = an._kontynuuj_uciety_json(_klient(_wybuch), _ROZMOWA, _URWANY)

    assert wynik == _URWANY


def test_udana_kontynuacja_skleja_odpowiedz(monkeypatch):
    from footstats.ai import analyzer as an
    from footstats.ai import client as cl

    monkeypatch.setattr(cl, "GROQ_MODEL", "openai/gpt-oss-120b")
    wynik = an._kontynuuj_uciety_json(
        _klient(lambda **kw: _Odp("DOKONCZENIE")), _ROZMOWA, "CZESC")

    assert wynik == "CZESCDOKONCZENIE"
