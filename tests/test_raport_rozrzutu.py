"""Raport rozrzutu kursow — czy liczba, ktora pokazuje, jest prawdziwa.

Ten raport ma odpowiedziec na jedyne pytanie pilota jedna liczba. Blad w nim
nie da awarii — da wynik wygladajacy na odkrycie. Stad nacisk na przypadki,
w ktorych raport MUSI odmowic odpowiedzi zamiast zgadywac.
"""
from __future__ import annotations

import scripts.stan_uczenia as su


class _Conn:
    """Atrapa: raport ma jedno zapytanie, wiec zwracamy wiersze niezaleznie od SQL."""

    def __init__(self, wiersze):
        self._wiersze = wiersze

    def execute(self, sql, params=()):
        return self

    def fetchall(self):
        return self._wiersze


def _w(bookmaker, outcome, price, sport="soccer_epl", event="e1",
       market="totals", line=2.5, dzien="2026-08-27"):
    return {"snapshot_date": dzien, "sport_key": sport, "event_id": event,
            "market": market, "line": line, "outcome": outcome,
            "bookmaker": bookmaker, "price": price}


def _rynek_totals(ceny_per_ksiazka, **kw):
    """ceny_per_ksiazka: {bukmacher: (cena_over, cena_under)}"""
    return [_w(b, o, c, **kw)
            for b, (over, under) in ceny_per_ksiazka.items()
            for o, c in (("Over", over), ("Under", under))]


def test_brak_danych_nie_wywala_raportu(capsys):
    su.raport_rozrzutu_kursow(_Conn([]))
    assert "BRAK DANYCH" in capsys.readouterr().out


def test_raport_pokazuje_uzyta_referencje(capsys):
    """Mediana miekkich ksiazek to referencja duzo slabsza niz Pinnacle —
    wniosek trzeba wtedy czytac inaczej, wiec nazwa MUSI byc widoczna."""
    su.raport_rozrzutu_kursow(_Conn(_rynek_totals({
        "sport888": (1.80, 2.10),
        "williamhill": (1.85, 2.00),
        "betsson": (2.05, 1.80),
    })))
    assert "mediana" in capsys.readouterr().out


def test_raport_oznacza_rynek_zbyt_cienki(capsys):
    """Dwie ksiazki to nie rozrzut — rynek roznych mial ich dokladnie dwie.
    Bez tej etykiety efektowna rozpietosc z dwoch kwot czytaloby sie jak sygnal."""
    su.raport_rozrzutu_kursow(_Conn(_rynek_totals({
        "pinnacle": (1.79, 2.05),
        "mybookieag": (1.80, 1.91),
    })))
    out = capsys.readouterr().out
    assert "ksiazek=2" in out
    assert "ZBYT CIENKI" in out


def test_raport_pokazuje_ksiazke_z_najwyzszym_edge(capsys):
    """Ksiazka musi miec >=3 obserwacje, zeby trafic do zestawienia."""
    wiersze = []
    for i in range(4):
        wiersze += _rynek_totals(
            {"pinnacle": (2.00, 2.00), "soft": (2.40, 1.70), "trzeci": (2.05, 1.85)},
            event=f"e{i}")
    su.raport_rozrzutu_kursow(_Conn(wiersze))
    assert "soft" in capsys.readouterr().out


def test_werdykt_stosuje_prog_do_dolnej_granicy_nie_do_punktu(capsys):
    """Sedno progu ze specu. Jeden rynek z ogromnym edge daje wysoka mediane,
    ale przy n=1 przedzial jest calym zakresem — raport NIE moze wtedy orzec
    'warto ciagnac'. To ten sam blad, ktory 26.08 dwa razy przeszedl przez
    tabele kubelkow bez bledu standardowego."""
    su.raport_rozrzutu_kursow(_Conn(_rynek_totals({
        "pinnacle": (2.00, 2.00),
        "soft": (2.60, 1.60),
        "trzeci": (2.05, 1.85),
    })))
    out = capsys.readouterr().out
    assert "PRZEKRACZA" not in out, "przy n=1 nie wolno orzekac, ze warto ciagnac"


def test_raport_pokazuje_mediane_rozpietosci(capsys):
    su.raport_rozrzutu_kursow(_Conn(_rynek_totals({
        "pinnacle": (2.00, 2.00),
        "soft": (2.40, 1.70),
        "trzeci": (2.05, 1.85),
    })))
    assert "mediana rozpietosci cen" in capsys.readouterr().out


def test_raport_grupuje_per_liga(capsys):
    wiersze = _rynek_totals({"pinnacle": (2.00, 2.00), "soft": (2.10, 1.90)},
                            sport="soccer_epl", event="e1")
    wiersze += _rynek_totals({"pinnacle": (1.90, 1.90), "soft": (2.00, 1.80)},
                             sport="soccer_japan_j_league", event="e2")
    su.raport_rozrzutu_kursow(_Conn(wiersze))
    out = capsys.readouterr().out
    assert "soccer_epl" in out and "soccer_japan_j_league" in out


# --- integracja z poprawka kompletnosci rynku (najwazniejsze) ----------------

