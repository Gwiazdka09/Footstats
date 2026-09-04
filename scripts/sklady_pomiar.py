#!/usr/bin/env python
"""sklady_pomiar.py — czy absencje w składach niosą coś ponad cenę.

===========================  PRE-REJESTRACJA  ===============================
Spisana 2026-09-04, PRZED pojawieniem się pierwszego wiersza danych. Pierwszy
przebieg produkcyjny z zapisem absencji to `footstats-final` 2026-09-05 11:00.

DLACZEGO TO OSTATNI NIEZMIERZONY KIERUNEK. Wszystko inne padło i zostało
zmierzone: xG nic ponad strzały, pięć cech z terminarza martwych, strzały nie
replikują, rynek golowy gorszy od 1X2, cena kompletna względem modelu (dołożenie
go out-of-sample szkodzi), a nasza niezgoda z ceną jest systematycznie błędna
i tym bardziej, im większa. Składy są jedyną informacją, której rynek NIE ma
natychmiast — publikowane ~60 minut przed meczem, wyceniane przez rynek
w minutach, nie godzinach.

CO MIERZYMY. `daily_phases` zapisuje do `model_log` komplet:
  `p_over_abs`     Over 2.5 modelu PO korekcie o absencje
  `rynek_p_over`   Over 2.5 rynku, zdewigowane, Z TAMTEJ CHWILI
  `edge_absencje`  różnica tych dwóch
  `absencje_udzial_*`, `absencje_pewne_*`  ile i jak pewnych braków

MIARA ROZSTRZYGAJĄCA: sparowana różnica Briera dwuwyjściowego między
`p_over_abs` a `rynek_p_over`, na meczach rozliczonych. Konwencja Briera
identyczna z `rynek_golowy.py` (suma po obu wyjściach), żeby liczby dawały się
zestawić z −0.01752, jakie model bez absencji ma wobec zamknięcia Pinnacle.

JEDEN MOMENT ANALIZY, USTALONY Z GÓRY. Skrypt ODMAWIA policzenia czegokolwiek
poniżej `MIN_ROZLICZONYCH` wierszy. Powód nie jest kosmetyczny: zaglądanie do
rosnącej próby i patrzenie, kiedy „wyszło", to najskuteczniejszy znany sposób
produkowania fałszywych odkryć — każde spojrzenie to osobna szansa na
przekroczenie progu przypadkiem. Do tego czasu wolno wyłącznie LICZYĆ WIERSZE
(`--licz`), bez oglądania wyników.

MOC, POLICZONA Z GÓRY, ŻEBY NIE CZEKAĆ NA COŚ NIEOSIĄGALNEGO. Odchylenie
sparowanych różnic Briera dla dwóch podobnych prognoz wynosi w tym projekcie
~0.186 (zmierzone na n=47 956 w `rynek_golowy.py`). Minimalny wykrywalny efekt
przy z=2 to więc 2*0.186/sqrt(n):
    n=  500  ->  0.0166      n= 2000  ->  0.0083
    n= 1000  ->  0.0118      n= 5000  ->  0.0053
Dla skali: cała przewaga zamknięcia nad otwarciem to 0.00224, a deficyt modelu
wobec ceny golowej 0.01752. Przy n=500 wykryjemy więc TYLKO efekt wielkości
naszego całego deficytu — czyli sytuację, w której absencje odwracają wynik.
Efekty mniejsze wymagają tysięcy meczów i to jest fakt do zaakceptowania
z góry, a nie powód do wcześniejszego zaglądania.

REGUŁA DECYZYJNA, ZAMROŻONA:
  * z >= 2  → absencje niosą informację ponad cenę golową. Byłby to pierwszy
    taki wynik; wymaga replikacji na kolejnej, rozłącznej porcji danych, zanim
    cokolwiek z niego wyniknie.
  * |z| < 2 → nierozstrzygnięte przy tej próbie. Raportujemy przedział ufności
    i to, jaki efekt dałoby się jeszcze wykryć — nie „brak efektu".
  * z <= -2 → korekta o absencje POGARSZA prognozę wobec ceny. Wyłączyć.

KONTROLA OBOWIĄZKOWA: mecze BEZ wykrytych absencji (`absencje_pewne_*` = 0)
muszą dać różnicę nieodróżnialną od zera — tam korekta z definicji nic nie
zmienia. Gdyby i tam coś „wychodziło", mierzylibyśmy nie absencje, tylko
dobór meczów, w których FotMob w ogóle oddał skład.
=============================================================================

    python scripts/sklady_pomiar.py --licz      # tylko licznik wierszy
    python scripts/sklady_pomiar.py             # pomiar, gdy dane wystarcza
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

MIN_ROZLICZONYCH = 500
SD_SPAROWANEJ = 0.186     # zmierzone w rynek_golowy.py na n=47 956

ZAPYTANIE = """
    SELECT p_over_abs, rynek_p_over, edge_absencje,
           absencje_pewne_home, absencje_pewne_away,
           prob_over25, over25_correct, actual_result, match_date, league
      FROM model_log
     WHERE p_over_abs IS NOT NULL
       AND rynek_p_over IS NOT NULL
       AND actual_result IS NOT NULL
       AND over25_correct IS NOT NULL
