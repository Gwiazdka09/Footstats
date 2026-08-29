"""smoke_team_news.py — RECZNY smoke na zywym FotMobie.

Pytest nigdy nie dotyka sieci (.claude/rules/tests-no-prod.md), wiec to jedyne
miejsce, w ktorym sprawdzamy, czy zrodlo nadal odpowiada tym, czego oczekuje
parser. Odpalac przed flipem FOOTSTATS_TEAM_NEWS=1 i po kazdym podejrzeniu,
ze FotMob zmienil ksztalt.

    python scripts/smoke_team_news.py [YYYY-MM-DD]

Kod wyjscia 1 = zrodlo nie oddalo nic albo pokrycie jest zerowe.
"""
from __future__ import annotations

import io
import sys
from datetime import date

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from footstats.scrapers.teamnews.fotmob import FotMobTeamNews  # noqa: E402


def main() -> int:
    dzien = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    print(f"FotMob team-news, dzien {dzien} (1 request na liste + 1 na mecz)...")

    dane = FotMobTeamNews().fetch(dzien)
    if not dane:
        print("BRAK DANYCH — zrodlo padlo albo zmienilo ksztalt. Patrz log ERROR.")
        return 1

    n = len(dane)
    z_xi = sum(1 for t in dane if t.xi_home and t.xi_away)
    z_abs = sum(1 for t in dane if t.absencje_home or t.absencje_away)
    z_sed = sum(1 for t in dane if t.sedzia)
    prognoz = sum(1 for t in dane if t.sklad_jest_prognoza)
    pewnych = sum(1 for t in dane
                  for a in t.absencje_home + t.absencje_away if a.pewna)

    print(f"meczow: {n}")
    print(f"  pelny XI:          {z_xi}/{n}")
    print(f"  absencje:          {z_abs}/{n}")
    print(f"  sedzia:            {z_sed}/{n}")
    print(f"  typ 'predicted':   {prognoz}/{n}  (reszta to lastStarting11)")
    print(f"  absencji PEWNYCH:  {pewnych}  (tylko te wchodza do korekty lambdy)")

    print("\nprobka:")
    for t in dane[:5]:
        pewne = [a.nazwisko for a in t.absencje_home + t.absencje_away if a.pewna]
        print(f"  {t.home} - {t.away} [{t.typ_skladu}] sedzia={t.sedzia} "
              f"pewnych absencji={len(pewne)}")

    if z_xi == 0 and z_abs == 0:
        print("\nUWAGA: zero skladow i zero absencji przy niepustej liscie meczow "
              "— to wyglada na zmiane schematu, nie na brak danych.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
