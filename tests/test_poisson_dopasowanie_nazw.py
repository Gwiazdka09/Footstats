"""Poisson musi znaleźć historię drużyny mimo różnic w zapisie nazwy.

BUG (2026-08-07, prod): `predict_match` porównywało nazwy DOKŁADNĄ równością
(`df["gospodarz"] == g`), a dwa źródła zapisują je inaczej:

    Bzzoiro (predykcje)        dataset (football-data.co.uk)
    "Górnik Zabrze"            "Gornik Zabrze"
    "SC Cambuur"               "Cambuur"

Skutek zmierzony na realnym przebiegu `footstats-final` 07.08: z 49 kandydatów
ZERO miało obie drużyny rozpoznane, więc `predict_match` zwracało None dla
wszystkich i cały ruch szedł fallbackiem Bzzoiro-ML — mimo świeżego datasetu
i naprawionego pyarrow. Po normalizacji rozpoznane są 2.

CELOWO BEZ DOPASOWANIA ROZMYTEGO. Zmierzone na tych samych danych:

    team_similarity("Wisła Kraków", "Wisla")       = 0.800
    team_similarity("Wisła Płock",  "Wisla")       = 0.800

Identyczny wynik dla DWÓCH RÓŻNYCH klubów — próg nie jest w stanie ich rozdzielić,
a wybór złego liczy λ z cudzych meczów i nikt tego nie zauważy. To ta sama klasa
błędu co uśrednianie podobieństw przy rozliczaniu kuponów (bug #12).
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.core.poisson import predict_match


def _historia(pary: list[tuple[str, str]], n: int = 10) -> pd.DataFrame:
    """DataFrame w schemacie produkcyjnym — tyle meczów, by Poisson miał podstawę."""
    wiersze = []
    for i in range(n):
        for g, a in pary:
            wiersze.append({
                "gospodarz": g, "goscie": a,
                "gole_g": 2, "gole_a": 1,
                "data": f"2026-0{(i % 9) + 1}-01",
            })
    return pd.DataFrame(wiersze)


def test_dokladne_nazwy_dzialaja_jak_dotad() -> None:
    df = _historia([("Gornik Zabrze", "Radomiak Radom")])
    assert predict_match("Gornik Zabrze", "Radomiak Radom", df) is not None


def test_polskie_znaki_nie_blokuja_dopasowania() -> None:
    """Dokładnie para, która przeszła przez produkcję 07.08 i nie została policzona."""
    df = _historia([("Gornik Zabrze", "Radomiak Radom")])
    assert predict_match("Górnik Zabrze", "Radomiak Radom", df) is not None


def test_prefiks_klubowy_nie_blokuje_dopasowania() -> None:
    df = _historia([("Cambuur", "Excelsior")])
    assert predict_match("SC Cambuur", "Excelsior", df) is not None


def test_obie_druzyny_moga_roznic_sie_zapisem() -> None:
    df = _historia([("Gornik Zabrze", "Cambuur")])
    assert predict_match("Górnik Zabrze", "SC Cambuur", df) is not None


def test_nieznana_druzyna_nadal_zwraca_none() -> None:
    """Brak historii ma dawać None, a nie λ policzone z przypadkowych meczów."""
    df = _historia([("Gornik Zabrze", "Radomiak Radom")])
    assert predict_match("Shanghai Port", "Beijing Guoan", df) is None


def test_rozne_kluby_o_podobnej_nazwie_nie_sa_laczone() -> None:
    """`Wisla` (Kraków) i `Wisla Plock` to dwa kluby — λ nie może ich mieszać.

    Gdyby dopasowanie było rozmyte, oba trafiłyby w ten sam wpis (0.800 do obu),
    więc ten test jest jedynym, który tego pilnuje.
    """
    df = _historia([("Wisla", "Lech Poznan")])
    assert predict_match("Wisla Plock", "Lech Poznan", df) is None, (
        "Plock dostal historie Krakowa"
    )


def test_puste_i_none_nie_wywracaja_dopasowania() -> None:
    df = _historia([("Gornik Zabrze", "Radomiak Radom")])
    df.loc[0, "gospodarz"] = None
    df.loc[1, "goscie"] = ""
    assert predict_match("Górnik Zabrze", "Radomiak Radom", df) is not None


@pytest.mark.parametrize("kolumna", ["gospodarz", "goscie"])
def test_dopasowanie_dziala_w_obie_strony(kolumna: str) -> None:
    """Drużyna bywa w historii raz gospodarzem, raz gościem."""
    pary = [("Gornik Zabrze", "X")] if kolumna == "gospodarz" else [("X", "Gornik Zabrze")]
    df = _historia(pary + [("Radomiak Radom", "Y")])
    assert predict_match("Górnik Zabrze", "Radomiak Radom", df) is not None


def test_poisson_nie_porownuje_nazw_surowa_rownoscia() -> None:
    """Guard przed cofnięciem zmiany — `== g` na kolumnie drużyn wraca po cichu."""
    import ast
    import pathlib

    zrodlo = pathlib.Path("src/footstats/core/poisson.py").read_text(encoding="utf-8")
    drzewo = ast.parse(zrodlo)

    KOLUMNY = {"gospodarz", "goscie"}
    winne = []
    for wezel in ast.walk(drzewo):
        if not isinstance(wezel, ast.Compare) or not isinstance(wezel.ops[0], ast.Eq):
            continue
        lewa = wezel.left
        # Wzorzec: df_mecze["gospodarz"] == cos
        if (
            isinstance(lewa, ast.Subscript)
            and isinstance(lewa.slice, ast.Constant)
            and lewa.slice.value in KOLUMNY
        ):
            winne.append(f"linia {wezel.lineno}: porownanie kolumny {lewa.slice.value!r}")

    assert not winne, "surowe == na nazwach druzyn: " + "; ".join(winne)
