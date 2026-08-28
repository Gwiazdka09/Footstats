"""J1 w API-Football: to źródło ma udokumentowaną cichą awarię.

01.08.2026 konto zostało **zawieszone** (nie limit — suspended). API dalej
odpowiadało HTTP 200 z pustą `response`, więc job `footstats-final` po prostu
przestał dostawać składy, tabele i sędziego. Nic tego nie zgłosiło; wpis
`project_apifootball_zawieszone` opisuje to jako cichą utratę danych.

Kod ma tu dwie warstwy ciszy:
  * kształt odpowiedzi bez oczekiwanych kluczy → `return None`,
  * wyczerpany budżet → po cichu oddaje WYGASŁE dane z cache, a wołający nie ma
    jak odróżnić ich od świeżych.

Osobno naprawiony błąd, który nie był kwestią logu, tylko poprawności:
częściowe sparsowanie predykcji zostawiało REALNE `pw` obok DOMYŚLNYCH `pr`/`pp`.
"""
from __future__ import annotations

import logging

import pytest

from footstats.scrapers import api_football as af


# ── kształt odpowiedzi ──────────────────────────────────────────────────────

def test_pusta_odpowiedz_standings_mowi_ktora_liga_stracila_tabele(caplog, monkeypatch):
    """Dokładnie to zwracało zawieszone konto: HTTP 200 i pusta `response`."""
    klient = af.APIFootball.__new__(af.APIFootball)
    monkeypatch.setattr(klient, "_get", lambda *a, **k: {"response": []}, raising=False)

    with caplog.at_level(logging.WARNING):
        assert klient.tabela_liga(39, 2026) is None

    assert "BEZ tabeli" in caplog.text
    assert "39" in caplog.text, "log ma nazwac LIGE, inaczej nie wiadomo czego brakuje"


def test_kurs_ktory_nie_jest_liczba_jest_glosny(caplog):
    with caplog.at_level(logging.WARNING):
        assert af._parse_odd("nie-liczba") is None
    assert "nie jest liczba" in caplog.text


def test_brak_kursu_to_stan_normalny_i_milczy(caplog):
    """Kontrola. `None` znaczy „bukmacher nie wystawił" — to nie awaria,
    a `_parse_odd` woła się dla każdego kursu każdego meczu."""
    with caplog.at_level(logging.WARNING):
        assert af._parse_odd(None) is None
        assert af._parse_odd("1.85") == 1.85
        assert af._parse_odd(2.10) == 2.10

    assert caplog.text == ""


# ── poprawność: wszystko albo nic ───────────────────────────────────────────

def _klient_z_predykcja(monkeypatch, pct: dict):
    """Prawdziwe `kandydaci_liga` na podstawionym `_get` — bez sieci."""
    from datetime import datetime, timedelta, timezone

    za_dobe = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    klient = af.APIFootball.__new__(af.APIFootball)

    def _get(endpoint, params=None):
        if endpoint == "/fixtures":
            return {"response": [{
                "fixture": {"id": 1, "date": za_dobe},
                "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
                "league": {"name": "Premier League"},
            }]}
        if endpoint == "/predictions":
            return {"response": [{"predictions": {"percent": pct}}]}
        return None

    monkeypatch.setattr(klient, "_get", _get, raising=False)
    return klient


@pytest.mark.parametrize(
    "pct",
    [
        {"home": "60%", "draw": "zepsute", "away": "20%"},
        {"home": "zepsute", "draw": "25%", "away": "25%"},
        {"home": "60%", "draw": "20%", "away": None},
        {"home": "60%", "draw": "20%"},
    ],
)
def test_czesciowe_predykcje_nie_mieszaja_realnych_z_domyslnymi(monkeypatch, caplog, pct):
    """TO NIE JEST kwestia logu, tylko poprawności — i jest sprawdzane na
    PRAWDZIWEJ `kandydaci_liga`, nie na odtworzonej logice.

    Były DWIE drogi do tej samej mieszanki, obie ciche:
      * wyjątek na drugiej wartości zostawiał REALNE `pw` obok DOMYŚLNYCH
        `pr`/`pp` (50/25/25 z resetu wyżej) — suma nawet 150%;
      * `pct.get("away", "25%") or "25%"` podstawiał domyślną wartość PER POLE,
        więc brak samego `away` dawał realne 60/20 obok domyślnego 25 — suma 105%.
        Ta druga wyszła dopiero z parametryzacji tego testu.

    Taka mieszanka szła prosto do progu selekcji `max_p`. Teraz jest
    wszystko-albo-nic: albo trzy zmierzone, albo trzy domyślne.
    """
    klient = _klient_z_predykcja(monkeypatch, pct)

    with caplog.at_level(logging.WARNING):
        wyniki = klient.kandydaci_liga(39, godziny=72, prog_pw=0.0)

    assert len(wyniki) == 1
    w = wyniki[0]
    assert (w["pw"], w["pr"], w["pp"]) == (50.0, 50.0, 50.0), (
        f"zepsuty fragment ma cofnac CALY zestaw do domyslnych, dostalem"
        f" {w['pw']}/{w['pr']}/{w['pp']}"
    )
    assert "domyslne 50/50/50" in caplog.text, (
        "log ma podac wartosci, ktore NAPRAWDE zostaly uzyte — pierwsza wersja"
        " mowila 50/25/25 z dawnych `.get(k, \"25%\")`, a realny fallback pochodzi"
        " z resetu `pw = pr = pp = 50.0` na poczatku iteracji"
    )


def test_komplet_predykcji_przechodzi_bez_zmian(monkeypatch, caplog):
    """Kontrola: poprawna odpowiedź ma dawać ZMIERZONE wartości i zero szumu."""
    klient = _klient_z_predykcja(
        monkeypatch, {"home": "60%", "draw": "25%", "away": "15%"})

    with caplog.at_level(logging.WARNING):
        wyniki = klient.kandydaci_liga(39, godziny=72, prog_pw=0.0)

    assert (wyniki[0]["pw"], wyniki[0]["pr"], wyniki[0]["pp"]) == (60.0, 25.0, 15.0)
    assert "domyslne" not in caplog.text


def test_kod_produkcyjny_uzywa_wszystko_albo_nic():
    """Dodatkowa kotwica na KSZTALT kodu: oba mechanizmy (sprawdzenie kompletu
    i przypisanie dopiero w `else`) muszą tam zostać. Sam wynik mógłby wyjść
    poprawnie przypadkiem, gdyby ktoś przepisał to inaczej i gorzej."""
    import inspect

    zrodlo = inspect.getsource(af.APIFootball.kandydaci_liga)
    assert "pw, pr, pp = _pw, _pr, _pp" in zrodlo
    assert "brakujace" in zrodlo, (
        "znikl sprawdzian kompletu pol — brak samego `away` znowu wymiesza"
        " realne z domyslnymi"
    )
