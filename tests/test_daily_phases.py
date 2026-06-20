"""
test_daily_phases.py — testy czystych helperów wydzielonych z daily_agent.py
do core/daily_phases.py (dług techniczny #3, behavior-preserving refactor).
"""
from footstats.core.daily_phases import _dodaj_kelly, _wzbogac_o_kursy_fallback


def _no_calibration(monkeypatch):
    """Mock kalibracji — neutralny multiplier, brak zapytań do DB (zero touch prod)."""
    import footstats.core.calibration as cal
    monkeypatch.setattr(cal, "get_stake_multiplier", lambda *a, **k: 1.0)
    monkeypatch.setattr(cal, "calibration_summary", lambda *a, **k: {"n": 0})


def test_dodaj_kelly_dodaje_stawke_do_kuponu(monkeypatch):
    _no_calibration(monkeypatch)
    dane = {"kupon_a": {"zdarzenia": [{"pewnosc_pct": 65, "kurs": 2.10}]}}
    _dodaj_kelly(dane, bankroll=200.0)
    z = dane["kupon_a"]["zdarzenia"][0]
    assert "kelly_stake" in z
    assert z["kelly_stake"] >= 0.0


def test_dodaj_kelly_dodaje_stawke_do_top3(monkeypatch):
    _no_calibration(monkeypatch)
    dane = {"top3": [{"pewnosc_pct": 70, "kurs": 1.85}]}
    _dodaj_kelly(dane, bankroll=200.0)
    assert "kelly_stake" in dane["top3"][0]


def test_dodaj_kelly_brak_edge_zwraca_zero(monkeypatch):
    _no_calibration(monkeypatch)
    # Niska pewność vs wysoki kurs wymagany — brak edge
    dane = {"kupon_a": {"zdarzenia": [{"pewnosc_pct": 20, "kurs": 1.3}]}}
    _dodaj_kelly(dane, bankroll=200.0)
    assert dane["kupon_a"]["zdarzenia"][0]["kelly_stake"] == 0.0


def test_dodaj_kelly_nieprawidlowy_bankroll_uzywa_fallback(monkeypatch):
    """Bankroll None/ujemny (np. z DB) nie crashuje — fallback do AGENT_BANKROLL."""
    _no_calibration(monkeypatch)
    dane = {"kupon_a": {"zdarzenia": [{"pewnosc_pct": 65, "kurs": 2.0}]}}
    _dodaj_kelly(dane, bankroll=None)
    assert "kelly_stake" in dane["kupon_a"]["zdarzenia"][0]


def test_dodaj_kelly_brak_kuponow_nie_crashuje(monkeypatch):
    _no_calibration(monkeypatch)
    dane = {}
    _dodaj_kelly(dane, bankroll=200.0)  # nie powinno rzucić
    assert dane == {}


# ── _wzbogac_o_kursy_fallback (D6/D1b — SofaScore fallback kursów) ────────────

def _mock_sofa_session(monkeypatch):
    """Mock sesji Playwright — nie odpala realnej przeglądarki."""

    class _FakeBrowser:
        def close(self):
            pass

    class _FakeP:
        def stop(self):
            pass

    monkeypatch.setattr(
        "footstats.scrapers.form_scraper._sofa_session",
        lambda: (_FakeP(), _FakeBrowser(), object()),
    )


def _no_af(monkeypatch):
    """Mock AF fallback — zawsze None, żeby testy Sofascore nie zależały od AF/sieci."""
    import footstats.core.daily_phases as dp_mod
    monkeypatch.setattr(dp_mod, "fetch_odds_af", lambda home, away, data: None)


def test_fallback_uzupelnia_gdy_odds_puste(monkeypatch):
    import footstats.scrapers.sofascore_odds as so_mod

    _no_af(monkeypatch)
    monkeypatch.setattr(so_mod, "PLAYWRIGHT_OK", True)
    _mock_sofa_session(monkeypatch)
    monkeypatch.setattr(
        so_mod, "fetch_odds",
        lambda home, away, data, page=None: {"home": 1.5, "draw": 3.5, "away": 4.5},
    )

    wyniki = [{"gospodarz": "Real Madrid", "goscie": "Barcelona", "data": "2026-06-21", "odds": {}}]
    _wzbogac_o_kursy_fallback(wyniki)

    assert wyniki[0]["odds"] == {"home": 1.5, "draw": 3.5, "away": 4.5}


