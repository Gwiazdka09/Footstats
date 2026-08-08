"""Porównuje skuteczność Poissona-DC i Bzzoiro-ML na rozliczonych meczach.

PO CO: od 2026-08-07 `model_source` rozdziela oba modele w `predictions`
i `model_log`. To jedyny sposób, żeby odpowiedzieć, czy nasz model realnie
bije poprzednika — do tej pory wszystko leciało pod jedną etykietą.

DWIE TABELE MIERZĄ CO INNEGO i nie wolno ich mylić:
  * `predictions` — typ WYBRANY do kuponu (przez Groq albo filtry), czyli
    skuteczność całego łańcucha selekcji;
  * `model_log`  — argmax samego modelu 1X2, czyli skuteczność modelu
    w oderwaniu od tego, co z nią potem zrobiono.
Rozjazd między nimi to miara tego, ile psuje (albo naprawia) warstwa selekcji.

STATYSTYKA: przedział Wilsona, nie „normalny" — przy małym n i odsetkach
blisko 0/1 ten drugi wychodzi poza [0,1] i sugeruje pewność, której nie ma.
Werdykt zapada TYLKO gdy obie próby przekraczają `MIN_ROZLICZONYCH`, a ich
przedziały się nie nakładają. Inaczej skrypt mówi wprost „za mało danych".

Użycie:
    python -m scripts.porownaj_modele
"""
from __future__ import annotations

import sys
from math import sqrt
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Minimum rozliczonych na model, poniżej którego nie ogłaszamy niczego.
# Projekt ma już zapisane, że na n=6 nie wolno flipować flag — 30 to nadal
# mało, ale poniżej tego przedział Wilsona jest tak szeroki, że każda różnica
# tonie w szumie.
MIN_ROZLICZONYCH = 30

# 1.96 = dwustronne 95%.
_Z = 1.96


def przedzial_wilsona(trafienia: int, n: int, z: float = _Z) -> tuple[float, float]:
    """95% przedział ufności dla odsetka trafień (metoda Wilsona).

    Zwraca (0.0, 1.0) dla pustej próby — „nic nie wiadomo", a nie „zero procent".
    """
    if n <= 0:
        return (0.0, 1.0)
    p = trafienia / n
    mianownik = 1 + z * z / n
    srodek = (p + z * z / (2 * n)) / mianownik
    rozpietosc = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / mianownik
    return (max(0.0, srodek - rozpietosc), min(1.0, srodek + rozpietosc))


def werdykt(trafienia_a: int, n_a: int, trafienia_b: int, n_b: int) -> dict:
    """Czy różnica między modelami jest realna, czy to jeszcze szum."""
    brakuje_a = max(0, MIN_ROZLICZONYCH - n_a)
    brakuje_b = max(0, MIN_ROZLICZONYCH - n_b)
    wynik = {
        "rozstrzygniete": False,
        "lepszy": None,
        "powod": "",
        "brakuje_a": brakuje_a,
        "brakuje_b": brakuje_b,
        "przedzial_a": przedzial_wilsona(trafienia_a, n_a),
        "przedzial_b": przedzial_wilsona(trafienia_b, n_b),
    }

    if brakuje_a or brakuje_b:
        wynik["powod"] = (
            f"za malo rozliczonych (minimum {MIN_ROZLICZONYCH} na model): "
            f"brakuje A={brakuje_a}, B={brakuje_b}"
        )
        return wynik

    dol_a, gora_a = wynik["przedzial_a"]
    dol_b, gora_b = wynik["przedzial_b"]
    if dol_a > gora_b:
        wynik.update(rozstrzygniete=True, lepszy="a", powod="przedzialy rozlaczne")
    elif dol_b > gora_a:
        wynik.update(rozstrzygniete=True, lepszy="b", powod="przedzialy rozlaczne")
    else:
        wynik["powod"] = "przedzialy sie nakladaja — roznica moze byc szumem"
    return wynik


# ─────────────────────────── wykonanie ────────────────────────────────────

def _statystyki(conn, tabela: str) -> dict[str, tuple[int, int]]:
    """{model_source: (trafienia, rozliczone)} — zapytania wypisane wprost."""
    zapytania = {
        "predictions": (
            "SELECT COALESCE(NULLIF(model_source,''),'(brak)') zr,"
            " COUNT(tip_correct) n, COALESCE(SUM(tip_correct),0) traf"
            " FROM predictions GROUP BY 1"
        ),
        "model_log": (
            "SELECT COALESCE(NULLIF(model_source,''),'(brak)') zr,"
            " COUNT(tip_correct) n, COALESCE(SUM(tip_correct),0) traf"
            " FROM model_log GROUP BY 1"
        ),
    }
    return {
        r["zr"]: (int(r["traf"]), int(r["n"]))
        for r in conn.execute(zapytania[tabela]).fetchall()
    }


def _raport(nazwa: str, opis: str, dane: dict[str, tuple[int, int]]) -> None:
    print(f"\n=== {nazwa} — {opis} ===")
    if not dane:
        print("  brak danych")
        return
    for model, (traf, n) in sorted(dane.items()):
        if n == 0:
            print(f"  {model:12} 0 rozliczonych — brak podstawy do oceny")
            continue
        dol, gora = przedzial_wilsona(traf, n)
        print(f"  {model:12} {traf:4}/{n:<4} = {traf / n * 100:5.1f}%"
              f"   95% CI [{dol * 100:4.1f}% – {gora * 100:4.1f}%]")

    poisson = dane.get("poisson-dc", (0, 0))
    bzzoiro = dane.get("bzzoiro-ml", (0, 0))
    w = werdykt(poisson[0], poisson[1], bzzoiro[0], bzzoiro[1])
    if w["rozstrzygniete"]:
        lepszy = "Poisson-DC" if w["lepszy"] == "a" else "Bzzoiro-ML"
        print(f"  WERDYKT: lepszy {lepszy} ({w['powod']})")
    else:
        print(f"  WERDYKT: nierozstrzygniete — {w['powod']}")


def main() -> None:
    from footstats.utils.db import connect

    with connect() as conn:
        pred = _statystyki(conn, "predictions")
        log = _statystyki(conn, "model_log")

    _raport("predictions", "typ wybrany do kuponu (caly lancuch selekcji)", pred)
    _raport("model_log", "argmax samego modelu 1X2 (model bez selekcji)", log)
    print("\nRozjazd miedzy tabelami mierzy, ile psuje albo naprawia warstwa selekcji.")


if __name__ == "__main__":
    main()
