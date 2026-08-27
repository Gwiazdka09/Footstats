"""testy_przewagi.py — czy model bije CENĘ bukmachera, nie tylko własną bazę.

PO CO OSOBNO OD `ranking_rynkow.py`: `przewaga_nad_baza` (D-drugi wybór) mierzy
przewagę modelu nad WŁASNĄ bazą częstości wyników w próbce — to pokazuje, czy
model COKOLWIEK wie o meczu. Nie mówi nic o tym, czy ta wiedza starcza, żeby
pobić MARŻĘ bukmachera. Kurs 1.60 na "1" wbudowuje ~62.5% implikowanego
prawdopodobieństwa (plus marża księgarni) — model może być lepszy od
"zgadywania po bazie" i wciąż systematycznie przepłacać względem tej ceny.
To jedyny test w projekcie mający realny związek z pieniędzmi (patrz
`.claude/rules/wypuszczenie-pl.md`: dodatnia przewaga nad bazą NIE oznacza zysku).

HIPOTEZA ZEROWA: każdy kupon wchodzi z prawdopodobieństwem `1/kurs` (z marżą
księgarni wbudowaną w kurs). Oczekiwana liczba trafień w próbce to suma tych
prawdopodobieństw — RÓŻNYCH dla każdego kuponu, więc suma trafień to zmienna
Poissona-dwumianowa (Poisson binomial), nie zwykły dwumian. Test liczony
DOKŁADNIE (splot), bez przybliżenia normalnego: `n` bywa tu jednocyfrowe
(Over 2.5: n=9 w pomiarze 26.08), a przybliżenie normalne na takiej próbie kłamie.
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)

# Typy 1X2 grupowane pod jedną etykietą — trzy różne zakłady na ten sam mecz
# z różną ceną, ale jeden rynek dla celów tego testu (tak samo liczy się
# "prog" jako średnia implikowanego prawdopodobieństwa WSZYSTKICH trzech).
_TYPY_1X2 = ("1", "X", "2")


def poisson_binomial_cdf(probs: list[float], k: int) -> float:
    """P(X <= k) dla sumy niezależnych prób Bernoulliego o RÓŻNYCH `p`.

    Splot dokładny (programowanie dynamiczne), O(n^2) — dla `n` rzędu
    dziesiątek/setek kuponów to ułamek sekundy, a jedyna tania alternatywa
    (przybliżenie normalne) systematycznie myli się przy małych `n` właśnie
    tam, gdzie ten test jest najbardziej potrzebny (pojedyncze rynki mają
    tu n=9..60, patrz pomiar 26.08).
    """
    n = len(probs)
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0

    # pmf[i] = P(dokladnie i trafien) po uwzglednieniu prob wczytanych dotad.
    pmf = [1.0]
    for p in probs:
        nowy = [0.0] * (len(pmf) + 1)
        for i, masa in enumerate(pmf):
            nowy[i] += masa * (1.0 - p)
            nowy[i + 1] += masa * p
        pmf = nowy
    return sum(pmf[: k + 1])


def korekta_sidaka(p: float, ile_porownan: int) -> float:
    """Korekta Šidáka na wielokrotne porównania: `1 - (1-p)**ile_porownan`.

    Odpowiada na pytanie: jakie jest prawdopodobieństwo zaobserwowania wyniku
    TAK SKRAJNEGO JAK NAJGORSZY z `ile_porownan` niezależnie testowanych
    rynków? Bez tej korekty pojedynczy "istotny" wynik wśród kilku testów to
    zwykły efekt wielokrotnego szukania (data dredging), nie sygnał.
    """
    return 1.0 - (1.0 - p) ** ile_porownan


def kupon_z_legs(rekord: dict) -> dict | None:
    """Dokleja `rynek` wyciągnięty z pierwszej nogi `legs_json`.

    Zwraca None, gdy `legs_json` jest pusty/uszkodzony/bez pola `tip` — kupon
    ma wtedy zostać POMINIĘTY przez wywołującego, nie wywalić całego testu.
    Typy 1X2 ("1"/"X"/"2") grupujemy pod jedną etykietą "1X2" — reszta rynków
    (BTTS, Over/Under 2.5, ...) zostaje bez zmian.
    """
    try:
        legs = json.loads(rekord.get("legs_json") or "")
        tip = str(legs[0]["tip"])
    except (json.JSONDecodeError, TypeError, KeyError, IndexError) as e:
        # DEBUG, nie WARNING: uszkodzony/pusty `legs_json` w starych wierszach
        # to znany stan danych, nie awaria toczacego sie przebiegu — patrz
        # `test_ciche_except_audit.py` (log przy kazdym przebiegu byłby szumem,
        # ale calkowita cisza ukrywalaby, ile kuponow raport realnie pomija).
        log.debug("kupon_z_legs: pomijam kupon z uszkodzonym legs_json: %s", e)
        return None
    rynek = "1X2" if tip in _TYPY_1X2 else tip
    return {**rekord, "rynek": rynek}


def policz_przewage(kupony: list[dict]) -> dict:
    """Test przewagi nad kursem bukmachera, osobno per rynek.

    Wejście to SUROWE wiersze `coupons` (`status`, `total_odds`, `stake_pln`,
    `payout_pln`, `legs_json`) — parsowanie `legs_json` i filtr kursu dzieją
    się TUTAJ, żeby obie ścieżki błędów (kurs <= 1.0, zepsuty `legs_json`)
    były testowalne bez mockowania bazy.

    Zwraca:
        {"rynki": {rynek: {n, trafienia, oczekiwane, roi, p_surowe,
                            p_po_korekcie}},
         "pominieto_kurs": int, "pominieto_legs": int, "n_wejsciowe": int}

    `p_po_korekcie` per rynek jest już skorygowane Šidákiem na LICZBĘ RYNKÓW
    w wyniku — to poprawna korekta dla każdego z osobna, jeśli patrzymy na
    wszystkie naraz i wybieramy którykolwiek jako "ciekawy" (np. najgorszy).
    """
    pominieto_kurs = 0
    pominieto_legs = 0
    grupy: dict[str, list[dict]] = {}
    for rekord in kupony:
        wzbogacony = kupon_z_legs(rekord)
        if wzbogacony is None:
            pominieto_legs += 1
            continue
        kurs = wzbogacony.get("total_odds")
        if kurs is None or kurs <= 1.0:
            # Kurs <= 1.0 jest bezsensowny (implikowane prawdopodobienstwo
            # >= 100%) i dzielenie przez (kurs - 1) albo 1/kurs pod hipoteza
            # zerowa nie ma tu sensownej interpretacji.
            pominieto_kurs += 1
            continue
        grupy.setdefault(wzbogacony["rynek"], []).append(wzbogacony)

    liczba_rynkow = len(grupy)
    rynki: dict[str, dict] = {}
    for rynek, grupa in grupy.items():
        n = len(grupa)
        trafienia = sum(1 for k in grupa if k.get("status") == "WON")
        prawdopodobienstwa = [1.0 / float(k["total_odds"]) for k in grupa]
        oczekiwane = sum(prawdopodobienstwa)
        suma_stawek = sum(float(k.get("stake_pln") or 0.0) for k in grupa)
        suma_wyplat = sum(float(k.get("payout_pln") or 0.0) for k in grupa)
        roi = (100.0 * (suma_wyplat - suma_stawek) / suma_stawek
               if suma_stawek else None)
        p_surowe = poisson_binomial_cdf(prawdopodobienstwa, trafienia)
        rynki[rynek] = {
            "n": n,
            "trafienia": trafienia,
            "oczekiwane": oczekiwane,
            "roi": roi,
            "p_surowe": p_surowe,
            "p_po_korekcie": korekta_sidaka(p_surowe, liczba_rynkow),
        }

    return {
        "rynki": rynki,
        "pominieto_kurs": pominieto_kurs,
        "pominieto_legs": pominieto_legs,
        "n_wejsciowe": len(kupony),
    }
