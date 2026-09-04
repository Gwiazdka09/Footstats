#!/usr/bin/env python
"""ruch_linii.py — czy model wie coś, czego rynek dowiaduje się dopiero później.

===========================  PRE-REJESTRACJA  ===============================
Spisana 2026-09-04, PRZED policzeniem czegokolwiek z cen otwarcia.

DLACZEGO TO PYTANIE JEST INNE NIŻ WSZYSTKIE POPRZEDNIE. Każdy dotychczasowy
pomiar porównywał model z ceną ZAMKNIĘCIA — najlepszą prognozą, jaką rynek
kiedykolwiek wystawia. Model przegrywał wszędzie: 39 lig na 39 w 1X2, 22 na 22
w rynku golowym. Ale zamknięcie to nie jest cena, po której się stawia.

Tu pytamy o coś węższego i mocniejszego: czy nasza NIEZGODA z ceną otwarcia
przewiduje, w którą stronę ta cena pojedzie do zamknięcia. Model, który to
potrafi, ma informację, którą rynek dopiero nabywa — a to jedyna rzecz, jaką
da się w tej grze spieniężyć. Model, który tego nie potrafi, ma niezgodę
będącą szumem, i wtedy kierunek „ceny przedmeczowe" jest zamknięty razem
z resztą.

CZYSTY POMIAR, BEZ CONFOUNDU BUKMACHERA. Do dziś dataset niósł `odds_h`
(B365, przedmeczowa) i `odds_h_pinn` (Pinnacle, zamknięcie). Różnica między
nimi to ~2.5% mediany — ale ZMIERZONE 04.09, taka sama w obu formatach
źródła, także tam, gdzie obie ceny są zamknięciem. Czyli te 2.5% to marża
Pinnacle kontra średnia, a nie ruch w czasie. Tamtej pary NIE DA SIĘ użyć
do tego pytania.

`PSH/PSD/PSA` (otwarcie Pinnacle) i `PSCH/PSCD/PSCA` (zamknięcie Pinnacle)
to TEN SAM bukmacher w dwóch chwilach. Sprawdzone na E0 2425: identyczne
w 2.4% meczów, odchylenie ruchu 7.75%. To jest właściwa para i istnieje
w źródle od zawsze — po prostu nigdy jej nie wczytywaliśmy.

To NIE łamie reguły „żadnego cofania się do wariantu o innej semantyce"
z 04.09. Tamta reguła zabrania PODMIENIAĆ `PSC*` na `PS*` w jednej kolumnie.
Tutaj obie ceny stoją obok siebie jako osobne wielkości i o to właśnie chodzi.

TEST A — RUCH LINII. To on rozstrzyga.
  p_otw   = devig(PSH, PSD, PSA)
  p_zam   = devig(PSCH, PSCD, PSCA)
  dryf    = p_zam − p_otw           (dokąd pojechał rynek)
  sygnal  = p_model − p_otw         (gdzie my się z nim nie zgadzamy)
  regresja:  dryf = a + b·sygnal + c·p_otw
`p_otw` jest kontrolą, nie ozdobą: dryf zależy od poziomu ceny (faworyci
i longshoty jadą inaczej), a nasz sygnał też zależy od poziomu ceny. Bez tej
kontroli `b` łapałoby tę wspólną zależność i wychodziłoby dodatnie bez
żadnej informacji po naszej stronie.

Wymiar GOSPODARZA jest pierwszorzędny, GOŚCIA drugorzędny; remis pominięty,
bo model strukturalnie nie potrafi tam wystawić wysokiego prawdopodobieństwa
(maksimum 0.400 przy 0.578 rynku). Wynik liczy się TYLKO wtedy, gdy oba
wymiary zgadzają się co do znaku — jeden wymiar to jeden test, a dwa wymiary
tego samego zjawiska muszą wskazywać to samo.

TEST B — DEFICYT WOBEC OTWARCIA I WOBEC ZAMKNIĘCIA, sparowany, te same mecze,
ten sam bukmacher. Mówi, ile w ogóle warta jest różnica między otwarciem
a zamknięciem — czyli jak duża jest nagroda, o którą gramy w teście A.

TEST C — ROI PO NAJLEPSZEJ CENIE PRZEDMECZOWEJ (`MaxH/MaxD/MaxA`). Płasko
jedna jednostka na każdy wynik o EV > 0, podatek 12% od stawki. Do porównania
z tym samym pomiarem po cenie zamknięcia (`MaxC*`), gdzie model dał
−15.01% po podatku.

CZEGO TEN POMIAR NIE ROZSTRZYGA, i trzeba to wiedzieć z góry: produkcja
generuje predykcje o 11:00 w dniu meczu, czyli BLIŻEJ zamknięcia niż otwarcia.
Nawet dodatni wynik testu A nie znaczy automatycznie, że da się ten ruch
złapać — znaczy tylko, że model niesie informację TEGO TYPU, którą rynek
wycenia w ciągu dnia. Pytanie „czy zdążymy" jest osobne i tu nie pada.

REGUŁA DECYZYJNA, ZAMROŻONA:
  * `b` > 0 przy z >= 2 w OBU wymiarach → model wyprzedza rynek. Byłby to
    pierwszy dodatni wynik tego projektu, więc tym bardziej: zanim cokolwiek
    z niego wyniknie, holdout po dacie, pre-rejestrowany osobno.
  * |z| < 2 albo wymiary o przeciwnych znakach → niezgoda modelu z ceną
    otwarcia jest szumem. Kierunek „ceny przedmeczowe" zamknięty.
  * `b` < 0 przy z <= −2 → model jest ANTYPREDYKCYJNY wobec ruchu linii:
    tam, gdzie się nie zgadza, rynek jedzie w drugą stronę. To wynik silny
    i wart osobnego zapisania, bo znaczy, że nasza niezgoda jest systematycznie
    odwrotna, a nie przypadkowa.
  * TEST C: ROI po podatku dodatnie przy z >= 2 → HIPOTEZA, nie zielone światło.
=============================================================================

    python scripts/ruch_linii.py --zrzut sciezka/zrzut*.parquet --otwarcia otw.parquet
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from przewaga_nad_rynkiem import brier_wieloklasowy, sparowana_roznica  # noqa: E402

PODATEK = 0.12
MIN_JOIN = 0.60          # zrzut ma 39 lig, otwarcia tylko 22 sezonowe
WYNIK_NA_INDEKS = {"H": 0, "D": 1, "A": 2}
OTW = ("PSH", "PSD", "PSA")
ZAM = ("PSCH", "PSCD", "PSCA")
MAX_PRZED = ("MaxH", "MaxD", "MaxA")


def devig(o: np.ndarray) -> np.ndarray:
    """Rozkład bez marży z macierzy kursów (n, 3). NaN gdy kurs <= 1.0."""
    o = np.where(o > 1.0, o, np.nan)
    inv = 1.0 / o
    return inv / inv.sum(axis=1, keepdims=True)


def mnk(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Najmniejsze kwadraty ze stałą + błędy standardowe współczynników."""
    X = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    reszty = y - X @ beta
    dof = len(y) - X.shape[1]
    s2 = float(reszty @ reszty) / dof
    war = s2 * np.linalg.inv(X.T @ X)
    return beta, np.sqrt(np.diag(war))