"""


def brier_dwuwyjsciowy(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Ta sama konwencja co `rynek_golowy.py`: suma po obu wyjsciach."""
    return (p - y) ** 2 + ((1 - p) - (1 - y)) ** 2


def mde(n: int) -> float:
    """Minimalny wykrywalny efekt przy z=2 i zmierzonym odchyleniu."""
    return 2 * SD_SPAROWANEJ / np.sqrt(n) if n else float("inf")


def pobierz() -> list[dict]:
    from footstats.core.kalibracja_log import _connect
    with _connect() as conn:
        cur = conn.execute(ZAPYTANIE)
        kolumny = [o[0] for o in cur.description]
        return [dict(zip(kolumny, w)) for w in cur.fetchall()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--licz", action="store_true",
                    help="tylko licznik wierszy, BEZ ogladania wynikow")
    args = ap.parse_args()

    wiersze = pobierz()
    rozliczone = [w for w in wiersze if w.get("over25_correct") is not None]
    print(f"model_log z absencjami: {len(wiersze)} wierszy,"
          f" rozliczonych {len(rozliczone)}")
    print(f"prog analizy: {MIN_ROZLICZONYCH}"
          f"   minimalny wykrywalny efekt przy tym n: {mde(len(rozliczone)):.4f}")

    if args.licz:
        return
    if len(rozliczone) < MIN_ROZLICZONYCH:
        # To nie jest uprzejmosc. Zagladanie do rosnacej proby i patrzenie,
        # kiedy „wyszlo", to najskuteczniejszy znany sposob produkowania
        # falszywych odkryc — kazde spojrzenie to osobna szansa na przypadek.
        raise SystemExit(
            f"ODMOWA: {len(rozliczone)} < {MIN_ROZLICZONYCH} rozliczonych."
            " Do tego czasu wolno wylacznie liczyc wiersze (--licz).")

    p_mod = np.array([float(w["p_over_abs"]) for w in rozliczone])
    p_ryn = np.array([float(w["rynek_p_over"]) for w in rozliczone])
    y = np.array([1.0 if _over(w) else 0.0 for w in rozliczone])
    if p_mod.max() > 1.5:          # zapis bywa w procentach
        p_mod, p_ryn = p_mod / 100.0, p_ryn / 100.0

    b_mod = brier_dwuwyjsciowy(p_mod, y)
    b_ryn = brier_dwuwyjsciowy(p_ryn, y)
    _raport("WSZYSTKIE", b_ryn - b_mod)

    pewne = np.array([(w.get("absencje_pewne_home") or 0)
                      + (w.get("absencje_pewne_away") or 0) for w in rozliczone])
    if (pewne == 0).sum() >= 100:
        _raport("KONTROLA: bez wykrytych absencji", (b_ryn - b_mod)[pewne == 0])
        print("    Ta grupa MUSI wyjsc nieodroznialna od zera — korekta z definicji")
        print("    nic tam nie zmienia. Inaczej mierzymy dobor meczow, nie absencje.")


def _over(w: dict) -> bool:
    """Czy w meczu PADLO Over 2.5.

    `over25_correct` mimo nazwy NIE mowi, czy my trafilismy — settlement liczy
    ja jako `oblicz_tip_correct("Over 2.5", wynik)`, czyli ocenia staly typ
    "Over 2.5" wobec wyniku. Jest to wiec wynik faktyczny. Sprawdzone w kodzie,
    nie zgadniete: zla interpretacja odwrocilaby znak calego pomiaru,
    a wykres dalej wygladalby sensownie.
    """
    return bool(w.get("over25_correct"))


def _raport(nazwa: str, d: np.ndarray) -> None:
    n = len(d)
    se = float(d.std(ddof=1) / np.sqrt(n))
    sr = float(d.mean())
    z = sr / se if se > 0 else 0.0
    print(f"\n  {nazwa}: n={n}  roznica {sr:+.5f}  SE {se:.5f}  z {z:+.2f}")
    print(f"    95%: {sr - 1.96 * se:+.5f} .. {sr + 1.96 * se:+.5f}")
    print("    dla skali: deficyt modelu wobec ceny golowej -0.01752")


if __name__ == "__main__":
    main()
