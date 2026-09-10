"""core/clv_zalegle.py — kurs zamknięcia dla nóg rozliczonych w POPRZEDNICH dniach.

`evening_agent` liczy CLV w chwili rozliczenia, czyli w dniu meczu o 21:00 UTC.
Darmowe CSV football-data.co.uk dopisuje mecze z opóźnieniem kilku dni, więc
w tej chwili meczu tam jeszcze nie ma. Typ "1" ratował fallback API-Football,
ale Over/Under nie ma drugiego źródła — stąd rozkład z 10.09:

    typ         nóg rozliczonych od 06.09   z kursem zamknięcia
    OVER 2.5            45                          0
    UNDER 2.5           23                          0
    1                   10                          5

Ten moduł wraca do nóg z ostatnich `OKNO_DNI` dni, które kursu nie dostały,
i pyta CSV jeszcze raz. Zmierzone 10.09 na 219 kuponach od 01.09: 55 z 214 nóg
bez CLV ma już kurs w CSV, wobec 5 w dniu meczu.

Noga nie zna własnej daty, więc próbujemy `match_date_first` kuponu i
`PRZESUNIECIE_DNI` kolejnych dni. `kursy_zamkniecia` wymaga zgodności obu
drużyn, kierunku i DOKŁADNEJ daty — ta sama para nie gra dwa razy w trzy dni,
więc szersze okno nie może podpiąć cudzego meczu, najwyżej żadnego.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import date, timedelta

log = logging.getLogger(__name__)

# Dłużej nie ma sensu: mecz, którego CSV nie dopisało w tydzień, jest spoza
# zasięgu źródła (MLS, J1, K League), a nie spóźniony.
OKNO_DNI = 7

# Kupon wielonogowy ma w bazie tylko datę PIERWSZEGO meczu, a kick-off po
# północy UTC trafia do CSV pod datą następnego dnia.
PRZESUNIECIE_DNI = 2


def _wczytaj_z_bazy(od: date) -> list[dict]:
    from footstats.core.coupon_tracker import _exec

    def _fn(conn):
        return conn.execute(
            "SELECT id, match_date_first, legs_json FROM coupons"
            " WHERE status IN ('WON', 'LOST') AND match_date_first >= ?",
            (od.isoformat(),),
        ).fetchall()

    return [
        {"id": r["id"], "match_date_first": str(r["match_date_first"] or "")[:10],
         "nogi": json.loads(r["legs_json"] or "[]")}
        for r in _exec(_fn) or []
    ]


def _zapisz_do_bazy(kupon_id: int, nogi: list[dict]) -> None:
    from footstats.core.coupon_tracker import _exec

    def _fn(conn):
        conn.execute("UPDATE coupons SET legs_json=? WHERE id=?",
                     (json.dumps(nogi, ensure_ascii=False), kupon_id))

    _exec(_fn)


def _kurs_z_okna(kursy_fn: Callable, noga: dict, typ: str | None, start: date) -> float | None:
    """Kurs zamknięcia typu nogi z pierwszej daty okna, pod którą CSV zna mecz."""
    from footstats.scrapers.closing_odds import kurs_dla_typu

    home = noga.get("home") or noga.get("gospodarz") or ""
    away = noga.get("away") or noga.get("goscie") or ""
    for przesuniecie in range(PRZESUNIECIE_DNI + 1):
        dzien = (start + timedelta(days=przesuniecie)).isoformat()
        kurs = kurs_dla_typu(kursy_fn(home, away, dzien), typ)
        if kurs:
            return kurs
    return None


def uzupelnij_clv_zaleglych(
    dzis: date,
    okno_dni: int = OKNO_DNI,
    *,
    _wczytaj: Callable[[date], list[dict]] | None = None,
    _zapisz: Callable[[int, list[dict]], None] | None = None,
    _kursy: Callable | None = None,
) -> tuple[int, int]:
    """Dopisuje `clv_closing` nogom, które go nie dostały. Zwraca (uzupełnione, sprawdzone).

    „Sprawdzone” liczy wyłącznie nogi, dla których CSV W OGÓLE notuje cenę
    (1X2, Over/Under 2.5) — BTTS czy podwójna szansa nie idą do sieci wcale.
    Kupon zapisujemy w całości i tylko wtedy, gdy któraś noga dostała kurs.
    """
    from footstats.scrapers import closing_odds as co

    wczytaj = _wczytaj or _wczytaj_z_bazy
    zapisz = _zapisz or _zapisz_do_bazy
    kursy_fn = _kursy or co.kursy_zamkniecia

    uzupelnione = sprawdzone = bledy = 0
    for kupon in wczytaj(dzis - timedelta(days=okno_dni)):
        try:
            start = date.fromisoformat(str(kupon.get("match_date_first") or "")[:10])
        except ValueError:
            continue

        nogi = [dict(n) for n in kupon.get("nogi") or []]
        zmiana = False
        for noga in nogi:
            typ = noga.get("tip") or noga.get("typ") or noga.get("ai_tip")
            if noga.get("clv_closing") or noga.get("result") is None:
                continue
            if not co.typ_ma_kurs_zamkniecia(typ):
                continue
            sprawdzone += 1
            try:
                kurs = _kurs_z_okna(kursy_fn, noga, typ, start)
            except (OSError, ValueError, KeyError, TypeError) as e:
                # Telemetria nie może zatrzymać reszty — ale liczymy, żeby
                # padnięte źródło nie wyglądało jak „CSV jeszcze nie ma meczu”.
                bledy += 1
                log.debug("CLV zalegle %s: %s", kupon.get("id"), e)
                continue
            if kurs:
                noga["clv_closing"] = kurs
                uzupelnione += 1
                zmiana = True

        if zmiana:
            zapisz(kupon["id"], nogi)

    if bledy:
        log.warning("CLV zalegle: zrodlo kursow zamkniecia padlo dla %d z %d nog",
                    bledy, sprawdzone)
    return uzupelnione, sprawdzone