def wczytaj(wzorce: list[str], otwarcia: str) -> pd.DataFrame:
    pliki: list[str] = []
    for w in wzorce:
        pliki += sorted(glob.glob(w))
    if not pliki:
        raise SystemExit(f"Zero plikow dla {wzorce}")
    zrzut = pd.concat([pd.read_parquet(p) for p in pliki], ignore_index=True)
    zrzut = zrzut[zrzut["actual_res"].isin(WYNIK_NA_INDEKS)]

    otw = pd.read_parquet(otwarcia)
    # Kluby rozszczepione dostaly w datasecie pisownie kanoniczna; surowe CSV
    # jej nie maja, wiec bez tego kroku join gubilby je NIELOSOWO.
    from footstats.data.rozszczepienia import scal_pisownie, wczytaj_mape
    otw = scal_pisownie(otw, wczytaj_mape())

    df = zrzut.merge(otw, on=["league", "match_date", "home", "away"],
                     how="left", validate="m:1")
    udane = float(df[list(OTW)].notna().all(axis=1).mean())
    print(f"Zrzut {len(zrzut)} meczow ({zrzut['league'].nunique()} lig)"
          f" | otwarcia dopasowane do {100 * udane:.1f}%")
    if udane < MIN_JOIN:
        raise SystemExit(f"Join ponizej progu {MIN_JOIN:.0%} — przerywam.")
    return df


