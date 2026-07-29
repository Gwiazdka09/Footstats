"""test_fixtures_fallback.py — awaryjne źródło meczów gdy Bzzoiro padnie.

Bzzoiro było single point of failure: brak klucza / 503 → cloud_draft zwracał
{"ok": False} i cały dzienny draft ginął. Fallback bierze fixtures z API-Football,
a prawdopodobieństwa liczy Poisson (fallback NIE ma ramienia ML).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import footstats.core.cloud_draft as cd
from footstats.scrapers.bzzoiro import ENV_BZZOIRO
from footstats.scrapers.fixtures_fallback import FixturesFallbackClient

# ── fixture API-Football (kształt realnej odpowiedzi /fixtures) ───────────────

_AF_FIXTURE = {
    "fixture": {
        "id": 123,
        "date": "2026-08-01T18:30:00+02:00",
        "status": {"short": "NS"},
    },
    "league": {"name": "Premier League"},
    "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
}


def _klient_af(response: list) -> MagicMock:
    af = MagicMock()
    af._get.return_value = {"response": response}
    return af


# ── FixturesFallbackClient ───────────────────────────────────────────────────


def test_mapuje_fixture_na_schemat_bzzoiro():
    """Fixture AF → dict o kluczach, których oczekuje szybkie_pewniaczki_2dni."""
    klient = FixturesFallbackClient(klient_af=_klient_af([_AF_FIXTURE]), dni=1)
    ok, _ = klient.waliduj()
    assert ok is True and klient._valid is True

    mecze = klient.predykcje_tygodnia()
    assert len(mecze) == 1
    m = mecze[0]
    assert m["gosp"] == "Arsenal"
    assert m["gosc"] == "Chelsea"
    assert m["liga"] == "Premier League"
    assert m["data"] == "2026-08-01"
    assert m["godzina"] == "18:30"
    assert m["status"] == "notstarted"
    # Fallback nie ma modelu ML — prawdopodobieństwa dołoży Poisson.
    assert m.get("pred_ml") is None


def test_pomija_fixture_bez_druzyn():
    """Brak nazwy drużyny → mecz odrzucony, reszta przechodzi."""
    zepsuty = {
        "fixture": {"date": "2026-08-01T18:30:00+02:00", "status": {"short": "NS"}},
        "league": {"name": "X"},
        "teams": {"home": {"name": ""}, "away": {"name": "B"}},
    }
    klient = FixturesFallbackClient(klient_af=_klient_af([zepsuty, _AF_FIXTURE]), dni=1)
    assert len(klient.predykcje_tygodnia()) == 1


def test_pomija_mecze_juz_rozegrane():
    """Status inny niż zaplanowany → mecz nie trafia do draftu."""
    skonczony = {
        "fixture": {"date": "2026-08-01T18:30:00+02:00", "status": {"short": "FT"}},
        "league": {"name": "X"},
        "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
    }
    klient = FixturesFallbackClient(klient_af=_klient_af([skonczony]))
    assert klient.predykcje_tygodnia() == []


def test_brak_klucza_af_jest_graceful():
    """Bez klucza AF fallback jest nieaktywny — nie rzuca, zwraca pustą listę."""
    klient = FixturesFallbackClient(klient_af=None, klucz_af="")
    ok, msg = klient.waliduj()
    assert ok is False and klient._valid is False
    assert "APISPORTS" in msg
    assert klient.predykcje_tygodnia() == []


def test_blad_sieci_jest_graceful():
    """Wyjątek z klienta AF → pusta lista, nie wyjątek w górę."""
    af = MagicMock()
    af._get.side_effect = OSError("timeout")
    klient = FixturesFallbackClient(klient_af=af)
    assert klient.predykcje_tygodnia() == []


def test_pyta_af_o_kazdy_dzien_horyzontu():
    """dni=2 → dwa zapytania /fixtures (AF filtruje po konkretnej dacie)."""
    af = _klient_af([])
    klient = FixturesFallbackClient(klient_af=af, dni=2)
    klient.predykcje_tygodnia()
    assert af._get.call_count == 2
    assert all(c.args[0] == "/fixtures" for c in af._get.call_args_list)


# ── dołączanie kursów (fallback ich nie ma, a najlepszy_typ ich wymaga) ─────


def test_dolacz_kursy_uzupelnia_mecze_bez_kursow():
    """Bez kursów najlepszy_typ zwraca None → zero kuponów. Fallback musi je dociągnąć."""
    from footstats.scrapers.fixtures_fallback import dolacz_kursy

    wyniki = [
        {"gospodarz": "Arsenal", "goscie": "Chelsea", "data": "2026-08-01",
         "typy": [("1", 60.0)], "odds": {}},
    ]
    with patch("footstats.scrapers.api_football.fetch_odds_af",
               return_value={"home": 1.85, "draw": 3.4, "away": 4.2}) as mock_af:
        n = dolacz_kursy(wyniki, limit=5)

    assert n == 1
    assert wyniki[0]["odds"]["home"] == 1.85
    mock_af.assert_called_once_with("Arsenal", "Chelsea", "2026-08-01")


def test_dolacz_kursy_respektuje_limit_budzetu():
    """Budżet AF to 100 req/dzień, a 1 mecz = 2 zapytania → limit jest twardy."""
    from footstats.scrapers.fixtures_fallback import dolacz_kursy

    wyniki = [
        {"gospodarz": f"H{i}", "goscie": f"A{i}", "data": "2026-08-01",
         "typy": [("1", 50.0 + i)], "odds": {}}
        for i in range(10)
    ]
    with patch("footstats.scrapers.api_football.fetch_odds_af",
               return_value={"home": 1.9}) as mock_af:
        n = dolacz_kursy(wyniki, limit=3)

    assert n == 3
    assert mock_af.call_count == 3


def test_dolacz_kursy_bierze_najpewniejsze_najpierw():
    """Limitowany budżet ma iść na mecze z najwyższą pewnością, nie na pierwsze z brzegu."""
    from footstats.scrapers.fixtures_fallback import dolacz_kursy

    slaby = {"gospodarz": "Slaby", "goscie": "X", "data": "2026-08-01",
             "typy": [("1", 41.0)], "odds": {}}
    mocny = {"gospodarz": "Mocny", "goscie": "Y", "data": "2026-08-01",
             "typy": [("1", 78.0)], "odds": {}}
    wyniki = [slaby, mocny]

    with patch("footstats.scrapers.api_football.fetch_odds_af",
               return_value={"home": 1.9}) as mock_af:
        dolacz_kursy(wyniki, limit=1)

    assert mock_af.call_args[0][0] == "Mocny"
    assert mocny["odds"] and not slaby["odds"]


def test_dolacz_kursy_nie_nadpisuje_istniejacych():
    """Mecz który już ma kursy (ścieżka Bzzoiro) nie marnuje budżetu."""
    from footstats.scrapers.fixtures_fallback import dolacz_kursy

    wyniki = [{"gospodarz": "A", "goscie": "B", "data": "2026-08-01",
               "typy": [("1", 60.0)], "odds": {"home": 2.0}}]
    with patch("footstats.scrapers.api_football.fetch_odds_af") as mock_af:
        assert dolacz_kursy(wyniki, limit=5) == 0
    mock_af.assert_not_called()


def test_dolacz_kursy_graceful_gdy_af_padnie():
    """Błąd AF nie może wywalić draftu — mecz zostaje bez kursów."""
    from footstats.scrapers.fixtures_fallback import dolacz_kursy

    wyniki = [{"gospodarz": "A", "goscie": "B", "data": "2026-08-01",
               "typy": [("1", 60.0)], "odds": {}}]
    with patch("footstats.scrapers.api_football.fetch_odds_af",
               side_effect=OSError("timeout")):
        assert dolacz_kursy(wyniki, limit=5) == 0
    assert wyniki[0]["odds"] == {}


# ── wpięcie w cloud_draft ────────────────────────────────────────────────────


_WYNIKI = [
    {"gospodarz": "A", "goscie": "B", "liga": "ENG", "data": "2026-08-01", "odds": {"1": 1.8}},
]


class _BzzOK:
    def __init__(self, klucz):
        pass

    def waliduj(self):
        return (True, "ok")


class _BzzDown:
    def __init__(self, klucz):
        pass

    def waliduj(self):
        return (False, "503")


def _patch_wspolne(monkeypatch, fallback_valid=True):
    monkeypatch.setattr("footstats.core.quick_picks.szybkie_pewniaczki_2dni",
                        lambda klient, prog, godziny: list(_WYNIKI))
    monkeypatch.setattr("footstats.core.daily_filters._pre_filtruj_ligi", lambda w: list(w))
    monkeypatch.setattr("footstats.core.system_paper.najlepszy_typ", lambda w: (60.0, "1", 1.8))
    monkeypatch.setattr(cd, "_wykryj_model_source", lambda: "poisson-dc")
    monkeypatch.setattr(cd, "_swiezosc_danych_system",
                        lambda: {"stale_days": 0, "stale": False})

    class _Fallback:
        def __init__(self, *a, **k):
            self._valid = fallback_valid

        def waliduj(self):
            return (fallback_valid, "ok" if fallback_valid else "brak APISPORTS_KEY")

    monkeypatch.setattr("footstats.scrapers.fixtures_fallback.FixturesFallbackClient", _Fallback)


def test_bzzoiro_ok_nie_rusza_fallbacku(monkeypatch):
    """Ścieżka bez zmian gdy Bzzoiro żyje — fallback tylko awaryjny."""
    monkeypatch.setenv(ENV_BZZOIRO, "fake-key")
    monkeypatch.setattr("footstats.scrapers.bzzoiro.BzzoiroClient", _BzzOK)
    _patch_wspolne(monkeypatch)
    r = cd.generuj_system_draft(dni=2, dry_run=True)
    assert r["ok"] is True
    assert r["fixtures_source"] == "bzzoiro"


def test_brak_klucza_bzzoiro_uzywa_fallbacku(monkeypatch):
    """Brak BZZOIRO_API_KEY nie zabija draftu — wchodzi API-Football."""
    monkeypatch.delenv(ENV_BZZOIRO, raising=False)
    _patch_wspolne(monkeypatch)
    r = cd.generuj_system_draft(dni=2, dry_run=True)
    assert r["ok"] is True
    assert r["fixtures_source"] == "api-football-fallback"
    assert r["candidates"] == 1


def test_bzzoiro_niedostepne_uzywa_fallbacku(monkeypatch):
    """Bzzoiro odpowiada 503 → fallback zamiast {'ok': False}."""
    monkeypatch.setenv(ENV_BZZOIRO, "fake-key")
    monkeypatch.setattr("footstats.scrapers.bzzoiro.BzzoiroClient", _BzzDown)
    _patch_wspolne(monkeypatch)
    r = cd.generuj_system_draft(dni=2, dry_run=True)
    assert r["ok"] is True
    assert r["fixtures_source"] == "api-football-fallback"


def test_oba_zrodla_martwe_zwraca_blad(monkeypatch):
    """Gdy i Bzzoiro, i AF są martwe — uczciwy błąd, nie ciche zero kuponów."""
    monkeypatch.setenv(ENV_BZZOIRO, "fake-key")
    monkeypatch.setattr("footstats.scrapers.bzzoiro.BzzoiroClient", _BzzDown)
    _patch_wspolne(monkeypatch, fallback_valid=False)
    r = cd.generuj_system_draft(dni=2, dry_run=True)
    assert r["ok"] is False
    assert "fallback" in r["error"].lower()
