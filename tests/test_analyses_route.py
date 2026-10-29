"""
test_analyses_route.py — endpoint Analizy meczowe: filtr ważnych lig + budowa kart
z eventów Bzzoiro. Bez sieci/DB (mock player_db).
"""
import pytest

from footstats.api.routes import analyses


@pytest.fixture(autouse=True)
def _bez_fotmoba(monkeypatch):
    """Skład z FotMob = sieć; domyślnie "nie wiemy" (None) → karta bez filtra."""
    monkeypatch.setattr(analyses.sklad_fotmob, "aktualny_sklad", lambda n: None)
    monkeypatch.setattr(analyses.sklad_fotmob, "przygotuj_sklady", lambda n: None)


_EVENTS = [
    {"gosp": "France", "gosc": "Egypt", "liga": "World Cup 2026", "data": "2026-07-08",
     "pred_ml": {"prob_home_win": 56, "prob_draw": 24, "prob_away_win": 20,
                 "prob_over_25": 54, "prob_btts_yes": 54}, "odds": {"home": 1.4}},
    {"gosp": "Foo", "gosc": "Bar", "liga": "Botola Pro",   # nieważna liga → odpada
     "data": "2026-07-08", "pred_ml": {"prob_home_win": 40}},
]


def test_build_cards_filtruje_wazne(monkeypatch):
    monkeypatch.setattr(analyses, "get_team_stats",
                        lambda t, s: {"matches": 3, "goals_for": 10, "goals_against": 2,
                                      "avg_rating": 7.16} if t == "France" else None)
    monkeypatch.setattr(analyses, "team_goal_shares_recent_z_sezonem", lambda t, s: (None, {}))
    cards = analyses._build_cards(_EVENTS)
    assert len(cards) == 1                       # tylko World Cup, Botola odpada
    c = cards[0]
    assert c["home"] == "France" and c["host"] == "France"
    assert abs(c["home_stats"]["gf_pg"] - 10 / 3) < 0.01


def test_karta_bez_predykcji_i_kursow(monkeypatch):
    """Decyzja 10.09: zakładka to statystyki drużyn — event niesie `pred_ml`
    i `odds`, ale do odpowiedzi nie może trafić żadne z nich."""
    monkeypatch.setattr(analyses, "get_team_stats", lambda t, s: None)
    monkeypatch.setattr(analyses, "team_goal_shares_recent_z_sezonem", lambda t, s: (None, {}))

    [c] = analyses._build_cards(_EVENTS)

    assert "model" not in c and "odds" not in c
    tekst = repr(c)
    for klucz in ("prob_", "'pw'", "'o25'", "'bt'"):
        assert klucz not in tekst, f"w karcie zostało pole predykcji: {klucz}"


def test_wazna_liga():
    assert analyses._wazna("Premier League") is True
    assert analyses._wazna("World Cup 2026") is True
    assert analyses._wazna("PKO BP Ekstraklasa") is True
    assert analyses._wazna("Botola Pro") is False


# ── J2: typy zlapaly realny przypadek, nie kosmetyke ────────────────────────

def test_mecz_bez_nazw_druzyn_jest_pomijany_a_nie_odpytywany_z_None():
    """Znalezione mypy po naprawie `python_version` (J2), nie recznym czytaniem.

    `m.get("gosp")` i `m.get("gosc")` moga byc None, a `get_team_stats`
    i `team_goal_shares_recent` przyjmuja `str`. Zdarzenie bez nazw druzyn
    szlo wiec do wyszukiwania statystyk jako None — a karta meczu bez nazw
    i tak jest bezuzyteczna. Pomijamy je i mowimy o tym w logu.
    """
    from footstats.api.routes import analyses

    zdarzenia = [
        {"liga": "Premier League", "gosp": None, "gosc": "Chelsea", "pred_ml": {}},
        {"liga": "Premier League", "gosp": "Arsenal", "gosc": None, "pred_ml": {}},
        {"liga": "Premier League", "gosp": "", "gosc": "", "pred_ml": {}},
    ]
    assert analyses._build_cards(zdarzenia) == []


