"""test_weekly_picks.py — dobor typow "Pewniaczki Tygodnia" i ich render.

PO CO: modul byl WYKLUCZONY z pomiaru pokrycia, po zdjeciu z listy pokazal 11%.
To on decyduje, KTORE typy w ogole trafiaja do propozycji.

Sedno w `_typy_pewne` to rynki zlozone:
    1X = pw + pr        X2 = pr + pp        12 = pw + pp
Zamiana skladnikow (np. 1X liczone jako pw+pp) dalaby CICHO zly typ — liczba
nadal wygladalaby sensownie, bo to suma dwoch prawdopodobienstw. Dlatego kazdy
z trzech ma osobny test na wlasciwa pare.

`_ml_do_predykcji` konwertuje ML z Bzzoiro do wspolnego formatu. Blad tutaj
przenosi sie na wszystkie typy z tego meczu.
"""
from __future__ import annotations

import pytest

import footstats.core.weekly_picks as wp
from footstats.core.weekly_picks import _ml_do_predykcji, _typy_pewne


def _typy(pw=50.0, pr=25.0, pp=25.0, bt=50.0, o25=50.0, u25=50.0,
          g="Legia", a="Lech", prog=75.0):
    return _typy_pewne(pw, pr, pp, bt, o25, u25, g, a, prog)


def _opisy(wynik) -> list[str]:
    return [opis for opis, _szansa in wynik]


# ── _typy_pewne: progi ──────────────────────────────────────────────────────

def test_nic_ponizej_progu_nie_przechodzi():
    """Wysoki remis jest konieczny, zeby ZADEN rynek nie przeszedl.

    Przy niskim remisie `12` (pw+pp) samo z siebie przekracza prog — np.
    50/20/30 daje 12 = 80%. Rownowaga 35/35/30 trzyma wszystkie osiem ponizej 75.
    """
    assert _typy(pw=35, pr=35, pp=30, bt=40, o25=45, u25=55, prog=75) == []


def test_typ_dokladnie_na_progu_przechodzi():
    """Prog jest wlaczajacy (>=) — 75.0 przy progu 75 ma wejsc."""
    assert any("Wygrana Legia" in o for o in _opisy(_typy(pw=75.0, prog=75)))


def test_zwraca_szanse_zaokraglona():
    wynik = _typy(pw=82.4567, prog=75)
    assert wynik[0][1] == 82.5


def test_nizszy_prog_przepuszcza_wiecej():
    assert len(_typy(prog=95)) <= len(_typy(prog=40))


# ── _typy_pewne: rynki pojedyncze ───────────────────────────────────────────

def test_typ_1_z_prawdopodobienstwa_gospodarza():
    assert any("1 – Wygrana Legia" in o for o in _opisy(_typy(pw=80, prog=75)))


def test_typ_2_z_prawdopodobienstwa_goscia():
    assert any("2 – Wygrana Lech" in o for o in _opisy(_typy(pp=80, prog=75)))


def test_nazwa_druzyny_przycinana():
    """Dluga nazwa nie moze rozwalic tabeli w raporcie."""
    dluga = "Borussia Moenchengladbach Reserve"
    wynik = _opisy(_typy_pewne(90, 5, 5, 0, 0, 0, dluga, "X", 75))
    assert len(wynik[0].split("Wygrana ")[1]) <= 15


@pytest.mark.parametrize("pole,oczekiwane", [
    ("bt", "BTTS TAK"),
    ("o25", "Over 2.5"),
    ("u25", "Under 2.5"),
])
def test_rynki_golowe(pole, oczekiwane):
    assert oczekiwane in _opisy(_typy(**{pole: 88}, prog=75))


# ── _typy_pewne: rynki zlozone (najwazniejsze) ──────────────────────────────

def test_1X_to_gospodarz_plus_remis():
    """pw=50 + pr=30 = 80 >= 75. Gdyby liczylo pw+pp (50+20=70) — nie przeszloby."""
    wynik = _typy(pw=50, pr=30, pp=20, prog=75)
    assert any("1X" in o for o in _opisy(wynik))
    szansa = [s for o, s in wynik if "1X" in o][0]
    assert szansa == 80.0


def test_X2_to_remis_plus_gosc():
    """pr=30 + pp=50 = 80. Gdyby liczylo pw+pr (20+30=50) — nie przeszloby."""
    wynik = _typy(pw=20, pr=30, pp=50, prog=75)
    assert any("X2" in o for o in _opisy(wynik))
    assert [s for o, s in wynik if "X2" in o][0] == 80.0


def test_12_to_gospodarz_plus_gosc_bez_remisu():
    """pw=45 + pp=45 = 90. Remis (10) NIE moze wejsc do tej sumy."""
    wynik = _typy(pw=45, pr=10, pp=45, prog=75)
    assert any("12" in o for o in _opisy(wynik))
    assert [s for o, s in wynik if "12" in o][0] == 90.0


def test_wysoki_remis_nie_przepuszcza_12():
    """Regresja na pomylke skladnikow: 12 z remisem w sumie bylby zawsze ~100%."""
    wynik = _typy(pw=20, pr=60, pp=20, prog=75)
    assert not any("12" in o for o in _opisy(wynik))


def test_wiele_typow_naraz():
    wynik = _opisy(_typy(pw=80, pr=10, pp=10, bt=80, o25=80, u25=20, prog=75))
    assert len(wynik) >= 4
    assert any("1 – Wygrana" in o for o in wynik)
    assert "BTTS TAK" in wynik and "Over 2.5" in wynik


