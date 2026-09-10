"""core/alarmy_jakosci.py — alarmy KOŃCOWE: czy produkcja liczy to, co mierzymy.

`pipeline-health` pytał dotąd, czy coś POWSTAJE: predykcje, rozliczenia, kupony
System. Wszystkie trzy świeciły zielono, kiedy:

    * Poisson liczył 28% ocen, resztę fallback Bzzoiro-ML (do 10.09);
    * `model_log.lambda_h` była pusta w 1231 z 1231 wierszy (do 10.09);
    * team-news był martwy na trzech poziomach naraz (do 07.09);
    * CLV nie powstało ani razu w historii, a Over/Under nie dostawał kursu
      zamknięcia nigdy (do 10.09).

Każda z tych awarii miała zielone testy jednostkowe. Decyzja 10.09: zamiast
dokładać kolejne, pytamy bazę produkcyjną o SKUTEK — tak jak reszta monitora.

PROGI SĄ CELOWO NISKIE i każdy ma minimalną próbę: alarm łapie ZAPAŚĆ, nie
wahanie dnia. Przerwa reprezentacyjna daje kilka ocen i żadnej z Poissona —
to nie awaria. Szum zabija alarm tak samo skutecznie jak cisza.

SQL bez `?` poza parametrami i bez `%`: `utils.db._Conn._fix` zamienia każdy
znak zapytania na `%s`, a `%` psuje formatowanie psycopg2. Stąd `COUNT(x)`
zamiast operatora jsonb `?` i `= ANY(?)` zamiast `LIKE`.
"""
from __future__ import annotations

# Poisson: w 24h co najmniej 20 ocen, z czego mniej niż 20% z Poissona = zapaść.
# Zmierzone przed naprawą nazw: 16-36% dziennie, po naprawie ~42% na parach
# z sierpnia. 20% łapie powrót do "Poisson nie działa" (pyarrow, dataset),
# a nie dzień z egzotycznymi ligami.
PROG_POKRYCIA_POISSONA = 0.20
MIN_OCEN_POKRYCIA = 20

# λ w dzienniku: przy 10+ ocenach Poissona ZERO z λ to regres zapisu, nie pech.
MIN_OCEN_POISSONA_LAMBDA = 10

# Team-news: okno 72h, bo wzbogacamy tylko kandydatów (1-6 dziennie) i bywa
# dzień bez żadnego (08.09: 0 na 42 oceny). Trzy dni zera przy 30+ ocenach = martwy.
MIN_OCEN_TEAM_NEWS = 30

# CLV: 10 dni, żeby dociąganie zaległe (`core/clv_zalegle`, okno 7 dni) zdążyło.
MIN_NOG_CLV = 20


def _liczba(wiersz, klucz: str) -> int:
    """Wartość z wiersza jako int; brak klucza albo NULL = 0.

    Wiersz bez oczekiwanych kolumn to w praktyce atrapa innego testu albo
    zmieniony schemat — liczymy go jako zero, a nie wybuchamy KeyError-em,
    bo wyjątek tutaj zamieniłby się w fałszywy alarm "baza nie odpowiada".
    """
    if not isinstance(wiersz, dict):
        return 0
    return int(wiersz.get(klucz) or 0)


def _typy_z_kursem_zamkniecia() -> list[str]:
    from footstats.scrapers.closing_odds import _TYP_NA_KURS

    return sorted(_TYP_NA_KURS)


def sprawdz_jakosc(conn) -> tuple[list[str], dict]:
    """Zwraca `(powody_alarmu, metryki)`. Pusta lista powodów = zdrowo."""
    powody: list[str] = []

    oceny = conn.execute(
        "SELECT COUNT(*) AS n,"
        " SUM(CASE WHEN model_source = 'poisson-dc' THEN 1 ELSE 0 END) AS pois,"
        " SUM(CASE WHEN model_source = 'poisson-dc' AND lambda_h IS NOT NULL"
        "     THEN 1 ELSE 0 END) AS pois_lambda"
        " FROM model_log WHERE created_at > NOW() - INTERVAL '24 hours'"
    ).fetchone()
    n24, pois, pois_lambda = (_liczba(oceny, k) for k in ("n", "pois", "pois_lambda"))
    pokrycie = pois / n24 if n24 else None

    if n24 >= MIN_OCEN_POKRYCIA and pokrycie is not None and pokrycie < PROG_POKRYCIA_POISSONA:
        powody.append(
            f"Poisson policzył {pois} z {n24} ocen w 24h ({pokrycie:.0%}, próg "
            f"{PROG_POKRYCIA_POISSONA:.0%}) — reszta idzie na fallback Bzzoiro-ML"
        )
    if pois >= MIN_OCEN_POISSONA_LAMBDA and pois_lambda == 0:
        powody.append(
            f"λ nie trafia do dziennika: 0 z {pois} ocen Poissona w 24h ma lambda_h"
        )

    tn_wiersz = conn.execute(
        "SELECT COUNT(*) AS n,"
        " COUNT(absencje_pewne_home) + COUNT(absencje_pewne_away) AS tn"
        " FROM model_log WHERE created_at > NOW() - INTERVAL '72 hours'"
    ).fetchone()
    n72, team_news = _liczba(tn_wiersz, "n"), _liczba(tn_wiersz, "tn")
    if n72 >= MIN_OCEN_TEAM_NEWS and team_news == 0:
        powody.append(
            f"team-news nie wzbogacił żadnej z {n72} ocen od 72h — sprawdź FotMob"
            " i flagę FOOTSTATS_TEAM_NEWS na jobach"
        )

    # Tylko typy, dla których CSV football-data W OGÓLE notuje cenę — BTTS czy
    # podwójna szansa nie dostaną kursu nigdy i zaniżałyby proporcję.
    clv = conn.execute(
        "SELECT COUNT(*) AS mapowalne, COUNT(e->>'clv_closing') AS z_clv"
        " FROM coupons c CROSS JOIN LATERAL jsonb_array_elements(c.legs_json::jsonb) AS e"
        " WHERE c.status IN ('WON', 'LOST')"
        "   AND c.created_at > NOW() - INTERVAL '10 days'"
        "   AND UPPER(TRIM(e->>'tip')) = ANY(?)",
        (_typy_z_kursem_zamkniecia(),),
    ).fetchone()
    mapowalne, z_clv = _liczba(clv, "mapowalne"), _liczba(clv, "z_clv")
    if mapowalne >= MIN_NOG_CLV and z_clv == 0:
        powody.append(
            f"CLV: żadna z {mapowalne} rozliczonych nóg z 10 dni nie ma kursu"
            " zamknięcia — sprawdź football-data.co.uk i krok `clv_zalegle`"
        )

    metryki = {
        "oceny_24h": n24,
        "pokrycie_poissona": round(pokrycie, 3) if pokrycie is not None else None,
        "poisson_z_lambda": pois_lambda,
        "oceny_72h": n72,
        "team_news_72h": team_news,
        "clv_mapowalne": mapowalne,
        "clv_z_kursem": z_clv,
    }
    return powody, metryki
