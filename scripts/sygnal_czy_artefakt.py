#!/usr/bin/env python
"""sygnal_czy_artefakt.py — czy wyprzedzanie linii jest NASZE, i ile jest warte.

===========================  PRE-REJESTRACJA  ===============================
Spisana 2026-09-04, PRZED policzeniem czegokolwiek z tych trzech badań.

STAN WYJŚCIOWY. `ruch_linii.py` pokazał, że niezgoda modelu z ceną otwarcia
Pinnacle przewiduje kierunek dryfu do zamknięcia: b=+0.01327 (z=+10.68) na
gospodarzu, +0.01174 (z=+9.88) na gościu, n=70 132. Nieaktualność ceny
otwarcia została wykluczona — efekt jest płaski aż do przerw reprezentacyjnych
(≥14 dni bez meczu: b=+0.01261, z=+3.04).

Zostały trzy dziury i ten skrypt zajmuje się dokładnie nimi.

──────────────────────────────────────────────────────────────────────────────
BADANIE 1 — CZY TO ARTEFAKT POZIOMU CENY.

Regresja miała kontrolę `p_otw`, ale LINIOWĄ. Jeśli zależność dryfu od poziomu
ceny jest krzywa (a przy prawdopodobieństwach ograniczonych do [0,1] zwykle
jest), to liniowa kontrola zostawia resztę, a nasz sygnał — też będący funkcją
poziomu ceny — może tę resztę łapać. Wyglądałoby to identycznie jak informacja.

  A1. KONTROLA NIEPARAMETRYCZNA. Zamiast `c·p_otw` wchodzi 20 kubełków `p_otw`
      jako zmienne zero-jedynkowe. Pochłaniają DOWOLNY kształt zależności od
      poziomu ceny. Jeśli `b` przeżyje, efekt nie może być artefaktem poziomu.

      OGRANICZENIE, ZMIERZONE NA WŁASNYM TEŚCIE I DLATEGO ZAPISANE TUTAJ:
      kubełkowanie pochłania artefakt CZĘŚCIOWO, nie w całości. Na scenie,
      gdzie „sygnał" jest deterministyczną funkcją poziomu ceny i nie niesie
      niczego więcej, 20 kubełków zbija fałszywe z z 766 do 83 — dziewięć razy,
      ale nie do zera. Wewnątrz kubełka zależność wciąż się zmienia, a sygnał
      wciąż ją odtwarza. Dlatego A1 SAMO nie wystarcza i rozstrzyga dopiero
      razem z A2b.

  A2. PLACEBO PRZEZ PERMUTACJĘ W SEZONIE. Predykcje przetasowane wewnątrz
      (liga, sezon). Rozkład brzegowy zostaje, treść meczowa znika. `b` musi
      zniknąć — ale to placebo jest SŁABE: zrywa też związek z poziomem ceny,
      więc nie odróżnia „treści meczowej" od „artefaktu poziomu".

  A2b. PLACEBO PRZEZ PERMUTACJĘ W KUBEŁKU CENY — to jest właściwy test.
      Predykcje przetasowane wyłącznie między meczami o BARDZO PODOBNEJ cenie
      otwarcia (100 kubełków). Placebo zachowuje więc związek sygnału
      z poziomem ceny co do joty, a gubi tylko to, którego meczu dotyczy.
      * `b` przeżywa A2b → efekt jest funkcją POZIOMU CENY, czyli artefaktem;
      * `b` ginie w A2b, żyje w A1 → efekt jest TREŚCIĄ konkretnego meczu.

  A3. SUFIT. Regresja dryfu na FAKTYCZNY WYNIK (zero-jedynkowy) zamiast na
      sygnał modelu. To maksimum, jakie mogłaby osiągnąć prognoza doskonała —
      pokazuje, jaką częścią osiągalnego jest nasze `b`. Bez tego liczba
      0.0133 nie ma skali.

REGUŁA A, ZAMROŻONA:
  * A1 `b` > 0 przy z >= 2 w obu wymiarach ORAZ A2b |z| < 3 w obu
        → sygnał jest treścią meczową, nie artefaktem poziomu ceny.
  * A1 |z| < 2 → efekt był artefaktem poziomu. Wynik z `ruch_linii` upada.
  * A2b |z| >= 3 → placebo o tym samym związku z ceną „wyprzedza" rynek tak
        samo jak my, więc mierzyliśmy poziom ceny, nie mecz. Wynik upada
        niezależnie od A1. To jest test, który ma największą moc obalenia.

──────────────────────────────────────────────────────────────────────────────
BADANIE 2 — CLV, CZYLI SYGNAŁ PRZELICZONY NA CENĘ.

`b` jest w jednostkach prawdopodobieństwa i nic nie mówi o pieniądzach. CLV
(closing line value) mówi: czy kurs, po którym byśmy postawili NASZ typ przy
otwarciu, jest lepszy od kursu tego samego typu na zamknięciu.

  CLV = kurs_otwarcia / kurs_zamkniecia − 1,  dla typu = argmax modelu.

Dodatnie CLV to jedyna wielkość, którą praktycy uznają za wiarygodny predyktor
długoterminowej przewagi — wcześniejszy niż ROI i mniej zaszumiony.

Dwa punkty odniesienia liczone na TYCH SAMYCH meczach, bo sama liczba nic
nie znaczy:
  * typ = faworyt rynku (argmax ceny otwarcia);
  * typ losowy (ziarno ustalone: 20260904).

REGUŁA B, ZAMROŻONA:
  * CLV modelu > 0 przy z >= 2 ORAZ wyraźnie wyżej niż oba odniesienia
        → bijemy linię zamknięcia. Nadal NIE są to pieniądze, dopóki ROI po
          podatku jest ujemne — ale to jest ten wynik, który każe szukać dalej.
  * w przeciwnym razie → `b` nie przekłada się na cenę.

──────────────────────────────────────────────────────────────────────────────
BADANIE 3 — PUNKT ODNIESIENIA DLA ROI, KTÓREGO DOTĄD NIE BYŁO.

ROI −3.99% brutto (cena `MaxH`) było dotąd raportowane bez odpowiedzi na
pytanie „a ile wyszłoby BEZ ŻADNEJ umiejętności". Bez tej liczby nie wiadomo,
czy −3.99% to marża, czy nasza selekcja aktywnie szkodzi.

  * średni overround (Σ 1/kurs) dla PSH, PSCH, MaxH, MaxC;
  * ROI stawiania NA WSZYSTKIE TRZY wyniki każdego meczu — to jest dokładnie
    −(overround − 1) i jest wynikiem zera umiejętności;
  * ROI typu losowego (to samo ziarno).

`MaxH`/`MaxC` to maksimum po ~30 książkach, więc overround bywa tam bliski
100%, a nawet poniżej. Jeśli tak jest, to zero umiejętności daje około zera,
a nasze −3.99% znaczy, że selekcja modelu jest AKTYWNIE SZKODLIWA — co jest
mocniejszym stwierdzeniem niż „nie bijemy marży" i dotąd nie było sprawdzone.

CZEGO ŻADNE Z TYCH BADAŃ NIE ZMIENIA: ROI po podatku było −15.99% i pozostaje.
=============================================================================

    python scripts/sygnal_czy_artefakt.py --zrzut z/*.parquet --otwarcia otw.parquet
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ruch_linii import MAX_PRZED, OTW, ZAM, devig, mnk, wczytaj  # noqa: E402

ZIARNO = 20260904
KUBELKI = 20
WYNIK_NA_INDEKS = {"H": 0, "D": 1, "A": 2}
KOL_MAX_ZAM = ("MaxCH", "MaxCD", "MaxCA")


def _kubelki(x: np.ndarray, ile: int = KUBELKI) -> np.ndarray:
    """Zmienne zero-jedynkowe z kwantyli `x`, bez ostatniej (współliniowość)."""
    progi = np.unique(np.quantile(x, np.linspace(0, 1, ile + 1)[1:-1]))
    idx = np.digitize(x, progi)
    return np.column_stack([(idx == k).astype(float) for k in range(1, idx.max() + 1)])


def badanie_1(p_otw, p_zam, p_mod, y_1h, klucz_sezonu: np.ndarray) -> None:
    print("\n" + "=" * 92)
    print("  BADANIE 1 — czy `b` przezyje kontrole nieparametryczna i placebo")
    print("=" * 92)
    rng = np.random.default_rng(ZIARNO)

    def _permutuj(klucz: np.ndarray) -> np.ndarray:
        perm = np.arange(len(p_mod))
        for grupa in np.unique(klucz):
            idx = np.flatnonzero(klucz == grupa)
            perm[idx] = rng.permutation(idx)
        return perm

    p_sezon = p_mod[_permutuj(klucz_sezonu)]

    print(f"  {'wariant':<34}{'wymiar':<12}{'b':>12}{'SE':>10}{'z':>8}")
    print("  " + "-" * 78)
    wyniki: dict[str, list[float]] = {}
    for nazwa, zrodlo in (("A1 kontrola 20 kubelkow p_otw", p_mod),
                          ("A2 placebo: permutacja w sezonie", p_sezon),
                          ("A2b placebo: permutacja w cenie", None)):
        for wym, k in (("gospodarz", 0), ("gosc", 2)):
            dryf = p_zam[:, k] - p_otw[:, k]
            if zrodlo is None:
                # Permutacja WYLACZNIE miedzy meczami o niemal identycznej
                # cenie otwarcia: zwiazek sygnalu z poziomem ceny zostaje
                # nietkniety, znika tylko to, ktorego meczu sygnal dotyczy.
                klucz_ceny = np.digitize(
                    p_otw[:, k], np.quantile(p_otw[:, k], np.linspace(0, 1, 101)[1:-1]))
                sygnal = p_mod[_permutuj(klucz_ceny), k] - p_otw[:, k]
            else:
                sygnal = zrodlo[:, k] - p_otw[:, k]
            beta, se = mnk(dryf, np.column_stack([sygnal, _kubelki(p_otw[:, k])]))
            z = beta[1] / se[1] if se[1] > 0 else 0.0
            wyniki.setdefault(nazwa, []).append(z)
            print(f"  {nazwa:<34}{wym:<12}{beta[1]:>+12.5f}{se[1]:>10.5f}{z:>+8.2f}")

    # A3 — SUFIT. Porownanie MUSI byc bezwymiarowe.
    #
    # Pierwotnie A3 mialo zestawiac wspolczynniki `b`, i to bylo bledem
    # konstrukcji: `b` jest w jednostkach "na jednostke regresora", a regresory
    # maja tu skrajnie rozne rozrzuty (nasz sygnal ~0.0x, wynik zero-jedynkowy
    # ~0.5). Zestawienie surowych `b` porownywaloby dwie rozne skale i wychodzil
    # z tego nonsens — sufit NIZSZY niz nasz wynik.
    #
    # Bezwymiarowe jest R^2 CZASTKOWE: ile wariancji dryfu tlumaczy regresor
    # PONAD same kubelki ceny. Tak samo liczone dla obu, wiec porownywalne.
    print()

    def _r2_czastkowe(regresor, k):
        baza = _kubelki(p_otw[:, k])
        dryf = p_zam[:, k] - p_otw[:, k]
        b0, _ = mnk(dryf, baza)
        r0 = dryf - np.column_stack([np.ones(len(baza)), baza]) @ b0
        X = np.column_stack([regresor, baza])
        b1, _ = mnk(dryf, X)
        r1 = dryf - np.column_stack([np.ones(len(X)), X]) @ b1
        return 1.0 - float(r1 @ r1) / float(r0 @ r0)

    print(f"  {'A3 SUFIT (R^2 czastkowe, bezwymiarowe)':<46}"
          f"{'model':>10}{'wynik':>10}{'udzial':>9}")
    print("  " + "-" * 75)
    for wym, k in (("gospodarz", 0), ("gosc", 2)):
        r_mod = _r2_czastkowe(p_mod[:, k] - p_otw[:, k], k)
        r_praw = _r2_czastkowe(y_1h[:, k] - p_otw[:, k], k)
        print(f"  {'  ' + wym:<46}{r_mod:>10.5f}{r_praw:>10.5f}"
              f"{100 * r_mod / r_praw:>8.1f}%")

    a1 = wyniki["A1 kontrola 20 kubelkow p_otw"]
    a2b = wyniki["A2b placebo: permutacja w cenie"]
    print("\n  REGULA A (zamrozona przed przebiegiem):")
    if min(a1) >= 2 and max(abs(z) for z in a2b) < 3:
        print("    A1 przezylo kontrole nieparametryczna, A2b placebo martwe")
        print("    -> sygnal jest TRESCIA MECZOWA, nie artefaktem poziomu ceny.")
    elif min(a1) < 2:
        print("    A1 |z| < 2 -> efekt byl artefaktem poziomu ceny. Wynik upada.")
    else:
        print("    A2b: placebo o TYM SAMYM zwiazku z cena wyprzedza rynek tak")
        print("    samo jak my -> mierzylismy poziom ceny, nie mecz. Wynik upada.")


def _clv(kurs_otw: np.ndarray, kurs_zam: np.ndarray, wybor: np.ndarray) -> dict:
    """Średnie CLV wyboru: kurs otwarcia / kurs zamknięcia − 1."""
    i = np.arange(len(wybor))
    o, z = kurs_otw[i, wybor], kurs_zam[i, wybor]
    ok = np.isfinite(o) & np.isfinite(z) & (o > 1.0) & (z > 1.0)
    v = o[ok] / z[ok] - 1.0
    se = float(v.std(ddof=1) / np.sqrt(len(v)))
    return {"n": int(ok.sum()), "clv": float(v.mean()),
            "se": se, "z": float(v.mean()) / se if se > 0 else 0.0}


def badanie_2(d: pd.DataFrame, p_otw, p_mod) -> None:
    print("\n" + "=" * 92)
    print("  BADANIE 2 — CLV. Czy kurs naszego typu na OTWARCIU jest lepszy")
    print("  niz kurs tego samego typu na ZAMKNIECIU. Ten sam bukmacher.")
    print("=" * 92)
    ko = d[list(OTW)].to_numpy(dtype=float)
    kz = d[list(ZAM)].to_numpy(dtype=float)
    rng = np.random.default_rng(ZIARNO)

    # CLV liczone na kursach SUROWYCH miesza dwie rzeczy: ruch linii i zmiane
    # marzy. Pinnacle zacisniete marze w miare zblizania sie meczu (overround
    # 1.0362 na otwarciu, 1.0325 na zamknieciu), wiec surowe CLV jest UJEMNE
    # dla kazdego typu, takze losowego — z definicji, nie z braku przewagi.
    # Wersja bez marzy (odwrotnosci zdewigowanych prawdopodobienstw) usuwa ten
    # wspolny skladnik i dopiero ona mierzy sam ruch linii.
    ko_bm = 1.0 / devig(ko)
    kz_bm = 1.0 / devig(kz)

    warianty = (
        ("typ modelu (argmax p_model)", p_mod.argmax(axis=1)),
        ("typ rynku (argmax ceny otwarcia)", p_otw.argmax(axis=1)),
        ("typ losowy", rng.integers(0, 3, len(d))),
    )
    print(f"  {'wariant':<36}{'n':>8}{'CLV surowe':>12}{'z':>8}"
          f"{'CLV bez marzy':>15}{'z':>8}")
    print("  " + "-" * 87)
    wyniki = {}
    for nazwa, wybor in warianty:
        w = np.asarray(wybor)
        r = _clv(ko, kz, w)
        rb = _clv(ko_bm, kz_bm, w)
        wyniki[nazwa] = r
        wyniki[nazwa + "|bm"] = rb
        print(f"  {nazwa:<36}{r['n']:>8}{100 * r['clv']:>+11.3f}%{r['z']:>+8.2f}"
              f"{100 * rb['clv']:>+14.3f}%{rb['z']:>+8.2f}")

    m = wyniki["typ modelu (argmax p_model)"]
    ref = max(wyniki["typ rynku (argmax ceny otwarcia)"]["clv"],
              wyniki["typ losowy"]["clv"])
    print("\n  REGULA B (zamrozona przed przebiegiem, na CLV SUROWYM):")
    if m["clv"] > 0 and m["z"] >= 2 and m["clv"] > ref:
        print("    CLV dodatnie, istotne i wyzsze od obu odniesien")
        print("    -> bijemy linie zamkniecia. Nadal NIE sa to pieniadze,")
        print("       dopoki ROI po podatku jest ujemne (-15.99%).")
    else:
        print("    -> regula NIESPELNIONA na CLV surowym.")

    mb = wyniki["typ modelu (argmax p_model)|bm"]
    lb = wyniki["typ losowy|bm"]
    print("\n  CLV BEZ MARZY (dopisane po zobaczeniu, ze surowe CLV jest ujemne")
    print("  dla KAZDEGO typu — takze losowego — bo Pinnacle zaciska marze):")
    print(f"    model {100 * mb['clv']:+.3f}% (z={mb['z']:+.2f})"
          f"   losowy {100 * lb['clv']:+.3f}% (z={lb['z']:+.2f})"
          f"   roznica {100 * (mb['clv'] - lb['clv']):+.3f}pp")
    print("    Ta liczba jest wielkoscia realnej przewagi cenowej modelu.")
    print("    Nie zastepuje reguly B — jest jej diagnoza.")


def badanie_3(d: pd.DataFrame, y: np.ndarray, p_mod) -> None:
    print("\n" + "=" * 92)
    print("  BADANIE 3 — ile wyszloby BEZ ZADNEJ umiejetnosci")
    print("=" * 92)
    print(f"  {'cena':<28}{'n':>8}{'overround':>12}{'ROI wszystkie 3':>18}")
    print("  " + "-" * 68)
    rng = np.random.default_rng(ZIARNO)
    trafiony = np.zeros((len(y), 3), dtype=bool)
    trafiony[np.arange(len(y)), y] = True

    for nazwa, kol in (("PSH otwarcie Pinnacle", OTW),
                       ("PSCH zamkniecie Pinnacle", ZAM),
                       ("MaxH najlepsza przedmeczowa", MAX_PRZED),
                       ("MaxC najlepsza zamkniecie", KOL_MAX_ZAM)):
        if any(k not in d.columns for k in kol):
            continue
        k = d[list(kol)].to_numpy(dtype=float)
        ok = np.isfinite(k).all(axis=1) & (k > 1.0).all(axis=1)
        if ok.sum() < 1000:
            continue
        over = (1.0 / k[ok]).sum(axis=1)
        # Stawianie na wszystkie trzy wyniki: zwrot = (kurs trafiony) - 3.
        zwrot = (k[ok] * trafiony[ok]).sum(axis=1) - 3.0
        print(f"  {nazwa:<28}{int(ok.sum()):>8}{over.mean():>12.4f}"
              f"{100 * zwrot.mean() / 3.0:>+17.2f}%")

    print(f"\n  {'selekcja':<36}{'n':>8}{'ROI brutto':>13}{'SE':>9}{'z':>8}")
    print("  " + "-" * 74)
    k = d[list(MAX_PRZED)].to_numpy(dtype=float)
    ok = np.isfinite(k).all(axis=1) & (k > 1.0).all(axis=1)
    for nazwa, wybor in (("model (argmax), cena MaxH", p_mod.argmax(axis=1)),
                         ("losowy, cena MaxH", rng.integers(0, 3, len(d)))):
        w = np.asarray(wybor)[ok]
        kk, tt = k[ok], trafiony[ok]
        zwrot = np.where(tt[np.arange(len(w)), w], kk[np.arange(len(w)), w] - 1.0, -1.0)
        se = float(zwrot.std(ddof=1) / np.sqrt(len(zwrot)))
        print(f"  {nazwa:<36}{len(zwrot):>8}{100 * zwrot.mean():>+12.2f}%"
              f"{100 * se:>8.2f}%{zwrot.mean() / se:>+8.2f}")
    print("\n  ROI 'wszystkie 3' to dokladnie zero umiejetnosci. Nasze ROI")
    print("  czyta sie WYLACZNIE wobec tej liczby, nie wobec zera.")


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
    y_1h = np.zeros((len(y), 3))
    y_1h[np.arange(len(y)), y] = 1.0
    klucz = (d["league"].astype(str) + "|"
             + d["match_date"].astype(str).str[:4]).to_numpy()

    print(f"Do pomiaru: {len(y)} meczow, {d['league'].nunique()} lig")
    badanie_1(p_otw, p_zam, p_mod, y_1h, klucz)
    badanie_2(d, p_otw, p_mod)
    badanie_3(d, y, p_mod)


if __name__ == "__main__":
    main()