# ── _ml_do_predykcji ────────────────────────────────────────────────────────

@pytest.fixture
def bzz(monkeypatch):
    """Podstawia _bzz_parse_prob; zwraca (pw, pr, pp, bt, o25) albo None."""
    stan = {"wynik": (55.0, 25.0, 20.0, 52.0, 48.0)}
    monkeypatch.setattr(wp, "_bzz_parse_prob", lambda p: stan["wynik"])
    return stan


def test_brak_predykcji_daje_none(bzz):
    assert _ml_do_predykcji(None) is None
    assert _ml_do_predykcji({}) is None


def test_nieparsowalna_predykcja_daje_none(bzz):
    bzz["wynik"] = None
    assert _ml_do_predykcji({"cokolwiek": 1}) is None


def test_konwertuje_prawdopodobienstwa(bzz):
    wynik = _ml_do_predykcji({"x": 1})
    assert wynik["p_wygrana"] == 55.0
    assert wynik["p_remis"] == 25.0
    assert wynik["p_przegrana"] == 20.0
    assert wynik["btts"] == 52.0
    assert wynik["over25"] == 48.0


def test_under25_liczone_jako_dopelnienie(bzz):
    """under25 musi byc 100 - over25, inaczej rynki golowe sie rozjada."""
    bzz["wynik"] = (50.0, 25.0, 25.0, 50.0, 62.5)
    assert _ml_do_predykcji({"x": 1})["under25"] == 37.5


def test_metoda_oznaczona_jako_ml(bzz):
    """Znacznik decyduje o sortowaniu (Poisson przed ML) i o ikonie w raporcie."""
    assert _ml_do_predykcji({"x": 1})["metoda"] == "ML"


def test_lambdy_puste_dla_ml(bzz):
    """ML nie ma lambd — musi byc jawny myslnik, nie 0 udajace wartosc."""
    wynik = _ml_do_predykcji({"x": 1})
    assert wynik["lambda_g"] == "–" and wynik["lambda_a"] == "–"


def test_typowany_wynik_z_most_likely_score(bzz):
    wynik = _ml_do_predykcji({"most_likely_score": {"home": 2, "away": 1}})
    assert wynik["wynik_g"] == 2 and wynik["wynik_a"] == 1


def test_typowany_wynik_z_pola_goals(bzz):
    """Drugi wariant nazwy pola w API Bzzoiro."""
    wynik = _ml_do_predykcji({"goals": {"home": 3, "away": 0}})
    assert wynik["wynik_g"] == 3 and wynik["wynik_a"] == 0


def test_brak_typowanego_wyniku_daje_domyslne(bzz):
    wynik = _ml_do_predykcji({"x": 1})
    assert wynik["wynik_g"] == 1 and wynik["wynik_a"] == 0


def test_kursy_przekazywane(bzz):
    kursy = {"home": 1.85, "draw": 3.4}
    assert _ml_do_predykcji({"x": 1}, odds=kursy)["odds"] == kursy


def test_wyjatek_w_parsowaniu_daje_none(monkeypatch):
    def _wybuch(p):
        raise ValueError("zly ksztalt")

    monkeypatch.setattr(wp, "_bzz_parse_prob", _wybuch)
    assert _ml_do_predykcji({"x": 1}) is None


# ── wyswietl_pewniaczki ─────────────────────────────────────────────────────

def _pewniak(metoda="POISSON", **kw) -> dict:
    baza = {
        "gospodarz": "Legia", "goscie": "Lech", "liga": "Ekstraklasa",
        "data": "2026-08-02", "godzina": "14:45", "metoda": metoda,
        "ikony": "", "typy": [("1 – Wygrana Legia", 78.0)],
        "pred": {"lambda_g": 1.8, "lambda_a": 0.9, "wynik_g": 2, "wynik_a": 1},
    }
    baza.update(kw)
    return baza


def test_pusta_lista_pokazuje_komunikat(capsys):
    wp.wyswietl_pewniaczki([], prog=75)
    out = capsys.readouterr().out
    assert "Brak pewniakow" in out
    assert "75" in out


def test_naglowek_zlicza_metody(capsys):
    wp.wyswietl_pewniaczki([_pewniak("POISSON"), _pewniak("ML"), _pewniak("POISSON")])
    out = capsys.readouterr().out
    assert "3 meczow" in out
    assert "Poisson:2" in out
    assert "ML:1" in out


def test_renderuje_druzyny_i_lige(capsys):
    wp.wyswietl_pewniaczki([_pewniak()])
    out = capsys.readouterr().out
    assert "Legia" in out and "Lech" in out
    assert "Ekstraklasa" in out


def test_lambdy_pokazywane_tylko_dla_poissona(capsys):
    wp.wyswietl_pewniaczki([_pewniak("POISSON")])
    assert "λ" in capsys.readouterr().out

    wp.wyswietl_pewniaczki([_pewniak("ML", pred={"lambda_g": "–", "lambda_a": "–"})])
    assert "λ" not in capsys.readouterr().out


def test_brakujace_ikony_nie_wywalaja_renderu(capsys):
    p = _pewniak()
    del p["ikony"]
    wp.wyswietl_pewniaczki([p])
    assert "Legia" in capsys.readouterr().out
