"""Warstwa xG w `sily_ligowe` — czytelnik dla kolumn, których jeszcze nie ma.

Kolejność jest wymuszona przez zasadę z `af_stats.py`: „kolumna bez czytelnika
prędzej czy później zostanie użyta bez pomiaru". Więc najpierw czytelnik
(ten kod), potem pomiar A/B, i dopiero po dodatnim wyniku promocja `xg_home` /
`xg_away` do ramki modelu.

DOMYŚLNIE WYŁĄCZONE (`WAGA_XG=0`). Włączenie jest zmianą warstwy predykcji
i ma nastąpić dopiero po zmierzeniu, nie przy okazji.

Dlaczego xG wchodzi PO strzałach, a nie zamiast: pytanie brzmi „czy LEPSZA
miara tego samego zjawiska dokłada cokolwiek ponad miarę gorszą". Podmiana
odpowiadałaby na inne pytanie i mieszałaby dwie zmiany naraz.
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.core.form import sily_ligowe


def _liga(n_par: int = 12, xg_mnoznik: float = 1.0,
          z_xg: bool = True) -> pd.DataFrame:
    """Liga: 'Mocny' strzela dużo, 'Slaby' mało. xG skalowane mnożnikiem.

    `xg_mnoznik` > 1 na golach Mocnego znaczy „xG mówi, że Mocny jest jeszcze
    lepszy, niż wynika z goli" — po włączeniu warstwy jego atak ma urosnąć.
    """
    # Slaby MUSI strzelac wiecej niz zero, inaczej cala ligowa srednia pochodzi
    # od Mocnego i iloraz `jego_xg / srednia_xg` jest NIEZMIENNICZY na skalowanie
    # jego wlasnego xG — test wygladalby poprawnie, nie mogac niczego wykryc.
    wiersze = []
    for i in range(n_par):
        for gosp, gosc, gg, ga in (("Mocny", "Slaby", 3, 1), ("Slaby", "Mocny", 1, 2)):
            w = {
                "gospodarz": gosp, "goscie": gosc, "gole_g": gg, "gole_a": ga,
                "hst": gg + 2, "ast": ga + 2,
                "data": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i * 7),
            }
            if z_xg:
                w["xg_home"] = gg * (xg_mnoznik if gosp == "Mocny" else 1.0)
                w["xg_away"] = ga * (xg_mnoznik if gosc == "Mocny" else 1.0)
            wiersze.append(w)
    return pd.DataFrame(wiersze)


def _atak(df: pd.DataFrame, waga_xg: float, druzyna: str = "Mocny") -> float:
    wynik = sily_ligowe(df, waga_strzalow=0.7, waga_xg=waga_xg)
    assert wynik is not None
    return wynik[0][druzyna]["atak_dom"]


def test_waga_zero_nie_zmienia_niczego():
    """Domyślna ścieżka produkcyjna musi zostać bit-w-bit taka sama."""
    df = _liga()
    bez = sily_ligowe(df, waga_strzalow=0.7, waga_xg=0.0)
    brak_kolumn = sily_ligowe(df.drop(columns=["xg_home", "xg_away"]),
                              waga_strzalow=0.7, waga_xg=0.7)
    assert bez == brak_kolumn


def test_xg_przesuwa_rating_we_wskazanym_kierunku():
    """xG mówiące, że Mocny jest lepszy niż gole → wyższy atak po włączeniu."""
    df = _liga(xg_mnoznik=1.6)
    assert _atak(df, 0.7) > _atak(df, 0.0)


def test_xg_moze_rating_takze_obnizyc():
    """Warstwa ma być dwustronna, nie premią. xG niższe od goli → niższy atak."""
    df = _liga(xg_mnoznik=0.5)
    assert _atak(df, 0.7) < _atak(df, 0.0)


def test_brak_kolumn_xg_nie_wywraca_i_nie_zmienia():
    """Połowa datasetu nie ma xG — to normalny stan, nie awaria."""
    df = _liga(z_xg=False)
    assert sily_ligowe(df, waga_strzalow=0.7, waga_xg=0.7) is not None
    assert (sily_ligowe(df, waga_strzalow=0.7, waga_xg=0.7)
            == sily_ligowe(df, waga_strzalow=0.7, waga_xg=0.0))


def test_puste_xg_w_kolumnie_nie_psuje_ratingow():
    """Kolumna obecna, ale same NaN — musi zachować się jak jej brak."""
    df = _liga()
    df["xg_home"] = pd.NA
    df["xg_away"] = pd.NA
    assert (sily_ligowe(df, waga_strzalow=0.7, waga_xg=0.7)
            == sily_ligowe(df, waga_strzalow=0.7, waga_xg=0.0))


def test_druzyna_bez_xg_zostaje_na_dotychczasowym_ratingu():
    """Mieszanie jest PER DRUŻYNA — brak xG u jednej nie rusza pozostałych.

    Pokrycie xG z API-Football jest nierówne (od 27% w IRL do 100% w USA),
    więc stan „część drużyn ligi ma xG, część nie" jest tu regułą, nie wyjątkiem.
    """
    df = _liga(xg_mnoznik=1.6)
    # Slaby traci xG we wszystkich swoich meczach domowych i wyjazdowych
    maska = (df["gospodarz"] == "Slaby") | (df["goscie"] == "Slaby")
    df.loc[maska, ["xg_home", "xg_away"]] = pd.NA
    z_xg = sily_ligowe(df, waga_strzalow=0.7, waga_xg=0.7)
    bez = sily_ligowe(df, waga_strzalow=0.7, waga_xg=0.0)
    assert z_xg is not None and bez is not None
    assert z_xg[0]["Slaby"] == bez[0]["Slaby"], "drużyna bez xG nie mogła się ruszyć"


def test_domyslna_waga_z_configu_jest_zerem():
    """Włączenie ma być świadomą decyzją po pomiarze, nie efektem wdrożenia."""
    from footstats.config import WAGA_XG
    assert WAGA_XG == 0.0


def test_sily_ligowe_bierze_wage_z_configu_gdy_nie_podano():
    """Bez tego flaga w configu byłaby ozdobą — kod czytałby własny default."""
    import footstats.core.form as form
    df = _liga(xg_mnoznik=1.6)
    jawnie = sily_ligowe(df, waga_strzalow=0.7, waga_xg=0.7)
    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr("footstats.config.WAGA_XG", 0.7)
        z_configu = form.sily_ligowe(df, waga_strzalow=0.7)
    finally:
        monkey.undo()
    assert z_configu == jawnie