def test_fallback_pomija_gdy_bzzoiro_juz_ma_kursy(monkeypatch):
    import footstats.scrapers.sofascore_odds as so_mod

    _no_af(monkeypatch)
    monkeypatch.setattr(so_mod, "PLAYWRIGHT_OK", True)
    _mock_sofa_session(monkeypatch)

    calls = []
    monkeypatch.setattr(
        so_mod, "fetch_odds",
        lambda home, away, data, page=None: calls.append((home, away)) or {"home": 9.9},
    )

    wyniki = [{
        "gospodarz": "Real Madrid", "goscie": "Barcelona", "data": "2026-06-21",
        "odds": {"home": 1.5, "draw": 3.5, "away": 4.5},
    }]
    _wzbogac_o_kursy_fallback(wyniki)

    assert wyniki[0]["odds"] == {"home": 1.5, "draw": 3.5, "away": 4.5}  # niezmienione
    assert calls == []  # fetch_odds nie wywołany


def test_fallback_nie_nadpisuje_istniejacych_kluczy_tylko_dopisuje_brakujace(monkeypatch):
    import footstats.scrapers.sofascore_odds as so_mod

    _no_af(monkeypatch)
    monkeypatch.setattr(so_mod, "PLAYWRIGHT_OK", True)
    _mock_sofa_session(monkeypatch)
    monkeypatch.setattr(
        so_mod, "fetch_odds",
        lambda home, away, data, page=None: {"home": 1.1, "draw": 3.5, "away": 4.5, "btts": 1.8},
    )

    # Niekompletne kursy: brak 'away' -> kwalifikuje się do fallbacku
    wyniki = [{
        "gospodarz": "Real Madrid", "goscie": "Barcelona", "data": "2026-06-21",
        "odds": {"home": 1.5, "draw": 3.5},
    }]
    _wzbogac_o_kursy_fallback(wyniki)

    # 'home' z Bzzoiro (1.5) NIE jest nadpisany kursem SofaScore (1.1)
    assert wyniki[0]["odds"]["home"] == 1.5
    assert wyniki[0]["odds"]["away"] == 4.5
    assert wyniki[0]["odds"]["btts"] == 1.8


def test_fallback_brak_playwright_nie_crashuje(monkeypatch):
    import footstats.scrapers.sofascore_odds as so_mod
    _no_af(monkeypatch)
    monkeypatch.setattr(so_mod, "PLAYWRIGHT_OK", False)

    wyniki = [{"gospodarz": "A", "goscie": "B", "data": "2026-06-21", "odds": {}}]
    _wzbogac_o_kursy_fallback(wyniki)  # nie powinno rzucić
    assert wyniki[0]["odds"] == {}


def test_fallback_brak_meczow_do_uzupelnienia_nie_woła_sesji(monkeypatch):
    import footstats.scrapers.sofascore_odds as so_mod

    _no_af(monkeypatch)
    monkeypatch.setattr(so_mod, "PLAYWRIGHT_OK", True)

    def _should_not_be_called():
        raise AssertionError("sesja Playwright nie powinna być tworzona gdy brak braków")

    monkeypatch.setattr(
        "footstats.scrapers.form_scraper._sofa_session", lambda: _should_not_be_called()
    )

    wyniki = [{
        "gospodarz": "A", "goscie": "B", "data": "2026-06-21",
        "odds": {"home": 1.5, "draw": 3.5, "away": 4.5},
    }]
    _wzbogac_o_kursy_fallback(wyniki)  # nie powinno rzucić / nie powinno wołać sesji


# ── Fallback kursów: AF jako PRIORYTET, SofaScore jako 2. fallback (D1b) ──────

