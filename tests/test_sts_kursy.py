"""Testy parsowania i dopasowania kursów STS (TD 15.3)."""
from footstats.scrapers.sts_kursy import (
    _jest_czasem,
    _match_score,
    _parsuj_kurs,
    _parsuj_mecz,
    oblicz_value,
    porownaj_z_predykcjami,
    znajdz_kurs,
)


# ── _parsuj_kurs ────────────────────────────────────────────────────────────

def test_parsuj_kurs_valid():
    assert _parsuj_kurs("2.85") == 2.85


def test_parsuj_kurs_comma():
    assert _parsuj_kurs("2,85") == 2.85


def test_parsuj_kurs_invalid():
    assert _parsuj_kurs("abc") is None


def test_parsuj_kurs_out_of_range():
    assert _parsuj_kurs("0.5") is None
    assert _parsuj_kurs("2000") is None


# ── _jest_czasem ──────────────────────────────────────────────────────────────

def test_jest_czasem_dash():
    assert _jest_czasem("-") is True


def test_jest_czasem_jutro_godzina():
    assert _jest_czasem("jutro, 4:00") is True


def test_jest_czasem_data_godzina():
    assert _jest_czasem("13.06.2026, 3:00") is True


def test_jest_czasem_godzina_only():
    assert _jest_czasem("4:00") is True


def test_jest_czasem_team_name():
    assert _jest_czasem("Real Madryt") is False


# ── _parsuj_mecz ────────────────────────────────────────────────────────────

def test_parsuj_mecz_basic():
    header = "Międzynarodowe, Mistrzostwa Świata\n+885"
    details = "Korea Południowa\nCzechy\njutro\n4:00"
    outcomes = ["1\n2.85", "X\n3.20", "2\n2.95"]

    mecz = _parsuj_mecz(header, details, outcomes)

    assert mecz["liga"] == "Międzynarodowe, Mistrzostwa Świata"
    assert mecz["team1"] == "Korea Południowa"
    assert mecz["team2"] == "Czechy"
    assert mecz["mecz"] == "Korea Południowa - Czechy"
    assert mecz["k1"] == 2.85
    assert mecz["kx"] == 3.20
    assert mecz["k2"] == 2.95


def test_parsuj_mecz_with_dash_separator():
    header = "USA, USL W League - kobiety\n+15"
    details = "Brooke House FC [K]\n-\nFC Miami City [K]\njutro, 0:00"
    outcomes = ["1\n2.02", "X\n4.00", "2\n2.85"]

    mecz = _parsuj_mecz(header, details, outcomes)

    assert mecz["team1"] == "Brooke House FC [K]"
    assert mecz["team2"] == "FC Miami City [K]"
    assert mecz["czas"] == "jutro, 0:00"


def test_parsuj_mecz_too_few_teams_returns_none():
    header = "Liga\n+1"
    details = "jutro\n4:00"
    outcomes = ["1\n2.0", "X\n3.0", "2\n4.0"]

    assert _parsuj_mecz(header, details, outcomes) is None


def test_parsuj_mecz_missing_outcome_label():
    header = "Liga\n+1"
    details = "Drużyna A\nDrużyna B\njutro\n4:00"
    outcomes = ["1\n2.0", "X\n3.0"]  # brak '2'

    mecz = _parsuj_mecz(header, details, outcomes)

    assert mecz["k1"] == 2.0
    assert mecz["kx"] == 3.0
    assert mecz["k2"] is None


# ── _match_score / znajdz_kurs ─────────────────────────────────────────────

def test_match_score_matching_teams():
    mecz = {"team1": "Real Madrid", "team2": "FC Barcelona"}
    assert _match_score(mecz, "Real Madryt", "Barcelona") >= 1


def test_match_score_no_match():
    mecz = {"team1": "Korea Południowa", "team2": "Czechy"}
    assert _match_score(mecz, "Liverpool", "Chelsea") == 0


