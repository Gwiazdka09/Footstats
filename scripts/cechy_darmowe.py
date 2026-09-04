#!/usr/bin/env python
"""cechy_darmowe.py — czy odpoczynek, zagęszczenie i beniaminkostwo niosą coś,
czego NIE MA już w prognozie.

===========================  PRE-REJESTRACJA  ===============================
Spisana 2026-09-04, PRZED policzeniem czegokolwiek z tych cech.

DLACZEGO TO PYTANIE, I DLACZEGO AKURAT TERAZ. Rozkład Murphy'ego pokazał, że
wąskim gardłem modelu jest ROZDZIELCZOŚĆ (~0.037 przy niepewności ~0.62), a nie
kalibracja (ECE 0.03, dopasowanie kalibratora pogarsza out-of-sample). Niska
rozdzielczość znaczy brak INFORMACJI, więc jedyne, co ją podniesie, to nowa
zmienna — nie inne przetworzenie tych samych liczb. Te pięć cech wyprowadza się
z `full_dataset.parquet` za darmo: żadnego nowego źródła, żadnego pobierania.
To najtańsze miejsce, gdzie w ogóle można szukać.

DWA ŹRÓDŁA PROGNOZY, DWA RÓŻNE PYTANIA — i to jest sedno tego pomiaru:
  `model`   — czy NASZ model przeocza tę cechę;
  `pinn`    — czy przeocza ją ZAMKNIĘCIE PINNACLE, czyli najostrzejsza cena rynku.

Rozdzielenie jest konieczne, bo wyniki znaczą coś zupełnie innego. Cecha, która
poprawia tylko `model`, mówi wyłącznie, że jesteśmy gorsi od rynku w miejscu,
które rynek już umie wycenić — dokładnie to wiemy od 04.09 (39 lig na 39
ujemne). Dopiero cecha poprawiająca `pinn` byłaby informacją, której NIE MA
w cenie, czyli jedyną rzeczą, z której da się zarobić.

PIĘĆ CECH, USTALONYCH Z GÓRY I ZAMKNIĘTYCH. Nie dołożymy szóstej po zobaczeniu
wyników; 14.08 przetestowano 52 podzbiory i zero przeżyło holdout.
  1. `roznica_odpoczynku`   dni od poprzedniego meczu: gospodarz − gość, [-14,14]
  2. `roznica_zageszczenia` mecze w ostatnich 14 dniach: gospodarz − gość
  3. `roznica_nowosci`      beniaminek(gospodarz) − beniaminek(gość), gdzie
                            beniaminek = drużyna z <5 meczami w TEJ lidze
                            w ostatnich 365 dniach. To miejsce, gdzie model ma
                            NAJMNIEJ historii, więc a priori najsłabszy.
  4. `glebokosc_sezonu`     średnia z liczby meczów rozegranych przez obie
                            drużyny w tym sezonie tej ligi, /38
  5. `min_odpoczynek`       min(dni gospodarza, dni gościa), [0,14] — łapie
                            „ktoś jest zmęczony" bez kierunku

Cechy 1, 2 i 5 liczone po WSZYSTKICH meczach drużyny w zbiorze (mecz to mecz,
niezależnie od rozgrywek). Cechy 3 i 4 są z definicji per liga.

BRAK LOOKAHEADU. Każda cecha używa wyłącznie meczów o dacie ŚCIŚLE WCZEŚNIEJSZEJ
niż mecz oceniany. Podział train/holdout jest po dacie, a współczynniki widzą
tylko train.

METODA. Wielomianowa regresja logistyczna (3 wyjścia, bazowe = remis), liczona
własnym softmaxem na `scipy.optimize` (brak `statsmodels` w środowisku).
  BAZA        : [1, log(pH/pD), log(pA/pD)]  — sama rekalibracja źródła
  ROZSZERZONA : BAZA + cecha
Porównanie jest ZAGNIEŻDŻONE, więc izoluje dokładnie wkład cechy. Rekalibracja
bazy jest konieczna: bez niej cecha mogłaby wygrać tylko dlatego, że naprawia
skalę źródła, a nie dlatego, że cokolwiek wnosi.

Regularyzacja L2 = 1e-6, deklarowana z góry, wyłącznie dla stabilności
numerycznej. Cechy standaryzowane średnią i odchyleniem POLICZONYMI NA TRAIN.

PODZIAŁ, USTALONY Z GÓRY:
  TRAIN   mecze z datą <  2023-01-01
  HOLDOUT mecze z datą >= 2023-01-01

MIARA ROZSTRZYGAJĄCA: sparowana różnica log-loss na HOLDOUCIE (baza − rozszerzona;
dodatnie = cecha pomaga), SE ze sparowanych różnic. Log-loss, nie Brier, bo to
miara własna dopasowania logistycznego. Brier raportowany obok, jako kontrola
spójności kierunku — jeśli obie miary pokazują przeciwne znaki, wynik nie jest
wiarygodny i tak go opisujemy.

KOREKTA WIELOKROTNOŚCI: Šidák po 5 cechach, OSOBNO w każdym źródle. Źródła
odpowiadają na różne pytania, więc nie są jedną rodziną hipotez.

REGUŁA DECYZYJNA, ZAMROŻONA:
  * `pinn`, z >= 2 po korekcie  → cecha niesie informację, której NIE MA w cenie
    zamknięcia. To najmocniejszy możliwy wynik tego skryptu i JEDYNY, który
    uzasadnia pytanie o pieniądze. Dalej wymaga replikacji, nie wdrożenia.
  * `model`, z >= 2, `pinn` z < 2 → cecha zamyka część naszej luki do rynku,
    ale nie daje przewagi NAD rynkiem. Wolno ją wdrożyć do modelu (mniejszy
    Brier to mniejszy Brier), nie wolno na jej podstawie obstawiać.
  * oba z < 2 → cecha martwa. Nie szukamy podzbiorów, lig ani innych progów.

CZEGO TEN POMIAR NIE ZMIENIA. Werdyktu „model nie bije rynku". Nawet wszystkie
pięć cech dodatnich w ramieniu `model` zamyka ułamek luki −0.018..−0.052.

──────────────────────  REPLIKACJA (`--replikacja`)  ────────────────────────
Dopisana 2026-09-04 PO pierwszym przebiegu, PRZED policzeniem czegokolwiek
z tych dwóch kontroli. Powód jest wprost z reguły powyżej: `min_odpoczynek`
wyszedł dodatni na obu źródłach i przeżył korektę Šidáka na zamknięciu Pinnacle
(z=+2.82, p=0.0119), a reguła mówi wtedy „replikacja, NIE wdrożenie". Poniżej
jest to, co ma tę replikację rozstrzygnąć — spisane, zanim ją uruchomiono.

Że ta sekcja powstała po zobaczeniu pierwszego wyniku, jest jej WADĄ, nie
zaletą, i dlatego rozstrzyga tylko o tym, czy pierwszy wynik przeżył. Nie wolno
jej użyć do wyboru innej cechy ani innego progu.

DWIE KONTROLE, obie na cechach, które zapaliły się w pierwszym przebiegu:

  A. ODWRÓCONY PODZIAŁ. Współczynniki uczone na meczach OD 2023-01-01, oceniane
     na wcześniejszych. Efekt realny musi działać w obie strony; efekt będący
     jednym szczęśliwym podziałem — nie musi. Te same dane, inne role, więc to
     kontrola stabilności, nie niezależna próba, i tak ją opisujemy.

  B. ROZBICIE NA LIGI na pierwotnym holdoucie. Efekt szeroki rozkłada się na
     wiele lig; efekt z jednej ligi to ta sama pułapka co 52 podzbiory z 14.08.
     Ligi poniżej 200 meczów holdoutu pomijane — ich pojedyncze `z` to szum.

REGUŁA DECYZYJNA REPLIKACJI, ZAMROŻONA:
  * odwrócony podział z >= 2  ORAZ  >= 60% lig z różnicą dodatnią
        → efekt przeżył. Dalej NIE jest to wdrożenie: wielkość efektu
          (~0.0001 log-loss) jest o dwa rzędy mniejsza niż luka do ceny.
  * cokolwiek innego → traktujemy jak szum, który przeżył jeden podział.
    Nie raportujemy tego jako znaleziska.
=============================================================================

    python scripts/cechy_darmowe.py --zrzut sciezka/zrzut*.parquet
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
from scipy.optimize import minimize  # noqa: E402

from przewaga_nad_rynkiem import p_jednostronne, sparowana_roznica  # noqa: E402

PODZIAL = "2023-01-01"
L2 = 1e-6
MIN_JOIN = 0.99          # ponizej tego progu join jest podejrzany i przerywamy
WYNIK_NA_INDEKS = {"H": 0, "D": 1, "A": 2}
CECHY = ("roznica_odpoczynku", "roznica_zageszczenia", "roznica_nowosci",
         "glebokosc_sezonu", "min_odpoczynek")


# ─────────────────────────── cechy ───────────────────────────────────────────

def _dlugi(df: pd.DataFrame) -> pd.DataFrame:
    """Dwa wiersze na mecz — po jednym na drużynę, z flagą `dom`.

    Wszystkie cechy są własnością DRUŻYNY, nie meczu, więc liczy się je raz
    w tej postaci i dopiero na końcu rozkłada z powrotem na gospodarza i gościa.
    Liczenie osobno dla dom i wyj byłoby tą samą regułą w dwóch kopiach.
    """
    kol = ["rid", "date", "league", "season", "team", "dom"]
    a = pd.DataFrame({"rid": df.index, "date": df["date"], "league": df["league"],
                      "season": df["season"], "team": df["home"], "dom": True})
    b = pd.DataFrame({"rid": df.index, "date": df["date"], "league": df["league"],
                      "season": df["season"], "team": df["away"], "dom": False})
    return pd.concat([a[kol], b[kol]], ignore_index=True)


def _staty_druzyn(df: pd.DataFrame) -> pd.DataFrame:
    """Cztery surowe statystyki na (mecz, drużyna). Zero lookaheadu.

    `dni`  — dni od POPRZEDNIEGO meczu tej drużyny (NaN przy pierwszym);
    `zag`  — mecze tej drużyny w poprzedzających 14 dniach, BEZ bieżącego;
    `rok`  — mecze tej drużyny W TEJ LIDZE w poprzedzających 365 dniach, BEZ
             bieżącego (miara „jak długo tu jest", odporna na to, że sezon
             kalendarzowy w MEX/USA/NOR dzieli się inaczej niż jesień-wiosna);
    `kol`  — ile meczów ta drużyna rozegrała już w tym sezonie tej ligi.

    Wszystkie okna `rolling` liczą także wiersz bieżący, więc odejmujemy 1 —
    w chwili predykcji tego meczu jeszcze nie ma.
    """
    d = _dlugi(df).sort_values(["team", "date"], kind="stable").reset_index(drop=True)
    d["jeden"] = 1.0
    d["dni"] = d.groupby("team", sort=False)["date"].diff().dt.days

    okno = (d.set_index("date").groupby("team", sort=False)["jeden"]
            .rolling("14D").sum())
    assert len(okno) == len(d), "rolling zgubil wiersze — porzadek sie rozjechal"
    d["zag"] = okno.to_numpy() - 1.0

    # Sortowanie po lidze PRZED oknem ligowym: `groupby(...).rolling` zwraca
    # wiersze w kolejnosci grup, wiec musi ona odpowiadac kolejnosci ramki.
    dl = d.sort_values(["league", "team", "date"], kind="stable").reset_index(drop=True)
    okno_rok = (dl.set_index("date").groupby(["league", "team"], sort=False)["jeden"]
                .rolling("365D").sum())
    assert len(okno_rok) == len(dl), "rolling 365D zgubil wiersze"
    dl["rok"] = okno_rok.to_numpy() - 1.0
    dl["kol"] = dl.groupby(["league", "season", "team"], sort=False).cumcount()
    return dl


def zbuduj_cechy(df: pd.DataFrame) -> pd.DataFrame:
    """Klucz meczu + pięć cech. Zwraca NOWĄ ramkę, jeden wiersz na mecz."""
    df = df.sort_values("date", kind="stable").reset_index(drop=True)
    st = _staty_druzyn(df)
    dom = st[st["dom"]].set_index("rid").reindex(df.index)
    wyj = st[~st["dom"]].set_index("rid").reindex(df.index)

    dni_d = dom["dni"].clip(0, 14)
    dni_w = wyj["dni"].clip(0, 14)
    return pd.DataFrame({
        "league": df["league"],
        "match_date": df["date"].astype(str).str[:10],
        "home": df["home"],
        "away": df["away"],
        "roznica_odpoczynku": (dni_d - dni_w).clip(-14, 14),
        "min_odpoczynek": np.minimum(dni_d, dni_w),
        "roznica_zageszczenia": dom["zag"] - wyj["zag"],
        "roznica_nowosci": ((dom["rok"] < 5).astype(float)
                            - (wyj["rok"] < 5).astype(float)),
        "glebokosc_sezonu": (dom["kol"] + wyj["kol"]) / 2.0 / 38.0,
    })


# ─────────────────────── wielomianowa regresja logistyczna ───────────────────

def _straty(W_plaskie: np.ndarray, X: np.ndarray, Y1h: np.ndarray) -> tuple:
    """Ujemna log-wiarygodność softmaxu z bazową klasą D i jej gradient."""
    k = X.shape[1]
    W = W_plaskie.reshape(2, k)
    logity = np.zeros((len(X), 3))
    logity[:, 0] = X @ W[0]      # H
    logity[:, 2] = X @ W[1]      # A  (D zostaje zerem — identyfikacja)
    logity -= logity.max(axis=1, keepdims=True)
    exp = np.exp(logity)
    p = exp / exp.sum(axis=1, keepdims=True)
    n = len(X)
    strata = -np.log(np.clip((p * Y1h).sum(axis=1), 1e-12, None)).mean()
    strata += L2 * float((W ** 2).sum())
    r = (p - Y1h) / n
    grad = np.vstack([X.T @ r[:, 0], X.T @ r[:, 2]]) + 2 * L2 * W
    return strata, grad.ravel()


def dopasuj(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    Y1h = np.zeros((len(y), 3))
    Y1h[np.arange(len(y)), y] = 1.0
    w0 = np.zeros(2 * X.shape[1])
    res = minimize(_straty, w0, args=(X, Y1h), jac=True, method="L-BFGS-B",
                   options={"maxiter": 500})
    return res.x.reshape(2, X.shape[1])


def przewiduj(W: np.ndarray, X: np.ndarray) -> np.ndarray:
    logity = np.zeros((len(X), 3))
    logity[:, 0] = X @ W[0]
    logity[:, 2] = X @ W[1]
    logity -= logity.max(axis=1, keepdims=True)
    exp = np.exp(logity)
    return exp / exp.sum(axis=1, keepdims=True)


def log_loss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return -np.log(np.clip(p[np.arange(len(y)), y], 1e-12, None))


def brier(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    Y1h = np.zeros_like(p)
    Y1h[np.arange(len(y)), y] = 1.0
    return ((p - Y1h) ** 2).sum(axis=1)


# ─────────────────────────── przebieg ────────────────────────────────────────

def wczytaj_zrzut(wzorce: list[str]) -> pd.DataFrame:
    pliki: list[str] = []
    for w in wzorce:
        pliki += sorted(glob.glob(w))
    if not pliki:
        raise SystemExit(f"Zero plikow dla {wzorce}")
    df = pd.concat([pd.read_parquet(p) for p in pliki], ignore_index=True)
    return df[df["actual_res"].isin(WYNIK_NA_INDEKS)].reset_index(drop=True)


def rozklad_zrodla(df: pd.DataFrame, zrodlo: str) -> np.ndarray:
    """Rozkład 1X2 w skali 0..1. NaN w wierszu = wiersz odpada wyżej."""
    if zrodlo == "model":
        return df[["pw", "pr", "pp"]].to_numpy(dtype=float) / 100.0
    kol = ["odds_h_pinn", "odds_d_pinn", "odds_a_pinn"]
    o = df[kol].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        inv = 1.0 / o
    inv[(o <= 1.0) | ~np.isfinite(o)] = np.nan
    return inv / inv.sum(axis=1, keepdims=True)


def zmierz(dane: pd.DataFrame, zrodlo: str, cecha: str,
           odwroc: bool = False, per_liga: bool = False) -> dict | None:
    p = rozklad_zrodla(dane, zrodlo)
    ok = np.isfinite(p).all(axis=1) & np.isfinite(dane[cecha].to_numpy(dtype=float))
    d = dane[ok].reset_index(drop=True)
    p = np.clip(p[ok], 1e-6, 1 - 1e-6)
    if len(d) < 5000:
        return None

    y = d["actual_res"].map(WYNIK_NA_INDEKS).to_numpy(dtype=int)
    baza = np.column_stack([np.ones(len(d)),
                            np.log(p[:, 0] / p[:, 1]),
                            np.log(p[:, 2] / p[:, 1])])
    x = d[cecha].to_numpy(dtype=float)

    tren = (d["match_date"] < PODZIAL).to_numpy()
    if odwroc:
        tren = ~tren                 # replikacja: uczymy sie na pozniejszych
    hold = ~tren
    if tren.sum() < 2000 or hold.sum() < 2000:
        return None

    # Standaryzacja WYLACZNIE po treningu — inaczej holdout wplywalby na skale.
    sr, sd = float(x[tren].mean()), float(x[tren].std())
    xs = (x - sr) / (sd if sd > 0 else 1.0)
    rozsz = np.column_stack([baza, xs])

    W_b = dopasuj(baza[tren], y[tren])
    W_r = dopasuj(rozsz[tren], y[tren])

    p_b = przewiduj(W_b, baza[hold])
    p_r = przewiduj(W_r, rozsz[hold])
    yh = y[hold]

    ll_b, ll_r = log_loss(p_b, yh), log_loss(p_r, yh)
    ll = sparowana_roznica(ll_b, ll_r)
    br = sparowana_roznica(brier(p_b, yh), brier(p_r, yh))
    wynik = {"cecha": cecha, "zrodlo": zrodlo, "n_tren": int(tren.sum()),
             "n_hold": int(hold.sum()), "logloss": ll, "brier": br,
             "wsp": [float(W_r[0, -1]), float(W_r[1, -1])]}
    if per_liga:
        ligi = d["league"].to_numpy()[hold]
        rozbicie = []
        for liga in sorted(set(ligi)):
            m = ligi == liga
            if m.sum() < 200:
                continue
            rozbicie.append({"liga": liga, "n": int(m.sum()),
                             **sparowana_roznica(ll_b[m], ll_r[m])})
        wynik["per_liga"] = rozbicie
    return wynik


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zrzut", nargs="+", required=True)
    ap.add_argument("--replikacja", default=None,
                    help="cechy po przecinku — odwrocony podzial + rozbicie na ligi")
    args = ap.parse_args()

    from footstats.core.testy_przewagi import korekta_sidaka
    from footstats.data.historical_loader import load_cached

    zrzut = wczytaj_zrzut(args.zrzut)
    print(f"Zrzut walk-forward: {len(zrzut)} meczow, {zrzut['league'].nunique()} lig")

    df = load_cached()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    cechy = zbuduj_cechy(df)
    print(f"Cechy policzone na {len(cechy)} meczach datasetu")

    dane = zrzut.merge(cechy, on=["league", "match_date", "home", "away"],
                       how="left", validate="m:1")
    udane = float(dane[list(CECHY)].notna().all(axis=1).mean())
    print(f"Join zrzut<-cechy: {100 * udane:.2f}% wierszy z kompletem cech")
    if udane < MIN_JOIN:
        # Join gubi wiersze CICHO i NIELOSOWO (dziwne pisownie nazw), wiec
        # przekrzywia dokladnie te probe, na ktorej mamy rozstrzygac.
        raise SystemExit(f"Join ponizej progu {MIN_JOIN:.0%} — przerywam.")

    if args.replikacja:
        replikacja(dane, [c.strip() for c in args.replikacja.split(",")])
        return

    wyniki = []
    for zrodlo in ("model", "pinn"):
        for cecha in CECHY:
            w = zmierz(dane, zrodlo, cecha)
            if w is None:
                print(f"  {zrodlo}/{cecha}: pominiete (za malo danych)")
                continue
            wyniki.append(w)
            print(f"  {zrodlo}/{cecha}: n_hold={w['n_hold']}"
                  f" logloss {w['logloss']['roznica']:+.6f}"
                  f" z={w['logloss']['z']:+.2f}", flush=True)

    raport(wyniki, korekta_sidaka)


def replikacja(dane: pd.DataFrame, cechy: list[str]) -> None:
    """Dwie kontrole z sekcji REPLIKACJA. Nie wybiera cech — dostaje je z CLI."""
    print("\n" + "=" * 96)
    print("  REPLIKACJA — czy pierwszy wynik przezyl. Regula zamrozona w docstringu.")
    print("=" * 96)
    for cecha in cechy:
        for zrodlo in ("model", "pinn"):
            print(f"\n  {zrodlo}/{cecha}")
            odw = zmierz(dane, zrodlo, cecha, odwroc=True)
            if odw is None:
                print("    odwrocony podzial: za malo danych")
                continue
            ll = odw["logloss"]
            print(f"    A. ODWROCONY PODZIAL (ucz >= {PODZIAL}, oceniaj wczesniej)")
            print(f"       n={odw['n_hold']}  logloss {ll['roznica']:+.6f}"
                  f"  SE {ll['se']:.6f}  z {ll['z']:+.2f}")

            pl = zmierz(dane, zrodlo, cecha, per_liga=True)
            if pl is None or not pl.get("per_liga"):
                continue
            czesci = pl["per_liga"]
            dod = [c for c in czesci if (c["roznica"] or 0) > 0]
            print("    B. ROZBICIE NA LIGI (holdout pierwotny, >=200 meczow)")
            print(f"       lig: {len(czesci)}   z roznica dodatnia: {len(dod)}"
                  f"  ({100 * len(dod) / len(czesci):.0f}%)")
            naj = sorted(czesci, key=lambda c: -(c["roznica"] or 0))[:3]
            for c in naj:
                print(f"         {c['liga']:<26} n={c['n']:<6}"
                      f" {c['roznica']:+.6f}  z {(c['z'] or 0):+.2f}")

            udzial = len(dod) / len(czesci)
            przeszlo = (ll["z"] or 0) >= 2 and udzial >= 0.60
            print(f"    WERDYKT: {'PRZEZYL' if przeszlo else 'NIE PRZEZYL'}"
                  f"  (odwrocony z={ll['z']:+.2f}, lig dodatnich {100 * udzial:.0f}%)")
            if not przeszlo:
                print("       -> szum, ktory przezyl jeden podzial."
                      " Nie raportujemy jako znaleziska.")


def raport(wyniki: list[dict], korekta_sidaka) -> None:
    print("\n" + "=" * 104)
    print("  CECHY DARMOWE — czy niosa informacje, ktorej nie ma juz w prognozie")
    print(f"  Holdout: mecze od {PODZIAL}. Dodatnie = cecha POMAGA."
          f" p po korekcie Sidaka na {len(CECHY)} cech w kazdym zrodle.")
    print("=" * 104)
    for zrodlo, opis in (("model", "NASZ MODEL — czy my to przeoczamy"),
                         ("pinn", "ZAMKNIECIE PINNACLE — czy RYNEK to przeocza")):
        czesc = [w for w in wyniki if w["zrodlo"] == zrodlo]
        if not czesc:
            continue
        print(f"\n  ZRODLO: {zrodlo}   ({opis})")
        print(f"  {'cecha':<24}{'n hold':>9}{'d logloss':>12}{'SE':>10}{'z':>8}"
              f"{'p_kor':>9}{'d Brier':>11}{'z Brier':>9}")
        print("  " + "-" * 100)
        for w in sorted(czesc, key=lambda x: -(x["logloss"]["z"] or -99)):
            ll, br = w["logloss"], w["brier"]
            pk = korekta_sidaka(p_jednostronne(ll["z"]), len(CECHY)) if ll["z"] else None
            print(f"  {w['cecha']:<24}{w['n_hold']:>9}{ll['roznica']:>+12.6f}"
                  f"{ll['se']:>10.6f}{ll['z']:>+8.2f}"
                  f"{(f'{pk:.4f}' if pk is not None else '-'):>9}"
                  f"{br['roznica']:>+11.6f}{br['z']:>+9.2f}")

    print("\n  REGULA DECYZYJNA (zamrozona przed przebiegiem):")
    mocne_pinn = [w["cecha"] for w in wyniki
                  if w["zrodlo"] == "pinn" and (w["logloss"]["z"] or 0) >= 2
                  and (korekta_sidaka(p_jednostronne(w["logloss"]["z"]), len(CECHY)) or 1) < 0.05]
    mocne_model = [w["cecha"] for w in wyniki
                   if w["zrodlo"] == "model" and (w["logloss"]["z"] or 0) >= 2
                   and (korekta_sidaka(p_jednostronne(w["logloss"]["z"]), len(CECHY)) or 1) < 0.05]
    if mocne_pinn:
        print(f"    NIESIE INFORMACJE SPOZA CENY: {', '.join(mocne_pinn)}")
        print("    -> najmocniejszy mozliwy wynik. Wymaga replikacji, NIE wdrozenia.")
    else:
        print("    Zadna cecha nie poprawia zamkniecia Pinnacle.")
        print("    -> zadna z nich nie daje podstaw do obstawiania.")
    if mocne_model:
        print(f"    Zamyka czesc NASZEJ luki do rynku: {', '.join(mocne_model)}")
        print("    -> wolno wdrozyc do modelu, nie wolno na tym obstawiac.")
    else:
        print("    Zadna cecha nie poprawia rowniez naszego modelu.")
    print("\n  Luka modelu do zdewigowanej ceny to -0.018..-0.052 Briera w kazdej")
    print("  z 39 lig. Zaden wynik tego skryptu tego nie odwraca.")


if __name__ == "__main__":
    main()