def test_fallback_af_uzupelnia_najpierw_sofascore_nie_wolane(monkeypatch):
    """Gdy AF zwraca komplet kursów — Sofascore (scraper, anti-bot ryzyko) nie jest wołany."""
    import footstats.core.daily_phases as dp_mod

    monkeypatch.setattr(
        dp_mod, "fetch_odds_af",
        lambda home, away, data: {"home": 1.6, "draw": 3.4, "away": 4.2},
    )

    so_calls = []
    import footstats.scrapers.sofascore_odds as so_mod
    monkeypatch.setattr(so_mod, "PLAYWRIGHT_OK", True)
    monkeypatch.setattr(
        so_mod, "fetch_odds",
        lambda home, away, data, page=None: so_calls.append((home, away)) or {},
    )
    _mock_sofa_session(monkeypatch)

    wyniki = [{"gospodarz": "Real Madrid", "goscie": "Barcelona", "data": "2026-06-21", "odds": {}}]
    _wzbogac_o_kursy_fallback(wyniki)

    assert wyniki[0]["odds"] == {"home": 1.6, "draw": 3.4, "away": 4.2}
    assert so_calls == []  # Sofascore NIE wywołany — AF wystarczyło


def test_fallback_sofascore_jako_drugi_fallback_gdy_af_none(monkeypatch):
    """Gdy AF nie znajdzie kursów (None) — Sofascore próbuje jako 2. fallback."""
    import footstats.core.daily_phases as dp_mod

    monkeypatch.setattr(dp_mod, "fetch_odds_af", lambda home, away, data: None)

    import footstats.scrapers.sofascore_odds as so_mod
    monkeypatch.setattr(so_mod, "PLAYWRIGHT_OK", True)
    monkeypatch.setattr(
        so_mod, "fetch_odds",
        lambda home, away, data, page=None: {"home": 1.5, "draw": 3.5, "away": 4.5},
    )
    _mock_sofa_session(monkeypatch)

    wyniki = [{"gospodarz": "Real Madrid", "goscie": "Barcelona", "data": "2026-06-21", "odds": {}}]
    _wzbogac_o_kursy_fallback(wyniki)

    assert wyniki[0]["odds"] == {"home": 1.5, "draw": 3.5, "away": 4.5}


def test_fallback_af_czesciowe_kursy_dopelniane_przez_sofascore(monkeypatch):
    """AF daje tylko część 1X2 (brak 'away') — Sofascore dopełnia resztę, bez nadpisywania."""
    import footstats.core.daily_phases as dp_mod

    monkeypatch.setattr(
        dp_mod, "fetch_odds_af",
        lambda home, away, data: {"home": 1.6, "draw": 3.4},
    )

    import footstats.scrapers.sofascore_odds as so_mod
    monkeypatch.setattr(so_mod, "PLAYWRIGHT_OK", True)
    monkeypatch.setattr(
        so_mod, "fetch_odds",
        lambda home, away, data, page=None: {"home": 9.9, "away": 4.2, "btts": 1.8},
    )
    _mock_sofa_session(monkeypatch)

    wyniki = [{"gospodarz": "Real Madrid", "goscie": "Barcelona", "data": "2026-06-21", "odds": {}}]
    _wzbogac_o_kursy_fallback(wyniki)

    odds = wyniki[0]["odds"]
    assert odds["home"] == 1.6  # AF, nie nadpisany przez Sofascore (9.9)
    assert odds["draw"] == 3.4
    assert odds["away"] == 4.2  # dopełnione przez Sofascore (AF nie znalazł)
    assert odds["btts"] == 1.8  # dopełnione przez Sofascore


def test_fallback_af_brak_klucza_nie_crashuje_idzie_do_sofascore(monkeypatch):
    """fetch_odds_af zwraca None (brak klucza) — pipeline kontynuuje do Sofascore bez wyjątku."""
    import footstats.core.daily_phases as dp_mod

    monkeypatch.setattr(dp_mod, "fetch_odds_af", lambda home, away, data: None)

    import footstats.scrapers.sofascore_odds as so_mod
    monkeypatch.setattr(so_mod, "PLAYWRIGHT_OK", True)
    monkeypatch.setattr(so_mod, "fetch_odds", lambda home, away, data, page=None: None)
    _mock_sofa_session(monkeypatch)

    wyniki = [{"gospodarz": "A", "goscie": "B", "data": "2026-06-21", "odds": {}}]
    _wzbogac_o_kursy_fallback(wyniki)  # nie powinno rzucić
    assert wyniki[0]["odds"] == {}
