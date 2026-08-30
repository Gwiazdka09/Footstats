"""Pozycje zawodnikow z FotMoba — odblokowanie martwej korekty lambda.

DLACZEGO TO POWSTALO. `_apply_injury_corrections` liczy DWUSTRONNA korekte:
brak napastnika/pomocnika obniza WLASNA lambde, brak obroncy/bramkarza podnosi
lambde RYWALA. Klasyfikuje po pozycji (`_POZ_ATAK = F, M` / `_POZ_OBRONA = D, G`),
a jedynym zrodlem pozycji byl SofaScore.

ZMIERZONE 30.08: SofaScore zwraca HTTP 403 na KAZDE zapytanie — z Cloud Runa
przez Playwrighta (logi joba 26-30.08) i lokalnie przez `requests` (sonda,
403 takze na stronie glownej). Lokalnie przez przegladarke dziala, wiec blokada
dotyczy zakresu adresow datacenter ORAZ klientow nieprzegladarkowych. Nagłowkami
sie tego nie obchodzi.

Skutek byl cichy: `injuries_home`/`injuries_away` puste -> `injury_lambda_factors`
zwraca (1.0, 1.0) -> korekta nigdy nie odpala, a przebieg konczy sie sukcesem.

FotMob `/api/data/teams?id=` oddaje sklad POGRUPOWANY po pozycji
(keepers/defenders/midfielders/attackers) i te grupy mapuja sie 1:1 na kody,
ktorych oczekuje model.
"""
from __future__ import annotations

import json
from pathlib import Path

from footstats.scrapers.teamnews import fotmob as fm

_FIKS = Path(__file__).parent / "fixtures" / "fotmob"


def _squad() -> dict:
    return json.loads((_FIKS / "team_squad.json").read_text(encoding="utf-8"))


# ── mapowanie grup na kody modelu ───────────────────────────────────────────

def test_grupy_skladu_mapuja_sie_na_kody_modelu():
    poz = fm.parsuj_pozycje(_squad())
    assert poz["robert sanchez"] == "G"
    assert poz["tosin adarabioyo"] == "D"
    assert poz["jordan henderson"] == "M"
    assert poz["pedro neto"] == "F"


def test_kody_sa_dokladnie_tymi_ktorych_oczekuje_model():
    """Straznik na rozjazd: gdyby ktos zmienil litery, korekta cicho przestanie
    klasyfikowac i wroci do (1.0, 1.0)."""
    from footstats.core.lambda_optimizer import _POZ_ATAK, _POZ_OBRONA

    dozwolone = set(_POZ_ATAK) | set(_POZ_OBRONA)
    poz = fm.parsuj_pozycje(_squad())
    assert poz, "fikstura nie oddala zadnej pozycji"
    assert set(poz.values()) <= dozwolone, (
        f"kody spoza modelu: {set(poz.values()) - dozwolone}"
    )


def test_trener_nie_jest_zawodnikiem():
    poz = fm.parsuj_pozycje(_squad())
    assert "xabi alonso" not in poz


def test_nazwiska_sa_kluczami_znormalizowanymi():
    """Diakrytyki rozjezdzaja sie miedzy zrodlami — klucz musi je zdejmowac."""
    poz = fm.parsuj_pozycje(_squad())
    assert "moises caicedo" in poz
    assert "enzo fernandez" in poz


def test_nieznana_grupa_jest_pomijana_bez_wybuchu():
    dane = {"squad": {"squad": [
        {"title": "loaned_out", "members": [{"name": "Ktos Tam"}]},
        {"title": "attackers", "members": [{"name": "Strzelec Jeden"}]},
    ]}}
    poz = fm.parsuj_pozycje(dane)
    assert poz == {"strzelec jeden": "F"}


def test_pusty_sklad_daje_pusty_slownik():
    assert fm.parsuj_pozycje({}) == {}
    assert fm.parsuj_pozycje({"squad": {"squad": []}}) == {}


def test_smieci_w_czlonkach_nie_wywracaja_parsera():
    dane = {"squad": {"squad": [
        {"title": "defenders", "members": [None, "bzdura", {}, {"name": ""},
                                           {"name": "Obronca Jeden"}]},
    ]}}
    assert fm.parsuj_pozycje(dane) == {"obronca jeden": "D"}