def test_a(d: pd.DataFrame, p_otw, p_zam, p_mod) -> None:
    print("\n" + "=" * 92)
    print("  TEST A — RUCH LINII. Czy nasza niezgoda z otwarciem przewiduje,")
    print("  dokad pojedzie cena. Ten sam bukmacher w dwoch chwilach.")
    print("=" * 92)
    print(f"  {'wymiar':<14}{'n':>8}{'b (sygnal)':>13}{'SE':>10}{'z':>8}"
          f"{'c (poziom)':>13}{'R2':>8}")
    print("  " + "-" * 88)

    znaki = []
    for nazwa, k in (("gospodarz", 0), ("gosc", 2)):
        dryf = p_zam[:, k] - p_otw[:, k]
        sygnal = p_mod[:, k] - p_otw[:, k]
        X = np.column_stack([sygnal, p_otw[:, k]])
        beta, se = mnk(dryf, X)
        z = beta[1] / se[1] if se[1] > 0 else 0.0
        r2 = 1 - ((dryf - np.column_stack([np.ones(len(X)), X]) @ beta) ** 2).sum() \
            / ((dryf - dryf.mean()) ** 2).sum()
        znaki.append(z)
        print(f"  {nazwa:<14}{len(dryf):>8}{beta[1]:>+13.5f}{se[1]:>10.5f}"
              f"{z:>+8.2f}{beta[2]:>+13.5f}{r2:>8.4f}")

    zgodne = (znaki[0] > 0) == (znaki[1] > 0)
    najslabszy = min(abs(z) for z in znaki)
    print("\n  REGULA DECYZYJNA (zamrozona przed przebiegiem):")
    if not zgodne:
        print("    Wymiary maja PRZECIWNE znaki -> niezgoda modelu z otwarciem")
        print("    jest szumem. Kierunek 'ceny przedmeczowe' zamkniety.")
    elif najslabszy < 2:
        print(f"    Najslabszy wymiar |z|={najslabszy:.2f} < 2 -> niezgoda modelu")
        print("    z otwarciem jest szumem. Kierunek zamkniety.")
    elif znaki[0] > 0:
        print("    b > 0 w OBU wymiarach przy z >= 2 -> model WYPRZEDZA rynek.")
        print("    Pierwszy dodatni wynik tego projektu, wiec tym bardziej:")
        print("    holdout po dacie, pre-rejestrowany osobno, zanim cokolwiek dalej.")
    else:
        print("    b < 0 w OBU wymiarach przy z <= -2 -> model jest")
        print("    ANTYPREDYKCYJNY wobec ruchu linii: tam gdzie sie nie zgadza,")
        print("    rynek jedzie w DRUGA strone. Wynik silny, wart zapisania.")