def test_znajdz_kurs_finds_best_match():
    oferta = [
        {"team1": "Korea Południowa", "team2": "Czechy", "k1": 2.85, "kx": 3.20, "k2": 2.95},
        {"team1": "Real Madrid", "team2": "Barcelona", "k1": 2.10, "kx": 3.40, "k2": 3.30},
    ]
    wynik = znajdz_kurs("Real Madryt", "FC Barcelona", oferta)
    assert wynik is not None
    assert wynik["team1"] == "Real Madrid"


def test_znajdz_kurs_below_threshold_returns_none():
    oferta = [{"team1": "Korea Południowa", "team2": "Czechy", "k1": 2.85, "kx": 3.20, "k2": 2.95}]
    assert znajdz_kurs("Liverpool", "Chelsea", oferta) is None


# ── oblicz_value ─────────────────────────────────────────────────────────────

def test_oblicz_value_finds_value_bet():
    # Nasze p_wygrana=60% vs kurs 2.50 (implied=40%) -> EV=20
    wynik = oblicz_value(60.0, 25.0, 15.0, k1=2.50, kx=3.0, k2=6.0, prog_ev=5.0)
    assert "1" in wynik
    assert wynik["1"]["ev"] == 20.0
    assert wynik["1"]["implied"] == 40.0


def test_oblicz_value_below_threshold_excluded():
    # implied ~= nasze, EV poniżej progu
    wynik = oblicz_value(40.0, 30.0, 30.0, k1=2.50, kx=3.0, k2=3.0, prog_ev=5.0)
    assert "1" not in wynik


def test_oblicz_value_missing_kurs_skipped():
    wynik = oblicz_value(60.0, 25.0, 15.0, k1=None, kx=3.0, k2=6.0, prog_ev=5.0)
    assert "1" not in wynik


# ── porownaj_z_predykcjami ────────────────────────────────────────────────────

def test_porownaj_z_predykcjami_returns_value_bets():
    oferta = [
        {"team1": "Real Madrid", "team2": "Barcelona", "k1": 2.50, "kx": 3.0, "k2": 6.0,
         "liga": "La Liga", "mecz": "Real Madrid - Barcelona", "czas": "jutro, 21:00"},
    ]
    predykcje = [
        {"gosp": "Real Madryt", "gosc": "FC Barcelona",
         "pred": {"p_wygrana": 60.0, "p_remis": 25.0, "p_przegrana": 15.0}},
    ]

    wyniki = porownaj_z_predykcjami(predykcje, oferta=oferta, prog_ev=5.0)

    assert len(wyniki) == 1
    assert wyniki[0]["gosp"] == "Real Madryt"
    assert "1" in wyniki[0]["value"]


def test_porownaj_z_predykcjami_no_match_skipped():
    oferta = [
        {"team1": "Korea Południowa", "team2": "Czechy", "k1": 2.85, "kx": 3.20, "k2": 2.95,
         "liga": "Świat", "mecz": "Korea Południowa - Czechy", "czas": "jutro, 4:00"},
    ]
    predykcje = [
        {"gosp": "Liverpool", "gosc": "Chelsea",
         "pred": {"p_wygrana": 60.0, "p_remis": 25.0, "p_przegrana": 15.0}},
    ]

    assert porownaj_z_predykcjami(predykcje, oferta=oferta) == []


def test_porownaj_z_predykcjami_no_value_skipped():
    oferta = [
        {"team1": "Real Madrid", "team2": "Barcelona", "k1": 1.50, "kx": 4.0, "k2": 6.0,
         "liga": "La Liga", "mecz": "Real Madrid - Barcelona", "czas": "jutro, 21:00"},
    ]
    predykcje = [
        {"gosp": "Real Madryt", "gosc": "FC Barcelona",
         "pred": {"p_wygrana": 60.0, "p_remis": 25.0, "p_przegrana": 15.0}},
    ]
    # implied(1.50) = 66.7% > nasze 60% -> brak value
    assert porownaj_z_predykcjami(predykcje, oferta=oferta) == []