# ── pobieranie z cache ──────────────────────────────────────────────────────

def test_sklad_pobierany_raz_na_druzyne(monkeypatch):
    """Dwa mecze tej samej druzyny w jednym przebiegu to jeden request."""
    wolania = []

    def _stub(sciezka, **params):
        wolania.append(params.get("id"))
        return _squad()

    monkeypatch.setattr(fm, "_pobierz", _stub)
    zrodlo = fm.FotMobTeamNews()

    zrodlo.pozycje_druzyny(8455)
    zrodlo.pozycje_druzyny(8455)
    zrodlo.pozycje_druzyny(8456)

    assert wolania == [8455, 8456], f"nadmiarowe requesty: {wolania}"


def test_blad_skladu_nie_wywraca_przebiegu(monkeypatch):
    """Brak pozycji degraduje korekte do jednostronnej — nie zatrzymuje potoku."""
    import requests

    def _wybuch(sciezka, **params):
        raise requests.RequestException("timeout")

    monkeypatch.setattr(fm, "_pobierz", _wybuch)
    assert fm.FotMobTeamNews().pozycje_druzyny(8455) == {}


def test_brak_id_druzyny_nie_wola_sieci(monkeypatch):
    def _nie_wolno(*a, **k):
        raise AssertionError("request mimo braku id druzyny")

    monkeypatch.setattr(fm, "_pobierz", _nie_wolno)
    assert fm.FotMobTeamNews().pozycje_druzyny(None) == {}


# ── pozycje trafiaja do absencji ────────────────────────────────────────────

def _dzien():
    return json.loads((_FIKS / "matches_day.json").read_text(encoding="utf-8"))


def _mecz():
    return json.loads((_FIKS / "match_predicted.json").read_text(encoding="utf-8"))


def test_absencje_dostaja_pozycje_ze_skladu(monkeypatch):
    monkeypatch.setattr(fm, "_PRZERWA_S", 0.0)
    monkeypatch.setattr(fm, "_pobierz", lambda s, **p: (
        _dzien() if s == "matches" else _mecz() if s == "matchDetails" else _squad()))

    wynik = fm.FotMobTeamNews().fetch_dla("2026-08-30", None)
    absencje = [a for t in wynik for a in t.absencje_home]

    assert absencje, "fikstura nie ma absencji gospodarza"
    # Fikstura skladu to Chelsea — jej absencje maja sie dopasowac.
    assert any(a.pozycja for a in absencje), "zadna absencja nie dostala pozycji"
    assert all(a.pozycja in (None, "G", "D", "M", "F") for a in absencje)


def test_sklad_NIE_jest_pobierany_gdy_mecz_nie_ma_absencji(monkeypatch):
    """Dwa dodatkowe requesty na mecz to koszt, ktory ma sens tylko wtedy,
    gdy jest kogo sklasyfikowac."""
    monkeypatch.setattr(fm, "_PRZERWA_S", 0.0)
    mecz = _mecz()
    mecz["content"]["lineup"]["homeTeam"]["unavailable"] = []
    mecz["content"]["lineup"]["awayTeam"]["unavailable"] = []
    sciezki = []

    def _stub(s, **p):
        sciezki.append(s)
        return _dzien() if s == "matches" else mecz if s == "matchDetails" else _squad()

    monkeypatch.setattr(fm, "_pobierz", _stub)
    fm.FotMobTeamNews().fetch_dla("2026-08-30", None)

    assert "teams" not in sciezki, "pobrano sklad mimo braku absencji"


def test_awaria_skladu_zostawia_absencje_bez_pozycji(monkeypatch):
    """Degradacja do korekty jednostronnej, nie utrata absencji."""
    monkeypatch.setattr(fm, "_PRZERWA_S", 0.0)
    import requests

    def _stub(s, **p):
        if s == "teams":
            raise requests.RequestException("timeout")
        return _dzien() if s == "matches" else _mecz()

    monkeypatch.setattr(fm, "_pobierz", _stub)
    wynik = fm.FotMobTeamNews().fetch_dla("2026-08-30", None)

    absencje = [a for t in wynik for a in t.absencje_home + t.absencje_away]
    assert absencje, "absencje zniknely przez awarie skladu"
    assert all(a.pozycja is None for a in absencje)