def test_rynek_1x2_dwa_z_trzech_jest_niewycenialny_a_nie_zyskowny(capsys):
    """REGRES o najwyzszej stawce w calym pilocie.

    Gdyby raport nie przekazywal typu rynku do `cena_referencyjna`, ksiazka
    kwotujaca 2 z 3 wynikow 1X2 zostalaby referencja, devig policzylby cene
    uczciwa z okrojonego zestawu i KAZDY edge wyszedlby zawyzony. Zmierzone
    27.08 na realnej migawce: +37.8% zamiast +6.24%, przy progu decyzyjnym +2%.

    Tu ZADNA ksiazka nie ma kompletu, wiec poprawna odpowiedz brzmi
    'nie da sie wycenic', a nie jakakolwiek liczba."""
    wiersze = [
        _w("pinnacle", "Crystal Palace", 4.60, market="h2h", line=0.0),
        _w("pinnacle", "Manchester City", 1.70, market="h2h", line=0.0),
        _w("williamhill", "Crystal Palace", 4.70, market="h2h", line=0.0),
        _w("williamhill", "Manchester City", 1.68, market="h2h", line=0.0),
    ]
    su.raport_rozrzutu_kursow(_Conn(wiersze))
    out = capsys.readouterr().out
    assert "NIEWYCENIALNE" in out
    assert "PRZEKRACZA" not in out, "rynek bez pelnego kompletu nie moze dac werdyktu"


def test_rynek_1x2_z_kompletem_liczy_sie_normalnie(capsys):
    """Kontrola pozytywna do testu wyzej — pelne 1X2 ma przejsc i dac referencje."""
    wiersze = [
        _w("pinnacle", "Crystal Palace", 4.81, market="h2h", line=0.0),
        _w("pinnacle", "Draw", 4.21, market="h2h", line=0.0),
        _w("pinnacle", "Manchester City", 1.69, market="h2h", line=0.0),
        _w("betfair_ex_eu", "Crystal Palace", 5.30, market="h2h", line=0.0),
        _w("betfair_ex_eu", "Draw", 4.20, market="h2h", line=0.0),
        _w("betfair_ex_eu", "Manchester City", 1.72, market="h2h", line=0.0),
    ]
    su.raport_rozrzutu_kursow(_Conn(wiersze))
    out = capsys.readouterr().out
    assert "pinnacle" in out
    assert "NIEWYCENIALNE" not in out


def test_niewycenialne_nie_jest_mylone_z_brakiem_przewagi(capsys):
    """Komunikat musi mowic wprost, ze to brak POMIARU. Bez tego zdanie
    'nie ma przewagi' i 'nie dalo sie policzyc' wygladaja identycznie —
    ta sama cicha porazka, ktora w tym projekcie kosztowala szesc dni potoku."""
    wiersze = [
        _w("pinnacle", "A", 2.0, market="h2h", line=0.0),
        _w("pinnacle", "B", 2.0, market="h2h", line=0.0),
    ]
    su.raport_rozrzutu_kursow(_Conn(wiersze))
    assert "brak pomiaru" in capsys.readouterr().out


def test_przy_malej_liczbie_rynkow_raport_odmawia_werdyktu(capsys):
    """n=1 daje przedzial zdegenerowany do punktu, wiec 'dolna granica powyzej
    progu' bylaby spelniona zawsze, gdy tylko edge jest wysoki. Raport ma
    powiedziec, ze rynkow jest za malo — a nie ze warto ciagnac."""
    su.raport_rozrzutu_kursow(_Conn(_rynek_totals({
        "pinnacle": (2.00, 2.00),
        "soft": (2.60, 1.60),
        "trzeci": (2.05, 1.85),
    })))
    out = capsys.readouterr().out
    assert "ZA MALO RYNKOW" in out
    assert "PRZEKRACZA" not in out


def test_przy_wystarczajacej_liczbie_rynkow_werdykt_zapada(capsys):
    """Kontrola pozytywna: przy 8 rynkach o stabilnie wysokim edge raport MA
    orzec, ze warto ciagnac — inaczej bramka na liczbe rynkow zablokowalaby
    wszystko i pilot nigdy nie dalby odpowiedzi."""
    wiersze = []
    for i in range(8):
        wiersze += _rynek_totals(
            {"pinnacle": (2.00, 2.00), "soft": (2.60, 1.60), "trzeci": (2.05, 1.85)},
            event=f"e{i}")
    su.raport_rozrzutu_kursow(_Conn(wiersze))
    assert "PRZEKRACZA" in capsys.readouterr().out


def test_mediana_powyzej_progu_ale_dolna_granica_nie_daje_werdyktu(capsys):
    """Rozdziela PUNKT od DOLNEJ GRANICY — bez tego testu zamiana jednego na
    drugie przechodzi na zielono.

    Osiem rynkow o ROZNYCH edge: [-5%, -2%, +1%, +2.5%, +3.5%, +6%, +9%, +15%].
    Mediana = +3% (powyzej progu +2%), ale dolna granica przedzialu = -5%
    (ponizej). Poprawna odpowiedz brzmi 'za malo danych, zeby orzec'.

    Poprzedni test pozytywny uzywal osmiu IDENTYCZNYCH rynkow, wiec mediana
    rownala sie dolnej granicy i roznicy nie bylo jak zobaczyc."""
    edge_docelowe = [-0.05, -0.02, 0.01, 0.025, 0.035, 0.06, 0.09, 0.15]
    wiersze = []
    for i, e in enumerate(edge_docelowe):
        # pinnacle 2.00/2.00 -> cena uczciwa 0.5 na kazdy wynik.
        # soft Over = 2*(1+e) daje dokladnie edge = e; Under 1.60 daje -20%,
        # wiec najlepszym edge w rynku jest zawsze Over.
        wiersze += _rynek_totals(
            {"pinnacle": (2.00, 2.00), "soft": (round(2.0 * (1.0 + e), 4), 1.60)},
            event=f"e{i}")
    su.raport_rozrzutu_kursow(_Conn(wiersze))
    out = capsys.readouterr().out
    assert "dolna granica" in out
    assert "PRZEKRACZA" not in out, "prog musi isc do dolnej granicy, nie do mediany"

