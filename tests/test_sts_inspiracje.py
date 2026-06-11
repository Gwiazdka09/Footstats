"""Testy parsowania i wyceny sygnalow Strefy Inspiracji STS (TD 15.7/15.8)."""
from footstats.scrapers.sts_inspiracje import (
    _joint_probability,
    dopasuj_do_predykcji,
    normalize_market_tip,
    ocen_sygnal,
    parse_betbuilder_carousel,
    parse_popular_tickets,
)


# ── normalize_market_tip ──────────────────────────────────────────────────────

def test_normalize_podwojna_szansa():
    assert normalize_market_tip("Podwójna szansa: 1X") == "1X"
    assert normalize_market_tip("Podwójna szansa: X2") == "X2"


def test_normalize_mecz():
    assert normalize_market_tip("Mecz: 2") == "2"
    assert normalize_market_tip("Mecz: 1") == "1"


def test_normalize_liczba_goli_total():
    assert normalize_market_tip("Liczba goli: +1.5") == "OVER 1.5"
    assert normalize_market_tip("Liczba goli: -3.5") == "UNDER 3.5"


def test_normalize_liczba_goli_druzyny():
    assert normalize_market_tip("1. drużyna - liczba goli: -1.5") == "1 UNDER 1.5"
    assert normalize_market_tip("2. drużyna - liczba goli: +0.5") == "2 OVER 0.5"


def test_normalize_strzeli_gola():
    assert normalize_market_tip("1. drużyna - strzeli gola: tak") == "1 OVER 0.5"
    assert normalize_market_tip("2. drużyna - strzeli gola: nie") == "2 UNDER 0.5"


def test_normalize_unsupported_markets_return_none():
    assert normalize_market_tip("1. połowa - liczba goli: +0.5") is None
    assert normalize_market_tip("Liczba rzutów rożnych: +7.5") is None
    assert normalize_market_tip("Liczba kartek: +3.5") is None
    assert normalize_market_tip("Zawodnik - celne strzały - 1 lub więcej: tak") is None


# ── parse_popular_tickets (Strefa Inspiracji) ────────────────────────────────

_POPULARNE_TXT = """Strefa inspiracji
Odkryj
Obserwujesz
Popularne kupony
3829
Przejdź
Dariusz S.
70%
32 zdarzenia
2
30
Wysoki kurs
Kanada - Bośnia i Hercegowina
12.06.2026, 21:00
Bet Builder: 2 zdarzenia
1.36
Międzynarodowe, Mistrzostwa Świata
Podwójna szansa: 1X
1. drużyna - strzeli gola: tak
Katar - Szwajcaria
13.06.2026, 21:00
Bet Builder: 2 zdarzenia
1.41
Międzynarodowe, Mistrzostwa Świata
Mecz: 2
Liczba goli: +1.5
"""


def test_parse_popular_tickets_count():
    tickets = parse_popular_tickets(_POPULARNE_TXT)
    assert len(tickets) == 2


def test_parse_popular_tickets_first():
    tickets = parse_popular_tickets(_POPULARNE_TXT)
    t = tickets[0]
    assert t["team1"] == "Kanada"
    assert t["team2"] == "Bośnia i Hercegowina"
    assert t["mecz"] == "Kanada - Bośnia i Hercegowina"
    assert t["total_odds"] == 1.36
    assert t["n_zdarzenia"] == 2
    assert t["typy"] == ["1X", "1 OVER 0.5"]


def test_parse_popular_tickets_second():
    tickets = parse_popular_tickets(_POPULARNE_TXT)
    t = tickets[1]
    assert t["team1"] == "Katar"
    assert t["team2"] == "Szwajcaria"
    assert t["total_odds"] == 1.41
    assert t["typy"] == ["2", "OVER 1.5"]


# ── parse_betbuilder_carousel (strona glowna) ────────────────────────────────

