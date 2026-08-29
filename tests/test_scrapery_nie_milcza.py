"""J1 w scraperach karmiących model: terminarz (mecze) i Understat (xG).

Oba mają ten sam kształt cichej awarii: źródło ODPOWIADA, ale oddaje coś innego
niż dane, a kod traktuje to jak „nic nie ma". Różnica jest kluczowa — „brak
danych" to stan normalny (mecz jeszcze nierozegrany), a „zmieniony układ strony"
to awaria wymagająca reakcji. Bez logu wyglądają identycznie.

Nie wszystko tu ucichło i to jest świadome:
  * `_poprawna_data` to PREDYKAT — `False` jest odpowiedzią, nie połkniętą awarią;
  * `_i`/`_f` w Understat lecą dla każdego pola każdego zawodnika (setki na
    przebieg), a puste pole to stan normalny;
  * `_parsuj_liczbe` ma handler NIEOSIĄGALNY przy obecnym regexie.
Każdy z nich ma teraz komentarz mówiący, dlaczego milczy.
"""
from __future__ import annotations

import logging

from footstats.scrapers import terminarz as tz
from footstats.scrapers import understat_xg as ux


# ── terminarz: HTTP 200, ale to nie są dane ─────────────────────────────────

def test_odpowiedz_200_ktora_nie_jest_jsonem_jest_glosna(caplog, monkeypatch):
    """Dwie sąsiednie gałęzie (sieć, HTTP != 200) już logowały — ta jedna
    milczała. A to właśnie kształt „strona blokady / captcha / zmieniony
    endpoint": serwer mówi OK i oddaje HTML."""
    class _Odp:
        status_code = 200
        text = "<html><body>Access denied</body></html>"
        def json(self): raise ValueError("nie JSON")

    monkeypatch.setattr(tz.requests, "get", lambda *a, **k: _Odp())

    with caplog.at_level(logging.WARNING):
        assert tz._pobierz_json("http://x/api") is None

    assert "NIE jest JSON-em" in caplog.text
    assert "Access denied" in caplog.text, (
        "log ma pokazac POCZATEK tresci — bez niej nie wiadomo, czy to captcha,"
        " blokada, czy zmieniony endpoint"
    )


def test_wynik_nie_do_odczytania_mowi_ze_mecz_idzie_jako_nierozegrany(caplog):
    with caplog.at_level(logging.WARNING):
        assert tz._wynik_ft({"score1": "abc", "score2": "x", "team1": "Arsenal"}) == []

    assert "NIEROZEGRANY" in caplog.text
    assert "Arsenal" in caplog.text


def test_brak_wyniku_to_stan_normalny_i_milczy(caplog):
    """Kontrola. Mecz jeszcze nierozegrany nie ma wyniku — to nie awaria,
    a `_wynik_ft` leci po KAŻDYM meczu terminarza."""
    with caplog.at_level(logging.WARNING):
        assert tz._wynik_ft({"team1": "Arsenal"}) == []
        assert tz._wynik_ft({"score1": 2, "score2": 1}) == [2, 1]

    assert caplog.text == ""


def test_predykat_daty_zostaje_cichy(caplog):
    """`_poprawna_data` odpowiada na pytanie „czy to data". `False` JEST
    odpowiedzią — log tutaj byłby błędem, nie poprawą."""
    with caplog.at_level(logging.WARNING):
        assert tz._poprawna_data("2026-08-29") is True
        assert tz._poprawna_data("nie-data") is False

    assert caplog.text == ""


def test_zla_data_startu_ligi_mowi_co_traci_GUI(caplog):
    with caplog.at_level(logging.WARNING):
        assert tz.dni_do("kiedys") is None

    assert "za ile startuje" in caplog.text


# ── Understat: zmieniony układ strony ≠ brak danych ─────────────────────────

def test_zmieniony_uklad_tabeli_jest_glosny(caplog, monkeypatch):
    """Filtr wyżej przepuszcza tylko tabele z Team/xG/xGA, więc brak kolumny `M`
    znaczy: tabela JEST, ale Understat zmienił układ. Cicho wyglądało to jak
    liga bez xG — czyli jak brak danych, a nie jak awaria wymagająca reakcji."""
    html = """<html><body><table>
        <tr><th>Team</th><th>xG</th><th>xGA</th></tr>
        <tr><td>Arsenal</td><td>1.5</td><td>0.9</td></tr>
    </table></body></html>"""
    monkeypatch.setattr("footstats.scrapers.browser_fetch.pobierz_html",
                        lambda *a, **k: html)

    with caplog.at_level(logging.WARNING):
        wynik = ux.fetch_league_team_xg("EPL", 2026)

    assert wynik == {}
    assert "brakuje kolumny" in caplog.text
    assert "'M'" in caplog.text or "M" in caplog.text


def test_kompletna_tabela_ligi_nie_generuje_ostrzezen(caplog, monkeypatch):
    """Kontrola: poprawny układ ma przejść bez jednego ostrzeżenia."""
    html = """<html><body><table>
        <tr><th>Team</th><th>M</th><th>xG</th><th>xGA</th></tr>
        <tr><td>Arsenal</td><td>10</td><td>18.5</td><td>9.2</td></tr>
    </table></body></html>"""
    monkeypatch.setattr("footstats.scrapers.browser_fetch.pobierz_html",
                        lambda *a, **k: html)
    monkeypatch.setattr(ux, "_cache_set", lambda *a, **k: None)

    with caplog.at_level(logging.WARNING):
        wynik = ux.fetch_league_team_xg("EPL", 2026)

    assert "Arsenal" in wynik
    assert caplog.text == ""


def test_konwertery_pol_zawodnika_milcza(caplog):
    """`_i`/`_f` lecą dla każdego pola każdego zawodnika (setki na przebieg),
    a puste pole w Understat to stan normalny — log zalałby przebieg."""
    dane = [{"player_name": "X", "team_title": "Arsenal",
             "goals": "", "xG": "", "assists": "bzdura"}]

    with caplog.at_level(logging.WARNING):
        wynik = ux._mapuj_graczy(dane)

    assert len(wynik) == 1, "zawodnik ma przejsc mimo zepsutych pol"
    assert caplog.text == ""


def test_roznica_miedzy_i_a_f_jest_udokumentowana():
    """`_i` zwraca 0 (REALNA wartość udająca pomiar), `_f` zwraca None
    (uczciwe „nie wiadomo"). To NIE jest to samo i kod musi o tym mówić —
    inaczej ktoś potraktuje 0 goli jako zmierzone zero."""
    import inspect

    zrodlo = inspect.getsource(ux)
    assert "UWAGA NA ROZNICE" in zrodlo, (
        "znikl komentarz o tym, ze `_i` fabrykuje 0, a `_f` oddaje None"
    )
