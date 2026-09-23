#!/usr/bin/env python3
"""Offline runner modelu + generator kuponu AKO o zadanym kursie łącznym.

PO CO: pipeline produkcyjny (`daily_agent`) potrzebuje `DATABASE_URL`, `GROQ_API_KEY`
i kluczy do źródeł kursów. Gdy ich nie ma (świeży kontener, maszyna bez `.env`,
sesja Claude Code w chmurze), model nie da się uruchomić w ogóle. Ten skrypt liczy
predykcje wyłącznie na DARMOWYCH plikach CSV z football-data.co.uk (te same, które
`scrapers/sources/footballdata_source.py` już traktuje jako kotwicę wyników) —
bez bazy, bez sekretów, bez zapisu do prod i bez Telegrama. Wyłącznie stdlib,
więc działa też tam, gdzie nie ma pandas/scipy.

CO LICZY (odwzorowanie ścieżki produkcyjnej z `src/footstats/core/`):
  - `form.sily_ligowe()`          → ratingi dom/wyjazd wobec ligi + blend strzałów
                                    celnych (WAGA_STRZALOW = 0.7),
  - `poisson._baza_ligowa()`      → λ bazowa bez BONUS_DOMOWY (średnia goli
                                    gospodarzy już zawiera atut boiska),
  - `poisson._macierz()`          → macierz Poissona z Laplace smoothing,
  - sufit `p_remis` 0.40 (FAZA 16.3),
  - `lambda_optimizer.load_calibration()` → `data/model_calibration.json`.

CZEGO NIE LICZY (brak danych bez bazy/API): H2H, Importance Index, heurystyka
zmęczenia, HomeFortress, korekty rewanżowe, xG z Understat, warstwa LLM/RAG.
Wszystkie te wejścia mają w `predict_match()` neutralne wartości domyślne (1.0),
więc wynik odpowiada czystej ścieżce Poisson + siła ligowa.

RÓŻNICA WOBEC REPO — `_wspolna_liga()`: `_baza_ligowa()` wymaga, by obie drużyny
miały MIN_MECZOW_LIGOWYCH w lidze BIEŻĄCEGO meczu. Na starcie sezonu drużyna po
awansie/spadku tego nie spełnia i repo schodzi na `_oblicz_sile_wazona()`, który
liczy siłę z 15 ostatnich meczów PARY razem — miesza poziomy rozgrywkowe i daje
λ typu 0.9 vs 2.98. Zamiast tego bierzemy tabelę dywizji, w której OBIE drużyny
realnie grały (najczęściej ubiegłosezonowa), a poziom golowy skalujemy średnimi
dywizji, w której mecz się odbywa. Gdy wspólnej dywizji nie ma — brak predykcji,
mecz wypada z puli (odpowiednik `None` z `predict_match`).

UWAGA: kurs łączny AKO to iloczyn kursów, czyli założenie NIEZALEŻNOŚCI nóg
(patrz `betbuilder.Kombinacja`). To narzędzie analityczne, nie porada
inwestycyjna — zakłady to gra o ujemnej wartości oczekiwanej po marży bukmachera.

Użycie:
    python scripts/kupon_offline.py --kurs 50
    python scripts/kupon_offline.py --kurs 20 --max-nog 3 --top 30
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import urllib.request
from datetime import datetime
from itertools import combinations
from pathlib import Path

# ── Stałe z src/footstats/config.py ───────────────────────────────────────────
MAX_GOLE = 8
BONUS_DOMOWY = 1.15          # nieużywany w ścieżce ligowej — patrz `_baza_ligowa`
WAGA_STRZALOW = 0.7
OKNO_LIGOWE = 30
MIN_MECZOW_LIGOWYCH = 6
PR_CAP = 0.40                # sufit p_remis (FAZA 16.3)
MIN_EV_PCT = 3.0             # core/value_bet.py

# Waga modelu w mieszance z rynkiem. Rynek jest lepiej skalibrowany niż model
# (walk-forward repo: Brier 0.609 model vs 0.600 rynek; live settled acc 32.8%),
# więc szanse kuponu raportujemy też po zmieszaniu 50/50, nie tylko z modelu.
W_MODEL = 0.5

REPO = Path(__file__).resolve().parent.parent
BASE_URL = "https://www.football-data.co.uk"
# Ligi pokrywane przez football-data.co.uk (nadzbiór KODY_LIG z footballdata_source).
KODY_LIG = ("E0", "E1", "E2", "E3", "EC", "SC0", "SC1", "SP1",
            "D1", "I1", "F1", "N1", "P1", "B1", "T1")

RYNKI: tuple[tuple[str, str, str, str], ...] = (
    ("1",         "p1",      "B365H",    "AvgH"),
    ("X",         "pX",      "B365D",    "AvgD"),
    ("2",         "p2",      "B365A",    "AvgA"),
    ("Over 2.5",  "over25",  "B365>2.5", "Avg>2.5"),
    ("Under 2.5", "under25", "B365<2.5", "Avg<2.5"),
)


# ── Pobieranie danych ─────────────────────────────────────────────────────────
def _pobierz(url: str, cel: Path, ttl_s: int = 6 * 3600) -> str:
    """Treść pliku z cache (TTL jak w footballdata_source) albo z sieci."""
    if cel.exists() and (datetime.now().timestamp() - cel.stat().st_mtime) < ttl_s:
        return cel.read_text("utf-8", errors="ignore")
    with urllib.request.urlopen(url, timeout=30) as resp:  # nosec B310 — stały https
        tekst = resp.read().decode("utf-8", errors="ignore")
    cel.parent.mkdir(parents=True, exist_ok=True)
    cel.write_text(tekst, encoding="utf-8")
    return tekst


def _f(v: object) -> float | None:
    """Liczba albo None — puste pola CSV są w tych plikach normą."""
    try:
        return float(str(v))
    except (TypeError, ValueError):
        return None


def wczytaj_historie(cache: Path, sezony: tuple[str, ...]) -> list[dict]:
    """Mecze rozegrane (wyniki + strzały celne) ze wszystkich lig i sezonów."""
    mecze: list[dict] = []
    for sezon in sezony:
        for kod in KODY_LIG:
            try:
                tekst = _pobierz(f"{BASE_URL}/mmz4281/{sezon}/{kod}.csv",
                                 cache / f"{kod}_{sezon}.csv")
            except OSError:
                continue  # brak pliku dla ligi/sezonu → pomiń, reszta liczy się dalej
            for w in csv.DictReader(io.StringIO(tekst)):
                gole_g, gole_a = _f(w.get("FTHG")), _f(w.get("FTAG"))
                if gole_g is None or gole_a is None or not w.get("HomeTeam"):
                    continue
                try:
                    data = datetime.strptime(w["Date"], "%d/%m/%Y")
                except (ValueError, KeyError):
                    continue
                mecze.append({
                    "data": data, "league": kod,
                    "gospodarz": w["HomeTeam"].strip(), "goscie": w["AwayTeam"].strip(),
                    "gole_g": gole_g, "gole_a": gole_a,
                    "hst": _f(w.get("HST")), "ast": _f(w.get("AST")),
                })
    mecze.sort(key=lambda m: m["data"])
    return mecze


def wczytaj_fixtures(cache: Path) -> list[dict]:
    """Nadchodzące mecze z kursami (plik `fixtures.csv`, TTL 1h)."""
    tekst = _pobierz(f"{BASE_URL}/fixtures.csv", cache / "fixtures.csv", ttl_s=3600)
    return [w for w in csv.DictReader(io.StringIO(tekst.lstrip("﻿")))
            if w.get("HomeTeam")]


# ── Kalibracja (lambda_optimizer.load_calibration) ────────────────────────────
def kalibracja() -> tuple[float, float]:
    """(factor_home, factor_away) z pliku JSON, clamp 0.85-1.15; braki → (1.0, 1.0)."""
    try:
        d = json.loads((REPO / "data" / "model_calibration.json").read_text("utf-8"))
        return (max(0.85, min(1.15, float(d.get("factor_home", 1.0)))),
                max(0.85, min(1.15, float(d.get("factor_away", 1.0)))))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return 1.0, 1.0


# ── Siły ligowe (form._tabela_ratingow / sily_ligowe) ─────────────────────────
def _srednia(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _tabela_ratingow(mecze: list[dict], kol_dom: str, kol_wyj: str,
                     okno: int = OKNO_LIGOWE) -> tuple[dict, float, float] | None:
    """Ratingi dom/wyjazd wobec średniej ligowej dla dowolnej pary kolumn.

    Ta sama arytmetyka służy golom i strzałom celnym — ilorazy są bezwymiarowe,
    więc λ zostaje w golach niezależnie od tego, czym mierzymy siłę.
    """
    dane = [m for m in mecze if m[kol_dom] is not None and m[kol_wyj] is not None]
    if not dane:
        return None
    sr_dom = _srednia([m[kol_dom] for m in dane])
    sr_wyj = _srednia([m[kol_wyj] for m in dane])
    if not sr_dom or not sr_wyj or sr_dom <= 0 or sr_wyj <= 0:
        return None

    tabela: dict[str, dict] = {}
    for druzyna in {m["gospodarz"] for m in dane} | {m["goscie"] for m in dane}:
        dom = [m for m in dane if m["gospodarz"] == druzyna][-okno:]
        wyj = [m for m in dane if m["goscie"] == druzyna][-okno:]
        if len(dom) + len(wyj) < MIN_MECZOW_LIGOWYCH:
            continue  # poniżej tylu meczów rating jest szumem udającym wiedzę
        tabela[druzyna] = {
            "atak_dom":   (_srednia([m[kol_dom] for m in dom]) / sr_dom) if dom else 1.0,
            "atak_wyj":   (_srednia([m[kol_wyj] for m in wyj]) / sr_wyj) if wyj else 1.0,
            "obrona_dom": (_srednia([m[kol_wyj] for m in dom]) / sr_wyj) if dom else 1.0,
            "obrona_wyj": (_srednia([m[kol_dom] for m in wyj]) / sr_dom) if wyj else 1.0,
            "mecze": len(dom) + len(wyj),
        }
    return (tabela, sr_dom, sr_wyj) if tabela else None


def sily_ligowe(mecze_ligi: list[dict]) -> tuple[dict, float, float] | None:
    """Siła każdej drużyny wobec ligi: gole zmieszane ze strzałami celnymi."""
    z_goli = _tabela_ratingow(mecze_ligi, "gole_g", "gole_a")
    if not z_goli:
        return None  # liga bez goli — każdy iloraz byłby dzieleniem przez zero
    tabela, sr_dom, sr_wyj = z_goli

    ze_strzalow = _tabela_ratingow(mecze_ligi, "hst", "ast")
    if WAGA_STRZALOW > 0 and ze_strzalow:
        tab_s, w = ze_strzalow[0], WAGA_STRZALOW
        for druzyna, wpis in tabela.items():
            s = tab_s.get(druzyna)
            if not s:
                continue  # ta drużyna nie ma strzałów — zostaje na golach
            for klucz in ("atak_dom", "atak_wyj", "obrona_dom", "obrona_wyj"):
                wpis[klucz] = w * s[klucz] + (1 - w) * wpis[klucz]
    return tabela, sr_dom, sr_wyj


# ── Poisson (poisson._macierz) ────────────────────────────────────────────────
def _pmf(lam: float, n: int) -> list[float]:
    return [math.exp(-lam) * lam ** k / math.factorial(k) for k in range(n)]


def macierz(lambda_g: float, lambda_a: float, n: int = MAX_GOLE + 1) -> tuple:
    """Macierz Poissona z Laplace smoothing → (pw, pr, pp, btts, over25, top5)."""
    eps = 1e-8
    pg = [(p + eps) / (1.0 + n * eps) for p in _pmf(lambda_g, n)]
    pa = [(p + eps) / (1.0 + n * eps) for p in _pmf(lambda_a, n)]
    M = [[pg[i] * pa[j] for j in range(n)] for i in range(n)]
    suma = sum(sum(r) for r in M) or 1.0
    M = [[v / suma for v in r] for r in M]

    pw = sum(M[i][j] for i in range(n) for j in range(n) if i > j)
    pr = sum(M[i][i] for i in range(n))
    pp = sum(M[i][j] for i in range(n) for j in range(n) if i < j)
    btts = (1 - pg[0]) * (1 - pa[0])
    over25 = 1.0 - sum(M[i][j] for i in range(n) for j in range(n) if i + j <= 2)
    top5 = sorted(((M[i][j], i, j) for i in range(n) for j in range(n)), reverse=True)[:5]
    return pw, pr, pp, btts, over25, top5


def _wspolna_liga(g: str, a: str, liga_meczu: str, historia: list[dict],
                  cache_lig: dict) -> tuple[str | None, tuple | None]:
    """Liga odniesienia, w której OBIE drużyny mają rating (patrz docstring modułu)."""
    kandydaci = [liga_meczu] + [x for x in KODY_LIG if x != liga_meczu]
    for liga in kandydaci:
        if liga not in cache_lig:
            cache_lig[liga] = sily_ligowe([m for m in historia if m["league"] == liga])
        tab = cache_lig[liga]
        if tab and g in tab[0] and a in tab[0]:
            return liga, tab
    return None, None


def predykcja(g: str, a: str, liga: str, historia: list[dict],
              cache_lig: dict) -> dict | None:
    """Predykcja meczu albo None, gdy brak wspólnej ligi odniesienia."""
    fh, fa = kalibracja()
    liga_ref, tab = _wspolna_liga(g, a, liga, historia, cache_lig)
    if tab is None:
        return None
    tabela, sr_dom_ref, sr_wyj_ref = tab

    # Ratingi z ligi odniesienia, poziom golowy z ligi, w której mecz się odbywa.
    tab_meczu = cache_lig.get(liga)
    sr_dom, sr_wyj = (tab_meczu[1], tab_meczu[2]) if tab_meczu else (sr_dom_ref, sr_wyj_ref)

    sg, sa = tabela[g], tabela[a]
    lambda_g = max(0.05, sg["atak_dom"] * sa["obrona_wyj"] * sr_dom) * fh
    lambda_a = max(0.05, sa["atak_wyj"] * sg["obrona_dom"] * sr_wyj) * fa
    lambda_g, lambda_a = max(0.05, lambda_g), max(0.05, lambda_a)

    pw, pr, pp, btts, over25_raw, top5 = macierz(round(lambda_g, 4), round(lambda_a, 4))
    suma = (pw + pr + pp) or 1.0
    pw, pr, pp = pw / suma, pr / suma, pp / suma
    if pr > PR_CAP:
        nadwyzka, pr = pr - PR_CAP, PR_CAP
        reszta = (pw + pp) or 1.0
        pw += nadwyzka * (pw / reszta)
        pp += nadwyzka * (pp / reszta)

    return {
        "gospodarz": g, "gosc": a, "liga": liga,
        "sciezka": "liga" if liga_ref == liga else f"ref:{liga_ref}",
        "lambda_g": round(lambda_g, 2), "lambda_a": round(lambda_a, 2),
        "p1": pw, "pX": pr, "p2": pp, "btts": btts,
        "over25": min(over25_raw / suma, 1.0), "under25": 1 - min(over25_raw / suma, 1.0),
        "n_g": sg["mecze"], "n_a": sa["mecze"],
        "top5": [(f"{i}:{j}", round(v * 100, 1)) for v, i, j in top5],
    }


# ── Rynek i kandydaci ─────────────────────────────────────────────────────────
def _devig(kursy: list[float | None]) -> list[float] | None:
    """Prawdopodobieństwa rynkowe bez marży — normalizacja proporcjonalna."""
    if any(k is None or k <= 1.0 for k in kursy):
        return None
    surowe = [1 / k for k in kursy]  # type: ignore[operator]
    s = sum(surowe)
    return [x / s for x in surowe]


def zbuduj_kandydatow(historia: list[dict],
                      fixtures: list[dict]) -> tuple[list[dict], list[str]]:
    """Wszystkie typy (1/X/2, O/U 2.5) z predykcją, kursem, EV i mieszanką z rynkiem."""
    cache_lig: dict = {}
    kandydaci: list[dict] = []
    braki: list[str] = []

    for w in fixtures:
        liga, g, a = w.get("Div", ""), w["HomeTeam"].strip(), w["AwayTeam"].strip()
        pred = predykcja(g, a, liga, historia, cache_lig)
        if pred is None:
            braki.append(f"{liga} {g}-{a}")
            continue
        pred["kiedy"] = f"{w.get('Date','')} {w.get('Time','')}".strip()

        p_rynek: dict[str, float] = {}
        m1x2 = _devig([_f(w.get("AvgH")), _f(w.get("AvgD")), _f(w.get("AvgA"))])
        if m1x2:
            p_rynek.update({"1": m1x2[0], "X": m1x2[1], "2": m1x2[2]})
        mou = _devig([_f(w.get("Avg>2.5")), _f(w.get("Avg<2.5"))])
        if mou:
            p_rynek.update({"Over 2.5": mou[0], "Under 2.5": mou[1]})

        for nazwa, pole, kol_kurs, kol_avg in RYNKI:
            kurs = _f(w.get(kol_kurs)) or _f(w.get(kol_avg))
            if not kurs or kurs <= 1.01:
                continue
            p = pred[pole]
            pm = p_rynek.get(nazwa)
            p_mix = W_MODEL * p + (1 - W_MODEL) * pm if pm else p
            kandydaci.append({
                "mecz": f"{g} – {a}", "liga": liga, "kiedy": pred["kiedy"],
                "typ": nazwa, "kurs": kurs,
                "p": p, "p_rynek": pm, "p_mix": p_mix,
                "ev_pct": (p * kurs - 1) * 100,
                "ev_mix_pct": (p_mix * kurs - 1) * 100,
                "kurs_fair": 1 / p if p > 0 else float("inf"),
                "pred": pred,
            })
    return kandydaci, braki


# ── Budowa kuponu ─────────────────────────────────────────────────────────────
def _iloczyn(xs: list[float]) -> float:
    wynik = 1.0
    for x in xs:
        wynik *= x
    return wynik


def szukaj_kuponu(kandydaci: list[dict], cel: float, tol: float = 0.10,
                  max_nog: int = 6, min_ev: float = MIN_EV_PCT) -> dict | None:
    """Kupon o kursie łącznym ≈ `cel`, maksymalizujący łączne p_mix.

    Jedna noga na mecz: typy z tego samego spotkania są skorelowane, a iloczyn
    kursów zakłada niezależność (patrz `betbuilder.Kombinacja`).
    """
    najlepsze: dict[str, dict] = {}
    for k in kandydaci:
        if k["ev_mix_pct"] < min_ev:
            continue
        b = najlepsze.get(k["mecz"])
        if b is None or k["ev_mix_pct"] > b["ev_mix_pct"]:
            najlepsze[k["mecz"]] = k
    nogi = sorted(najlepsze.values(), key=lambda k: -k["p_mix"])[:24]

    lo, hi = cel * (1 - tol), cel * (1 + tol)
    wynik: dict | None = None
    for n in range(2, max_nog + 1):
        for combo in combinations(nogi, n):
            kurs = _iloczyn([c["kurs"] for c in combo])
            if not lo <= kurs <= hi:
                continue
            p_mix = _iloczyn([c["p_mix"] for c in combo])
            if wynik is None or p_mix > wynik["p_mix"]:
                wynik = {
                    "nogi": combo, "kurs": kurs, "p_mix": p_mix,
                    "p_model": _iloczyn([c["p"] for c in combo]),
                    "p_rynek": _iloczyn([c["p_rynek"] or c["p"] for c in combo]),
                    "ev_mix_pct": (p_mix * kurs - 1) * 100,
                }
    return wynik


# ── Wypis ─────────────────────────────────────────────────────────────────────
def drukuj_kupon(tytul: str, kupon: dict | None) -> None:
    if not kupon:
        print(f"\n{tytul}: brak kombinacji w zadanym przedziale kursu")
        return
    print(f"\n=== {tytul} ===")
    for n in sorted(kupon["nogi"], key=lambda x: x["kiedy"]):
        pred = n["pred"]
        rynek = f"{n['p_rynek'] * 100:.1f}%" if n["p_rynek"] else "n/d"
        print(f"  {n['kiedy']}  [{n['liga']}] {n['mecz']}")
        print(f"      typ {n['typ']:<10} kurs {n['kurs']:.2f} | p_model {n['p'] * 100:5.1f}%"
              f" | p_rynek {rynek:>6} | p_mix {n['p_mix'] * 100:5.1f}%"
              f" | EV_mix {n['ev_mix_pct']:+5.1f}% | λ {pred['lambda_g']}-{pred['lambda_a']}"
              f" [{pred['sciezka']}]")
    print(f"  → KURS ŁĄCZNY {kupon['kurs']:.2f} | nóg {len(kupon['nogi'])}"
          f" | p_mix {kupon['p_mix'] * 100:.2f}% | p_model {kupon['p_model'] * 100:.2f}%"
          f" | p_rynek {kupon['p_rynek'] * 100:.2f}% | EV_mix {kupon['ev_mix_pct']:+.1f}%")


def diagnostyka(kandydaci: list[dict]) -> None:
    """Jak bardzo model rozjeżdża się z rynkiem — surowy sygnał o jego pewności siebie."""
    pary = [(k["p"], k["p_rynek"]) for k in kandydaci if k["p_rynek"]]
    lam = [k["pred"]["lambda_g"] + k["pred"]["lambda_a"] for k in kandydaci if k["typ"] == "1"]
    if not pary or not lam:
        return
    mae = sum(abs(a - b) for a, b in pary) / len(pary)
    print(f"Diagnostyka: |p_model − p_rynek| średnio {mae * 100:.1f} pkt proc."
          f" na {len(pary)} typach; średnia λ_total {sum(lam) / len(lam):.2f}"
          f" (typowa liga: 2.5–2.8)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Offline model + kupon o zadanym kursie")
    ap.add_argument("--kurs", type=float, default=50.0, help="docelowy kurs łączny")
    ap.add_argument("--tol", type=float, default=0.10, help="tolerancja kursu (0.10 = ±10%%)")
    ap.add_argument("--max-nog", type=int, default=6, help="maksymalna liczba nóg")
    ap.add_argument("--min-ev", type=float, default=MIN_EV_PCT, help="minimalne EV_mix nogi [%%]")
    ap.add_argument("--sezony", default="2627,2526", help="sezony football-data.co.uk")
    ap.add_argument("--top", type=int, default=15, help="ile value betów wypisać")
    ap.add_argument("--cache", default=str(REPO / "cache" / "kupon_offline"))
    args = ap.parse_args()

    cache = Path(args.cache)
    historia = wczytaj_historie(cache, tuple(s.strip() for s in args.sezony.split(",")))
    fixtures = wczytaj_fixtures(cache)
    print(f"Historia: {len(historia)} meczów | nadchodzących meczów: {len(fixtures)}")

    kandydaci, braki = zbuduj_kandydatow(historia, fixtures)
    print(f"Z predykcją: {len({k['mecz'] for k in kandydaci})}/{len(fixtures)} meczów"
          f" ({len(kandydaci)} typów); bez predykcji: {len(braki)}")
    diagnostyka(kandydaci)

    value = sorted([k for k in kandydaci if k["ev_mix_pct"] >= args.min_ev],
                   key=lambda k: -k["ev_mix_pct"])
    print(f"\nValue bety (EV_mix ≥ {args.min_ev}%): {len(value)}")
    for k in value[:args.top]:
        print(f"  EV_mix {k['ev_mix_pct']:+6.1f}%  {k['typ']:<10} @{k['kurs']:.2f}"
              f"  p_mix {k['p_mix'] * 100:5.1f}%  [{k['liga']}] {k['mecz']}  ({k['kiedy']})")

    drukuj_kupon(f"KUPON — kurs ≈ {args.kurs:.0f}",
                 szukaj_kuponu(kandydaci, cel=args.kurs, tol=args.tol,
                               max_nog=args.max_nog, min_ev=args.min_ev))
    print("\nKurs łączny AKO = iloczyn kursów, czyli założenie niezależności nóg."
          "\nNarzędzie analityczne — nie porada inwestycyjna.")


if __name__ == "__main__":
    main()