def test_mecz_z_kompletem_nazw_dalej_buduje_karte(monkeypatch):
    """Kontrola pozytywna — bramka nie moze odsiac poprawnych meczow."""
    from footstats.api.routes import analyses

    monkeypatch.setattr(analyses, "get_team_stats", lambda *a, **k: {})
    monkeypatch.setattr(analyses, "team_goal_shares_recent_z_sezonem", lambda *a, **k: (None, {}))
    monkeypatch.setattr(analyses, "build_match_card", lambda *a, **k: {"ok": True, "home_stats": {"gf_pg": 1}, "away_stats": {"gf_pg": 1}})

    karty = analyses._build_cards(
        [{"liga": "Premier League", "gosp": "Arsenal", "gosc": "Chelsea", "pred_ml": {}}]
    )
    assert len(karty) == 1


def test_dzis_i_jutro_odcina_reszte_tygodnia_i_sortuje():
    """25.10: po paginacji Bzzoiro tydzien to ~100 waznych meczow, a kazda karta
    to 4 zapytania do DB przy timeoucie middleware 10 s — bierzemy dzis+jutro."""
    from datetime import date

    ev = [
        {"gosp": "C", "gosc": "D", "data": "2026-10-26", "godzina": "18:00"},
        {"gosp": "E", "gosc": "F", "data": "2026-10-29", "godzina": "18:00"},
        {"gosp": "A", "gosc": "B", "data": "2026-10-25", "godzina": "20:00"},
        {"gosp": "G", "gosc": "H", "data": "2026-10-24", "godzina": "20:00"},
        {"gosp": "I", "gosc": "J", "data": "2026-10-25", "godzina": "15:00"},
    ]
    wynik = analyses._na_dzis_i_jutro(ev, date(2026, 10, 25))

    assert [m["gosp"] for m in wynik] == ["I", "A", "C"]


# ── Wyszukiwarka + ukrywanie meczów rozpoczętych ────────────────────────────

def _ev(gosp, gosc, liga, dni=0, godz=3, status=None):
    """Event Bzzoiro w przyszłości (godz. od teraz) lub przeszłości (ujemne)."""
    from datetime import datetime, timedelta, timezone
    t = datetime.now(timezone.utc) + timedelta(days=dni, hours=godz)
    ev = {"gosp": gosp, "gosc": gosc, "liga": liga,
          "data": t.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Warsaw")).date().isoformat(),
          "godzina": t.strftime("%H:%M"), "data_full": t.isoformat()}
    if status:
        ev["status"] = status
    return ev


def _wywolaj(monkeypatch, events, q=None):
    import sys
    import types

    class _Klient:
        def __init__(self, *_a, **_k): ...
        def predykcje_tygodnia(self):
            return events

    modul = types.ModuleType("footstats.scrapers.bzzoiro")
    modul.BzzoiroClient = _Klient
    monkeypatch.setitem(sys.modules, "footstats.scrapers.bzzoiro", modul)
    monkeypatch.setenv("BZZOIRO_KEY", "x")
    monkeypatch.setattr(analyses, "get_team_stats", lambda *a, **k: {})
    monkeypatch.setattr(analyses, "team_goal_shares_recent_z_sezonem", lambda *a, **k: (None, {}))
    monkeypatch.setattr(analyses, "build_match_card",
                        lambda match, **k: {"home": match["gospodarz"], "away": match["goscie"],
                                            "liga": match["liga"], "data": match["data"],
                                            "home_stats": {"gf_pg": 1}, "away_stats": {"gf_pg": 1}})
    return analyses.analyses_matches(user_id=1, q=q)["matches"]


def test_zakonczony_i_rozpoczety_nie_pojawiaja_sie(monkeypatch):
    events = [
        _ev("Arsenal", "Chelsea", "Premier League", godz=3),
        _ev("Jagiellonia", "Wisla Plock", "Ekstraklasa", godz=1, status="finished"),
        _ev("Liverpool", "Everton", "Premier League", godz=-1),
    ]
    homes = [c["home"] for c in _wywolaj(monkeypatch, events)]
    assert homes == ["Arsenal"]