def test_parse_betbuilder_carousel():
    tile = (
        "Korea Południowa\nCzechy\ndzisiaj\n4:00\n"
        "Podwójna szansa: 1X\nLiczba goli: +1.5\nLiczba rzutów rożnych: +7.5\n2.92"
    )
    tickets = parse_betbuilder_carousel([tile])

    assert len(tickets) == 1
    t = tickets[0]
    assert t["team1"] == "Korea Południowa"
    assert t["team2"] == "Czechy"
    assert t["mecz"] == "Korea Południowa - Czechy"
    assert t["total_odds"] == 2.92
    assert t["typy"] == ["1X", "OVER 1.5", None]


def test_parse_betbuilder_carousel_skips_short_tiles():
    assert parse_betbuilder_carousel(["zbyt krótki\ntekst"]) == []


# ── _joint_probability / ocen_sygnal ──────────────────────────────────────────

def test_joint_probability_1x():
    # 1X (gospodarz nie przegrywa) dla lh=2.0, la=1.0 powinno byc wysokie (>50%)
    p = _joint_probability(["1X"], lh=2.0, la=1.0)
    assert 0.5 < p < 1.0


def test_joint_probability_combo_narrower_than_single():
    p_single = _joint_probability(["1X"], lh=1.35, la=1.35)
    p_combo  = _joint_probability(["1X", "UNDER 2.5"], lh=1.35, la=1.35)
    assert p_combo < p_single


def test_ocen_sygnal_brak_modelu_when_unsupported_market():
    ticket = {"total_odds": 2.92, "typy": ["1X", "OVER 1.5", None]}
    wynik = ocen_sygnal(ticket, lh=1.35, la=1.35)
    assert wynik["signal"] == "BRAK_MODELU"
    assert wynik["model_p"] is None
    assert wynik["implied"] == round(100 / 2.92, 1)


def test_ocen_sygnal_value_when_model_p_higher_than_implied():
    # Bardzo wysoki kurs (10.0 -> implied=10%) przy realistycznym 1X -> VALUE
    ticket = {"total_odds": 10.0, "typy": ["1X"]}
    wynik = ocen_sygnal(ticket, lh=1.35, la=1.35)
    assert wynik["signal"] == "VALUE"
    assert wynik["model_p"] > wynik["implied"]


def test_ocen_sygnal_no_value_when_implied_higher_than_model():
    # Bardzo niski kurs (1.01 -> implied~99%) -> model_p ponizej implied
    ticket = {"total_odds": 1.01, "typy": ["1X"]}
    wynik = ocen_sygnal(ticket, lh=1.35, la=1.35)
    assert wynik["signal"] == "NO_VALUE"


# ── dopasuj_do_predykcji ──────────────────────────────────────────────────────

def test_dopasuj_do_predykcji_matches_by_teams():
    tickets = [
        {"team1": "Real Madrid", "team2": "Barcelona", "mecz": "Real Madrid - Barcelona",
         "total_odds": 2.77, "typy": ["1X", "UNDER 2.5"]},
    ]
    predykcje = [
        {"gosp": "Real Madryt", "gosc": "FC Barcelona",
         "pred": {"expected_home_goals": 1.8, "expected_away_goals": 1.2}},
    ]

    wyniki = dopasuj_do_predykcji(tickets, predykcje)

    assert len(wyniki) == 1
    assert wyniki[0]["gosp"] == "Real Madryt"
    assert wyniki[0]["signal"] in ("VALUE", "NO_VALUE")
    assert wyniki[0]["model_p"] is not None


def test_dopasuj_do_predykcji_no_match_skipped():
    tickets = [
        {"team1": "Real Madrid", "team2": "Barcelona", "mecz": "Real Madrid - Barcelona",
         "total_odds": 2.0, "typy": ["1X"]},
    ]
    predykcje = [
        {"gosp": "Liverpool", "gosc": "Chelsea",
         "pred": {"expected_home_goals": 1.5, "expected_away_goals": 1.0}},
    ]

    assert dopasuj_do_predykcji(tickets, predykcje) == []
