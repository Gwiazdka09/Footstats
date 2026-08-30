"""Parser FotMoba na PRAWDZIWYCH fiksturach.

Zero sieci w pytescie (.claude/rules/tests-no-prod.md) — `_pobierz` jest
podmieniany. Fikstury pochodza z zywego zrodla (scripts/zapisz_fikstury_fotmob.py),
bo zmyslony ksztalt przechodzi na blednym kodzie.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

from footstats.scrapers.teamnews import fotmob as fm
from footstats.scrapers.teamnews.base import TeamNewsSource

_FIKS = Path(__file__).parent / "fixtures" / "fotmob"


def _wczytaj(nazwa: str) -> dict:
    return json.loads((_FIKS / nazwa).read_text(encoding="utf-8"))


# ── parsowanie pojedynczego meczu ───────────────────────────────────────────

def test_predicted_daje_pelny_sklad_i_absencje():
    tn = fm.parsuj_mecz(_wczytaj("match_predicted.json"), "2026-08-30")
    assert tn.typ_skladu == "predicted"
    assert tn.sklad_jest_prognoza is True
    assert len(tn.xi_home) == 11 and len(tn.xi_away) == 11
    assert tn.absencje_home and tn.absencje_away
    assert tn.home and tn.away


def test_lastStarting11_NIE_udaje_prognozy():
    """Sedno DTO: ostatni sklad to nie prognoza na TEN mecz. Gdyby parser to
    zlal, korekta lambdy liczylaby sie z danych o innym znaczeniu."""
    tn = fm.parsuj_mecz(_wczytaj("match_last_xi.json"), "2026-08-30")
    assert tn.typ_skladu == "lastStarting11"
    assert tn.sklad_jest_prognoza is False
    assert len(tn.xi_home) == 11


def test_absencje_maja_nazwiska_i_regule_pewna():
    tn = fm.parsuj_mecz(_wczytaj("match_predicted.json"), "2026-08-30")
    wszystkie = tn.absencje_home + tn.absencje_away
    assert all(a.nazwisko for a in wszystkie)
    for a in wszystkie:
        if (a.powrot or "").strip().casefold() == "doubtful":
            assert a.pewna is False
        elif a.powrot:
            assert a.pewna is True


def test_sa_absencje_obu_rodzajow_w_fiksturze():
    """Kontrola samej fikstury: gdyby zawierala wylacznie 'Doubtful',
    test reguly `pewna` przechodzilby na kodzie, ktory zawsze zwraca False."""
    tn = fm.parsuj_mecz(_wczytaj("match_predicted.json"), "2026-08-30")
    wszystkie = tn.absencje_home + tn.absencje_away
    assert any(a.pewna for a in wszystkie), "fikstura bez ani jednej twardej absencji"
    assert any(not a.pewna for a in wszystkie), "fikstura bez ani jednej watpliwej"


def test_sedzia_wyciagany_ze_statystykami():
    tn = fm.parsuj_mecz(_wczytaj("match_predicted.json"), "2026-08-30")
    assert tn.sedzia
    assert "n_matches" in tn.sedzia_stats
    assert "avg_goals" not in tn.sedzia_stats


def test_brak_lineup_daje_DTO_a_nie_wyjatek():
    """Mecz bez skladu to stan NORMALNY (FotMob pokrywa 147 lig, prognozy robi
    dla czesci). Ma wyjsc puste DTO — nie wyjatek i nie zmyslony sklad."""
    tn = fm.parsuj_mecz({"content": {}}, "2026-08-30")
    assert tn.typ_skladu is None
    assert tn.xi_home == () and tn.absencje_home == ()
    assert tn.sedzia is None


def test_smieci_zamiast_sedziego_nie_wywracaja_parsera():
    dane = {"content": {"matchFacts": {"infoBox": {"Referee": "tekst zamiast dictu"}}}}
    tn = fm.parsuj_mecz(dane, "2026-08-30")
    assert tn.sedzia is None and tn.sedzia_stats == {}


# ── adapter ─────────────────────────────────────────────────────────────────

def test_adapter_spelnia_protocol():
    assert isinstance(fm.FotMobTeamNews(), TeamNewsSource)


def test_fetch_laczy_liste_dnia_ze_szczegolami(monkeypatch):
    dzien = _wczytaj("matches_day.json")
    szczegoly = _wczytaj("match_predicted.json")
    wolania = []

    def _stub(sciezka, **params):
        wolania.append(sciezka)
        return dzien if sciezka == "matches" else szczegoly

    monkeypatch.setattr(fm, "_pobierz", _stub)
    monkeypatch.setattr(fm, "_PRZERWA_S", 0.0)

    wynik = fm.FotMobTeamNews().fetch("2026-08-30")
    assert wynik and all(w.source == "fotmob" for w in wynik)
    assert wolania[0] == "matches"
    assert wolania.count("matchDetails") == 5   # 3 mecze ENG + 2 GER w fiksturze


def test_data_zamieniana_na_format_zrodla(monkeypatch):
    """FotMob chce YYYYMMDD, my wszedzie indziej uzywamy YYYY-MM-DD."""
    widziane = {}

    def _stub(sciezka, **params):
        widziane.update(params)
        return {"leagues": []}

    monkeypatch.setattr(fm, "_pobierz", _stub)
    fm.FotMobTeamNews().fetch("2026-08-30")
    assert widziane["date"] == "20260830"


# ── glosnosc awarii ─────────────────────────────────────────────────────────

def test_403_to_ERROR_bo_zabija_cala_sciezke(monkeypatch, caplog):
    """Nieoficjalne API padnie kiedys bez ostrzezenia — tak jak konto AF
    i model Groqa. To jedyny moment, w ktorym mozemy sie o tym dowiedziec."""
    def _wybuch(sciezka, **params):
        odp = requests.Response()
        odp.status_code = 403
        raise requests.HTTPError("403 Forbidden", response=odp)

    monkeypatch.setattr(fm, "_pobierz", _wybuch)

    with caplog.at_level(logging.WARNING):
        assert fm.FotMobTeamNews().fetch("2026-08-30") == []

    assert any(r.levelno >= logging.ERROR for r in caplog.records), (
        "awaria zrodla to ERROR, nie WARNING — po niej nie ma zadnych danych"
    )
    assert "team-news" in caplog.text.lower()


def test_blad_pojedynczego_meczu_nie_zatrzymuje_reszty(monkeypatch, caplog):
    """Jeden mecz poza pokryciem to stan normalny przy 147 ligach — DEBUG,
    nie alarm. Ale reszta dnia ma sie policzyc."""
    dzien = _wczytaj("matches_day.json")
    szczegoly = _wczytaj("match_predicted.json")
    licznik = {"n": 0}

    def _stub(sciezka, **params):
        if sciezka == "matches":
            return dzien
        licznik["n"] += 1
        if licznik["n"] == 1:
            raise requests.RequestException("timeout")
        return szczegoly

    monkeypatch.setattr(fm, "_pobierz", _stub)
    monkeypatch.setattr(fm, "_PRZERWA_S", 0.0)

    with caplog.at_level(logging.WARNING):
        wynik = fm.FotMobTeamNews().fetch("2026-08-30")

    assert len(wynik) == 4, "jeden mecz odpadl, reszta miala sie policzyc"
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_zdrowy_przebieg_nie_generuje_szumu(monkeypatch, caplog):
    """Kontrola: fetch leci raz dziennie dla kazdego meczu."""
    monkeypatch.setattr(fm, "_PRZERWA_S", 0.0)
    monkeypatch.setattr(fm, "_pobierz", lambda s, **p:
                        _wczytaj("matches_day.json") if s == "matches"
                        else _wczytaj("match_predicted.json"))

    with caplog.at_level(logging.WARNING):
        fm.FotMobTeamNews().fetch("2026-08-30")

    assert caplog.text == ""


def test_pusta_lista_dnia_nie_jest_bledem(monkeypatch, caplog):
    """Dzien bez meczow (przerwa reprezentacyjna) to nie awaria."""
    monkeypatch.setattr(fm, "_pobierz", lambda s, **p: {"leagues": []})

    with caplog.at_level(logging.WARNING):
        assert fm.FotMobTeamNews().fetch("2026-08-30") == []

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# ── koszt: filtr dziala PRZED pobraniem szczegolow ──────────────────────────

def test_filtr_ogranicza_liczbe_requestow(monkeypatch):
    """FotMob mial 30.08 czterysta osiemdziesiat dwa mecze w 147 ligach.
    Sciaganie szczegolow wszystkich to 483 requesty na przebieg, zeby uzyc
    kilkudziesieciu. Filtr MUSI dzialac na liscie dnia, nie po pobraniu."""
    dzien = _wczytaj("matches_day.json")
    szczegoly = _wczytaj("match_predicted.json")
    sklad = json.loads((_FIKS / "team_squad.json").read_text(encoding="utf-8"))
    sciezki = []

    def _stub(sciezka, **params):
        sciezki.append(sciezka)
        return {"matches": dzien, "matchDetails": szczegoly}.get(sciezka, sklad)

    monkeypatch.setattr(fm, "_pobierz", _stub)
    monkeypatch.setattr(fm, "_PRZERWA_S", 0.0)

    pierwszy = fm.parsuj_liste_dnia(dzien)[0]
    wynik = fm.FotMobTeamNews().fetch_dla("2026-08-30", [(pierwszy.home, pierwszy.away)])

    # Koszt rozbity na rodzaje — zbiorcze liczenie ukrylo by, ktory element rosnie.
    assert sciezki.count("matches") == 1, "lista dnia pobrana wiecej niz raz"
    assert sciezki.count("matchDetails") == 1, (
        f"szczegoly {sciezki.count('matchDetails')} meczow zamiast 1")
    assert sciezki.count("teams") <= 2, (
        f"sklady: {sciezki.count('teams')} zapytan, dopuszczalne 2 (obie druzyny)")
    assert len(wynik) == 1


def test_brak_dopasowania_to_zero_requestow_o_szczegoly(monkeypatch):
    dzien = _wczytaj("matches_day.json")
    detale = []

    def _stub(sciezka, **params):
        if sciezka == "matches":
            return dzien
        detale.append(params.get("matchId"))
        return {}

    monkeypatch.setattr(fm, "_pobierz", _stub)
    monkeypatch.setattr(fm, "_PRZERWA_S", 0.0)

    assert fm.FotMobTeamNews().fetch_dla("2026-08-30", [("Nieistniejacy", "Klub")]) == []
    assert detale == []


def test_filtr_znosi_rozna_pisownie_nazw(monkeypatch):
    """Nasze zrodla pisza "Brighton", FotMob "Brighton & Hove Albion"."""
    dzien = _wczytaj("matches_day.json")
    monkeypatch.setattr(fm, "_pobierz", lambda s, **p:
                        dzien if s == "matches" else _wczytaj("match_predicted.json"))
    monkeypatch.setattr(fm, "_PRZERWA_S", 0.0)

    pierwszy = fm.parsuj_liste_dnia(dzien)[0]
    skrocona = pierwszy.away.split(" &")[0].split(" FC")[0]
    wynik = fm.FotMobTeamNews().fetch_dla("2026-08-30", [(pierwszy.home, skrocona)])

    assert len(wynik) == 1, f"'{skrocona}' nie dopasowalo sie do '{pierwszy.away}'"


def test_lista_dnia_parsuje_id_i_nazwy():
    mecze = fm.parsuj_liste_dnia(_wczytaj("matches_day.json"))
    assert mecze and all(m.id and m.home and m.away for m in mecze)
    assert all("/" in m.liga for m in mecze)


def test_pozycje_bez_id_lub_nazw_odpadaja():
    dane = {"leagues": [{"ccode": "X", "name": "Y", "matches": [
        {"id": None, "home": {"name": "A"}, "away": {"name": "B"}},
        {"id": 1, "home": {"name": ""}, "away": {"name": "B"}},
        {"id": 2, "home": {"name": "A"}, "away": {"name": "B"}},
    ]}]}
    assert [m.id for m in fm.parsuj_liste_dnia(dane)] == [2]


def test_mecz_bez_skladu_zachowuje_tozsamosc_z_listy_dnia():
    """Mecz bez lineupu moze wciaz niesc sedziego — bez nazw z listy dnia
    wypadalby z wyniku po cichu."""
    tn = fm.parsuj_mecz({"content": {}}, "2026-08-30", home="Wisla", away="Legia")
    assert tn.home == "Wisla" and tn.away == "Legia"
    assert tn.xi_home == ()