def test_q_szuka_w_calym_tygodniu_i_poza_waznymi_ligami(monkeypatch):
    events = [
        _ev("Arsenal", "Chelsea", "Premier League", dni=0, godz=3),
        _ev("Raja", "Wydad", "Botola Pro", dni=5, godz=2),
    ]
    assert [c["home"] for c in _wywolaj(monkeypatch, events)] == ["Arsenal"]
    assert [c["home"] for c in _wywolaj(monkeypatch, events, q="wydad")] == ["Raja"]


def test_q_ignoruje_diakrytyki_i_szuka_w_lidze(monkeypatch):
    events = [
        _ev("Jagiellonia Białystok", "Wisła Płock", "Ekstraklasa", dni=2, godz=2),
        _ev("Arsenal", "Chelsea", "Premier League", dni=1, godz=2),
    ]
    assert len(_wywolaj(monkeypatch, events, q="wisla")) == 1
    assert len(_wywolaj(monkeypatch, events, q="BIALYSTOK")) == 1
    assert len(_wywolaj(monkeypatch, events, q="premier")) == 1


def test_q_limit_20_wynikow_posortowane(monkeypatch):
    events = [_ev(f"Klub{i} FC", "Rywal", "Botola Pro", dni=1, godz=i % 5 + 1) for i in range(30)]
    wynik = _wywolaj(monkeypatch, events, q="klub")
    assert len(wynik) == analyses._MAX_WYNIKOW_SZUKANIA == 20


def test_q_jednoznakowe_to_widok_domyslny(monkeypatch):
    events = [
        _ev("Arsenal", "Chelsea", "Premier League", dni=0, godz=3),
        _ev("Raja", "Wydad", "Botola Pro", dni=5, godz=2),
    ]
    assert [c["home"] for c in _wywolaj(monkeypatch, events, q=" a ")] == ["Arsenal"]


def test_czas_meczu_przeniesiony_dziala_jak_w_kreatorze():
    from datetime import datetime, timezone
    from footstats.core.czas_meczu import juz_sie_zaczal, moment_meczu
    teraz = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    assert juz_sie_zaczal({"status": "FT"}, teraz) is True
    assert juz_sie_zaczal({"data_full": "2026-10-25T13:00:00Z"}, teraz) is False
    assert moment_meczu({}) is None


# ── 25.10: godzina meczu w Europe/Warsaw + gole z historii gdy team_stats puste ──

def test_godzina_warszawska_czas_letni():
    # 2026-10-24: jeszcze CEST (UTC+2) — 18:00 UTC to 20:00 w Warszawie
    assert analyses._start_warszawa({"data": "2026-10-24", "godzina": "18:00"}) == ("2026-10-24", "20:00")


def test_godzina_warszawska_czas_zimowy_i_zmiana_dnia():
    # 2026-10-31 CET (UTC+1) po zmianie czasu 25.10; 23:30 UTC -> 00:30 nastepnego dnia
    assert analyses._start_warszawa({"data": "2026-10-31", "godzina": "19:00"}) == ("2026-10-31", "20:00")
    assert analyses._start_warszawa({"data": "2026-10-31", "godzina": "23:30"}) == ("2026-11-01", "00:30")


def test_godzina_brak_lub_nieczytelna_to_none():
    assert analyses._start_warszawa({"data": "2026-10-31"}) == (None, None)
    assert analyses._start_warszawa({"data": "x", "godzina": "y"}) == (None, None)


def test_karta_ma_godzine(monkeypatch):
    monkeypatch.setattr(analyses, "get_team_stats", lambda t, s: None)
    monkeypatch.setattr(analyses, "team_goal_shares_recent_z_sezonem", lambda t, s: (None, {}))
    monkeypatch.setattr(analyses, "_zbior", lambda: None)
    ev = [{"gosp": "A", "gosc": "B", "liga": "Premier League", "data": "2026-10-31", "godzina": "19:00"}]
    [c] = analyses._build_cards(ev)
    assert c["godzina"] == "20:00" and c["data_pl"] == "2026-10-31"