def test_b(y: np.ndarray, p_otw, p_zam, p_mod) -> None:
    print("\n" + "=" * 92)
    print("  TEST B — deficyt wobec OTWARCIA i wobec ZAMKNIECIA, ten sam")
    print("  bukmacher, te same mecze. Dodatnie = model lepszy od ceny.")
    print("=" * 92)
    b_mod = brier_wieloklasowy(p_mod, y)
    b_otw = brier_wieloklasowy(p_otw, y)
    b_zam = brier_wieloklasowy(p_zam, y)
    for nazwa, b in (("otwarcie Pinnacle", b_otw), ("zamkniecie Pinnacle", b_zam)):
        d = sparowana_roznica(b, b_mod)
        print(f"  model vs {nazwa:<22} Brier ceny {float(b.mean()):.4f}"
              f"  roznica {d['roznica']:+.5f}  SE {d['se']:.5f}  z {d['z']:+.2f}")
    d = sparowana_roznica(b_otw, b_zam)
    print(f"\n  Ile warte jest samo zamkniecie: otwarcie - zamkniecie"
          f" {d['roznica']:+.5f}  SE {d['se']:.5f}  z {d['z']:+.2f}")
    print("  To jest rozmiar nagrody, o ktora gra TEST A.")


def test_c(d: pd.DataFrame, y: np.ndarray, p_mod) -> None:
    kursy = d[list(MAX_PRZED)].to_numpy(dtype=float)
    ok = np.isfinite(kursy).all(axis=1) & (kursy > 1.0).all(axis=1)
    if ok.sum() < 1000:
        print("\n  TEST C: za malo meczow z cena MaxH — pomijam.")
        return
    k, p, yy = kursy[ok], p_mod[ok], y[ok]
    trafiony = np.zeros_like(k, dtype=bool)
    trafiony[np.arange(len(yy)), yy] = True
    maska = (p * k - 1.0) > 0
    n = int(maska.sum())
    if n < 2:
        print("\n  TEST C: zero zakladow o EV > 0.")
        return
    zwroty = np.where(trafiony[maska], k[maska] - 1.0, -1.0)
    se = float(zwroty.std(ddof=1) / np.sqrt(n))
    po = float(zwroty.mean()) - PODATEK
    print("\n" + "=" * 92)
    print("  TEST C — ROI po NAJLEPSZEJ CENIE PRZEDMECZOWEJ (MaxH/MaxD/MaxA)")
    print("=" * 92)
    print(f"  meczow z cena {int(ok.sum())}  zakladow {n}"
          f"  trafione {int(trafiony[maska].sum())}")
    print(f"  ROI brutto {100 * float(zwroty.mean()):+.2f}%"
          f"  po podatku 12% {100 * po:+.2f}%"
          f"  SE {100 * se:.2f}%  z {po / se if se else 0:+.2f}")
    print("  Dla porownania po cenie ZAMKNIECIA (MaxC*, pomiar 04.09):"
          " -15.01% po podatku.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zrzut", nargs="+", required=True)
    ap.add_argument("--otwarcia", required=True)
    args = ap.parse_args()

    d = wczytaj(args.zrzut, args.otwarcia)
    p_otw = devig(d[list(OTW)].to_numpy(dtype=float))
    p_zam = devig(d[list(ZAM)].to_numpy(dtype=float))
    p_mod = d[["pw", "pr", "pp"]].to_numpy(dtype=float) / 100.0

    ok = np.isfinite(p_otw).all(axis=1) & np.isfinite(p_zam).all(axis=1)
    d, p_otw, p_zam, p_mod = d[ok], p_otw[ok], p_zam[ok], p_mod[ok]
    y = d["actual_res"].map(WYNIK_NA_INDEKS).to_numpy(dtype=int)
    print(f"Do pomiaru: {len(y)} meczow z obiema cenami Pinnacle,"
          f" {d['league'].nunique()} lig, {d['match_date'].min()} .. {d['match_date'].max()}")

    test_a(d, p_otw, p_zam, p_mod)
    test_b(y, p_otw, p_zam, p_mod)
    test_c(d, y, p_mod)


if __name__ == "__main__":
    main()