def test_gole_z_historii_gdy_brak_team_stats(monkeypatch):
    monkeypatch.setattr(analyses, "get_team_stats", lambda t, s: None)
    monkeypatch.setattr(analyses, "team_goal_shares_recent_z_sezonem", lambda t, s: (None, {}))
    monkeypatch.setattr(analyses, "_zbior", lambda: object())
    monkeypatch.setattr(
        analyses.opis_meczu, "forma",
        lambda df, t: {"gole_strzelone_sr10": 1.8, "gole_stracone_sr10": 0.9, "mecze_w_sredniej": 10}
        if t == "A" else None)
    ev = [{"gosp": "A", "gosc": "B", "liga": "Premier League", "data": "2026-10-31"}]
    [c] = analyses._build_cards(ev)
    assert c["home_stats"]["gf_pg"] == 1.8 and c["home_stats"]["ga_pg"] == 0.9
    assert c["home_stats"]["matches"] == 10
    assert c["away_stats"]["gf_pg"] is None          # brak w historii = brak, bez zmyślania


def test_team_stats_ma_pierwszenstwo_przed_historia(monkeypatch):
    monkeypatch.setattr(analyses, "get_team_stats",
                        lambda t, s: {"matches": 4, "goals_for": 8, "goals_against": 4})
    monkeypatch.setattr(analyses, "team_goal_shares_recent_z_sezonem", lambda t, s: (None, {}))
    monkeypatch.setattr(analyses, "_zbior", lambda: pytest.fail("nie powinno ladowac zbioru"))
    ev = [{"gosp": "A", "gosc": "B", "liga": "Premier League", "data": "2026-10-31"}]
    [c] = analyses._build_cards(ev)
    assert c["home_stats"]["gf_pg"] == 2.0


# ── strzelcy z poprzedniego sezonu: uczciwy podpis na karcie ────────────────

def _karta_z_udzialami(monkeypatch, odpowiedz):
    monkeypatch.setattr(analyses, "get_team_stats", lambda t, s: None)
    monkeypatch.setattr(analyses, "team_goal_shares_recent_z_sezonem",
                        lambda *a, **k: odpowiedz)
    [c] = analyses._build_cards(_EVENTS)
    return c


def test_karta_flaga_gdy_udzialy_z_poprzedniego_sezonu(monkeypatch):
    c = _karta_z_udzialami(monkeypatch, (2025, {"Lewandowski": 0.3}))
    assert c["strzelcy_poprzedni_sezon"] is True


def test_karta_bez_flagi_gdy_udzialy_z_biezacego_sezonu(monkeypatch):
    c = _karta_z_udzialami(monkeypatch, (analyses._SEASON, {"Lewandowski": 0.3}))
    assert c["strzelcy_poprzedni_sezon"] is False


def test_karta_bez_flagi_gdy_brak_strzelcow(monkeypatch):
    c = _karta_z_udzialami(monkeypatch, (None, {}))
    assert c["strzelcy_poprzedni_sezon"] is False


def test_strzelcy_na_karcie_tylko_z_obecnego_skladu(monkeypatch):
    monkeypatch.setattr(analyses, "get_team_stats", lambda t, s: None)
    monkeypatch.setattr(analyses, "team_goal_shares_recent_z_sezonem",
                        lambda *a, **k: (2025, {"R. Lewandowski": 0.12, "L. Yamal": 0.2}))
    monkeypatch.setattr(analyses.sklad_fotmob, "aktualny_sklad",
                        lambda n: frozenset({"lamine yamal"}))
    c = analyses._build_cards([_EVENTS[0]])[0]
    assert [x["name"] for x in c["top_scorers_home"]] == ["L. Yamal"]
    # skład znany => dane zweryfikowane, bez podpisu "poprzedni sezon"
    assert c["strzelcy_poprzedni_sezon"] is False


def test_flaga_poprzedni_sezon_zostaje_gdy_sklad_nieznany(monkeypatch):
    monkeypatch.setattr(analyses, "get_team_stats", lambda t, s: None)
    monkeypatch.setattr(analyses, "team_goal_shares_recent_z_sezonem",
                        lambda *a, **k: (2025, {"R. Lewandowski": 0.12}))
    c = analyses._build_cards([_EVENTS[0]])[0]     # autouse: aktualny_sklad -> None
    assert c["strzelcy_poprzedni_sezon"] is True
