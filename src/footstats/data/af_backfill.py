"""af_backfill.py — dociąganie statystyk meczowych z API-Football do historii.

CEL: 19 z 40 lig datasetu (48.7% zbioru, ~68 000 meczów) ma ZERO strzałów celnych.
Kolumny `hst`/`ast` tam istnieją, ale są NaN, więc `form.sily_ligowe` przechodzi
guard obecności kolumn, po `dropna` dostaje pustkę i `WAGA_STRZALOW=0.7` jest
cicho ignorowana — λ leci z samych goli. Tam, gdzie strzały są, zmierzony efekt
to Brier 0.6290 → 0.6180.

ZGODNOŚĆ POLA sprawdzona ZANIM wydaliśmy budżet: na Eredivisie (liga mająca
strzały u obu źródeł) `Shots on Goal` z API-Football zgadza się z `HST`
z football-data w 60 z 60 meczów, co do sztuki.

FAIL-CLOSED jest zasadą nadrzędną. Mecz bez wpisu wraca do goli po cichu i to
jest stan normalny (`form.py` obsługuje drużynę bez strzałów). Mecz z CUDZYMI
statystykami psuje λ tak, że nic nie pada i nikt tego nie zauważy. Dlatego
dopasowanie przechodzi cztery niezależne warstwy: mapa składu ligi, data ±1 dnia,
zgodność WYNIKU, jednoznaczne przypisanie stron w odpowiedzi.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from footstats.data import af_stats
from footstats.utils.normalize import normalize_team_name, team_similarity

log = logging.getLogger(__name__)

# Nazwy typów w /fixtures/statistics — sondowane 2026-09-03 na koncie Pro.
TYP_ST_CELNE = "Shots on Goal"
TYP_ST_WSZYSTKIE = "Total Shots"
TYP_XG = "expected_goals"

# Granice sensowności. Rekord ligowy strzałów celnych w meczu to ~20; 40 to
# zapas, przy którym pewne jest, że pole znaczy co innego, niż zakładamy.
MAX_STRZALOW_CELNYCH = 40.0
MAX_STRZALOW = 60.0

# Dopasowanie nazw. Progi zachowawcze — patrz `dopasuj_sklad`.
PROG = 0.80
MARGINES = 0.10

# Okno dat. API-Football podaje kick-off w UTC, football-data datę lokalną:
# mecz o 21:00 w Meksyku to 03:00 UTC następnego dnia.
OKNO_DNI = (-1, 0, 1)

# Ile zapytań zostaje NIETKNIĘTYCH dla potoku produkcyjnego.
#
# Backfill i potok dzielą jeden limit 7500/dobę — rozliczenia, składy i sędzia
# jadą z tej samej puli. Wyczerpanie jej pracą offline skończyłoby się HTTP 429
# na porannym jobie, czyli awarią produkcji wywołaną badaniem.
REZERWA_POTOKU = 1500

# Co ile meczów zrzucamy plik: tyle najwyżej requestów traci ubity proces.
ZAPIS_CO = 100

PLIK_LIG = Path(__file__).resolve().parents[3] / "data" / "af_league_ids.json"

# Sezony sondowane dla każdej ligi. NIE rozstrzygamy semantyki — "2024" to
# 2024/25 w Europie, ale kalendarzowy 2024 w Brazylii, Japonii czy MLS. Bierzemy
# kilku kandydatów i ufamy DATOM z odpowiedzi, bo one są jednoznaczne, a mecz
# spoza okna i tak odpadnie na weryfikacji wynikiem.
SEZONY_KANDYDACI = (2024, 2025, 2026)


def wczytaj_mape_lig(sciezka: Path | None = None) -> dict[str, dict]:
    """Mapa `liga_datasetu -> {af_league_id, nazwa_af, kraj}`, przejrzana ręcznie.

    Brak ligi w mapie znaczy: NIE backfillujemy jej. Id nie zgadujemy z nazwy —
    zmierzone 2026-09-03: dataset mówi `ROU-Superliga`, a API `Liga I`; dataset
    mówi `USA-MLS`, a API `Major League Soccer`; Holandia oddaje obok siebie
    `Eredivisie`, `Eerste Divisie` i `Eredivisie Women`. Automat przegapiłby
    dwie pierwsze i źle rozstrzygnął trzecią, a błąd byłby cichy: statystyki
    z innych rozgrywek w meczach, których nie dotyczą.

    Klucze zaczynające się od podkreślenia to komentarze i listy wykluczeń.
    """
    sciezka = Path(sciezka or PLIK_LIG)
    if not sciezka.exists():
        log.warning("Brak mapy lig %s — backfill nie ma czego pobierac", sciezka)
        return {}
    try:
        dane = json.loads(sciezka.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.error("Mapa lig %s nieczytelna (%s: %s) — backfill wstrzymany",
                  sciezka, type(e).__name__, e)
        return {}
    return {k: v for k, v in dane.items() if not k.startswith("_")}


def pobierz_statystyki(api_key: str, fixture_id: int) -> tuple[dict, int | None]:
    """Produkcyjny pobieracz dla `backfill`: (statystyki, pozostało z nagłówka).

    Świadomie NIE idzie przez `APIFootball._get`. Tamten cache trzyma wszystko
    w jednym pliku JSON i przepisuje go w całości przy KAŻDYM zapisie
    (`utils/cache.py::_af_save_disk_cache`) — kilka tysięcy odpowiedzi zrobiłoby
    z niego setki megabajtów spowalniających każde zapytanie potoku produkcyjnego.
    Cache indeksu fixture'ów (kilkadziesiąt zapytań) przez `_get` jest w porządku.
    """
    from footstats.scrapers.results_updater import _fetch_statystyki_surowe

    return _fetch_statystyki_surowe(api_key, fixture_id)


@dataclass(frozen=True)
class Para:
    """Mecz z datasetu skojarzony z fixture'em w API-Football."""

    date: pd.Timestamp
    league: str
    home: str
    away: str
    af_fixture_id: int
    af_home: str
    af_away: str


# ─────────────────────────── parser statystyk ──────────────────────────────


def _liczba(wartosc: object) -> float | None:
    """Surowa wartość z API → float, albo None gdy to nie jest liczba.

    API oddaje `None` (brak), liczby i teksty ("1.87", "58%"). Brak jest stanem
    normalnym; wartość nieliczbowa to już nie brak danych, więc idzie do logu —
    bez tego zmiana formatu u dostawcy byłaby całkowicie niewidoczna.

    `bool` odsiewamy jawnie: jest podklasą `int`, więc `True` stałoby się 1.0.
    """
    if wartosc is None or isinstance(wartosc, bool):
        return None
    if isinstance(wartosc, (int, float)):
        return float(wartosc)
    try:
        return float(str(wartosc).strip().rstrip("%"))
    except (TypeError, ValueError):
        log.debug("Wartosc %r z API-Football nie jest liczba — traktuje jak brak", wartosc)
        return None


def statystyki_druzyny(surowe: dict) -> dict[str, float | None]:
    """{typ: wartość} jednej drużyny → trzy pola, które nas obchodzą.

    Pozostałe z osiemnastu typów (rożne, kartki, posiadanie, podania, faule,
    spalone, obrony bramkarza, goals_prevented) nie mają w `src/` ani jednego
    czytelnika. Kolumna bez czytelnika prędzej czy później zostanie użyta
    bez pomiaru — dlatego nie wchodzą.
    """
    return {
        "st_celne": _liczba(surowe.get(TYP_ST_CELNE)),
        "st_wszystkie": _liczba(surowe.get(TYP_ST_WSZYSTKIE)),
        "xg": _liczba(surowe.get(TYP_XG)),
    }


def wiersz_sensowny(wiersz: dict) -> bool:
    """Czy liczby w wierszu mogą pochodzić z meczu piłkarskiego.

    Bez `hst`/`ast` wiersz nie niesie nic, co czyta model. `hst > hs` znaczy,
    że pola znaczą co innego, niż zakładamy — a wtedy lepiej nie mieć danych
    niż mieć przekręcone.
    """
    hst, ast = wiersz.get("hst"), wiersz.get("ast")
    if hst is None or ast is None:
        return False
    for celne, wszystkie in ((hst, wiersz.get("hs")), (ast, wiersz.get("as_"))):
        if not 0.0 <= celne <= MAX_STRZALOW_CELNYCH:
            return False
        if wszystkie is not None:
            if not 0.0 <= wszystkie <= MAX_STRZALOW or celne > wszystkie:
                return False
    return True


# ─────────────────────────── mapa składu ligi ──────────────────────────────


def dopasuj_sklad(
    nazwy_zrodla: list[str],
    nazwy_datasetu: list[str],
) -> tuple[dict[str, str], dict[str, int]]:
    """Mapa {nazwa z API: nazwa z datasetu} + licznik powodów odrzuceń.

    DLACZEGO PER LIGA, a nie globalnie: pula kandydatów ma ~20 nazw zamiast
    kilku tysięcy, więc kluby dzielące rdzeń ("Wisła Płock" i "Wisła Kraków")
    mają w niej OBA swoje dokładne odpowiedniki i żaden nie wchodzi na etap
    rozmyty. Globalnie `team_similarity` dałoby obu tyle samo i wybór byłby
    zgadywaniem — dokładnie ta klasa błędu wstrzymała rozliczenia 03.09.

    Trzy warstwy: dopasowanie dokładne ZDEJMUJE kandydata z puli rozmytej;
    rozmyte wymaga jednego zwycięzcy z przewagą `MARGINES`; iniektywność odrzuca
    obie nazwy, gdy dwie wskazują tę samą drużynę (sklejenie cudzych meczów).
    """
    raport = {"dokladne": 0, "rozmyte": 0, "remis": 0, "brak": 0, "sporne": 0}
    if not nazwy_zrodla or not nazwy_datasetu:
        raport["brak"] = len([n for n in nazwy_zrodla if n])
        return {}, raport

    norm_datasetu = {d: normalize_team_name(d) for d in nazwy_datasetu}
    mapa: dict[str, str] = {}
    zajete: set[str] = set()
    do_rozmytego: list[str] = []

    for nazwa in dict.fromkeys(n for n in nazwy_zrodla if n):
        n = normalize_team_name(nazwa)
        if not n:
            raport["brak"] += 1
            continue
        trafienie = next((d for d, nd in norm_datasetu.items() if nd == n), None)
        if trafienie is not None:
            mapa[nazwa] = trafienie
            zajete.add(trafienie)
            raport["dokladne"] += 1
        else:
            do_rozmytego.append(nazwa)

    wolne = {d: nd for d, nd in norm_datasetu.items() if d not in zajete}
    for nazwa in do_rozmytego:
        n = normalize_team_name(nazwa)
        oceny = sorted(
            ((team_similarity(n, nd), d) for d, nd in wolne.items()), reverse=True
        )
        if not oceny or oceny[0][0] < PROG:
            raport["brak"] += 1
            continue
        drugi = oceny[1][0] if len(oceny) > 1 else 0.0
        if oceny[0][0] - drugi < MARGINES:
            raport["remis"] += 1
            continue
        mapa[nazwa] = oceny[0][1]
        raport["rozmyte"] += 1

    licznik: dict[str, int] = {}
    for cel in mapa.values():
        licznik[cel] = licznik.get(cel, 0) + 1
    sporne = {cel for cel, ile in licznik.items() if ile > 1}
    for klucz in [k for k, v in mapa.items() if v in sporne]:
        del mapa[klucz]
        raport["sporne"] += 1

    return mapa, raport


# ─────────────────────────── dopasowanie meczów ────────────────────────────


def dopasuj_mecze(
    df_liga: pd.DataFrame,
    fixtures: list[dict],
    juz_pobrane: set[tuple] | None = None,
) -> tuple[list[Para], dict[str, int]]:
    """Mecze z datasetu skojarzone z fixture'ami. Fail-closed przy wątpliwości.

    Weryfikacja WYNIKIEM jest tu najtańszym i najmocniejszym zabezpieczeniem:
    to klucz niezależny od nazw i dat, dostępny za darmo w odpowiedzi
    `/fixtures`. Zła para o tym samym wyniku tego samego dnia jest praktycznie
    niemożliwa. Sprawdzamy ją ZANIM wydamy request na `/fixtures/statistics`.
    """
    juz_pobrane = juz_pobrane or set()
    raport = {"dopasowane": 0, "brak_w_af": 0, "wiele_kandydatow": 0,
              "wynik_niezgodny": 0, "nazwa_nierozpoznana": 0, "juz_mamy": 0}
    if df_liga is None or df_liga.empty or not fixtures:
        raport["brak_w_af"] = 0 if df_liga is None or df_liga.empty else len(df_liga)
        return [], raport

    nazwy_af = sorted({
        str((t or {}).get("name") or "")
        for f in fixtures
        for t in ((f.get("teams") or {}).get("home"), (f.get("teams") or {}).get("away"))
        if (t or {}).get("name")
    })
    nazwy_ds = sorted(set(df_liga["home"].astype(str)) | set(df_liga["away"].astype(str)))
    mapa, raport_mapy = dopasuj_sklad(nazwy_af, nazwy_ds)
    log.info("mapa skladu: %d/%d nazw AF dopasowanych %s",
             len(mapa), len(nazwy_af), raport_mapy)

    indeks: dict[tuple, list[dict]] = {}
    for f in fixtures:
        t = f.get("teams") or {}
        h = mapa.get(str((t.get("home") or {}).get("name") or ""))
        a = mapa.get(str((t.get("away") or {}).get("name") or ""))
        if not h or not a:
            continue
        surowa = str((f.get("fixture") or {}).get("date") or "")[:10]
        dzien = pd.to_datetime(surowa, errors="coerce")
        if pd.isna(dzien):
            continue
        indeks.setdefault((h, a, dzien.normalize()), []).append(f)

    znane = set(mapa.values())
    pary: list[Para] = []
    for r in df_liga.itertuples(index=False):
        data = pd.to_datetime(getattr(r, "date"), errors="coerce")
        if pd.isna(data):
            raport["brak_w_af"] += 1
            continue
        data = data.normalize()
        if (data, str(r.home), str(r.away)) in juz_pobrane:
            raport["juz_mamy"] += 1
            continue

        kandydaci: list[dict] = []
        for offset in OKNO_DNI:
            kandydaci += indeks.get(
                (str(r.home), str(r.away), data + pd.Timedelta(days=offset)), []
            )
        if not kandydaci:
            if str(r.home) not in znane or str(r.away) not in znane:
                raport["nazwa_nierozpoznana"] += 1
            else:
                raport["brak_w_af"] += 1
            continue
        if len(kandydaci) > 1:
            raport["wiele_kandydatow"] += 1
            continue

        m = kandydaci[0]
        gole = m.get("goals") or {}
        try:
            zgadza = (float(gole["home"]) == float(r.hg)
                      and float(gole["away"]) == float(r.ag))
        except (KeyError, TypeError, ValueError):
            zgadza = False
        if not zgadza:
            raport["wynik_niezgodny"] += 1
            continue

        teams = m.get("teams") or {}
        pary.append(Para(
            date=data,
            league=str(getattr(r, "league", "")),
            home=str(r.home),
            away=str(r.away),
            af_fixture_id=int((m.get("fixture") or {})["id"]),
            af_home=str((teams.get("home") or {}).get("name") or ""),
            af_away=str((teams.get("away") or {}).get("name") or ""),
        ))
        raport["dopasowane"] += 1

    return pary, raport


# ─────────────────────────── pobranie fixture'ów ───────────────────────────


def fixtures_ligi_sezonu(klient, af_league_id: int, sezon: int) -> list[dict]:
    """Wszystkie fixture'y ligi w sezonie — JEDNO zapytanie.

    BEZ parametru `page`. `/fixtures` go nie przyjmuje i odmowę oddaje jako
    **HTTP 200** z `results: 0` oraz `errors: {"page": "The Page field do not
    exist."}` — stronicowanie po nim dałoby zero fixture'ów dla każdej ligi
    i cicho nie zrobiło nic. Zmierzone 2026-09-03: `?league=88&season=2025`
    zwraca komplet 309 meczów przy `paging {current: 1, total: 1}`.

    Każdy `errors` w treści traktujemy jak awarię, nie jak "brak meczów w tym
    sezonie" — te dwa stany wyglądają w odpowiedzi identycznie.
    """
    from footstats.core.apisports_gate import blad_konta, zglos_odpowiedz

    dane = klient._get("/fixtures", params={"league": af_league_id, "season": sezon})
    if not dane:
        return []
    if zglos_odpowiedz(dane):
        log.error("API-Football zamknelo bramke przy lidze %s sezon %s",
                  af_league_id, sezon)
        return []
    blad = blad_konta(dane)
    if blad:
        log.error("API-Football odrzucil zapytanie o fixtures (liga %s, sezon %s): %s",
                  af_league_id, sezon, blad)
        return []
    return list(dane.get("response") or [])


# ─────────────────────────── pętla backfillu ───────────────────────────────


def _klucze_pobrane(df: pd.DataFrame) -> set[tuple]:
    """Klucze meczów już w pliku — RÓWNIEŻ tych bez statystyk.

    Ślad "tego meczu AF nie ma" musi się zapisywać: ENG-National League
    i FIN-Veikkausliiga nie mają w API żadnych statystyk, a bez śladu każdy
    kolejny przebieg płaciłby za nie od nowa.
    """
    if df is None or df.empty:
        return set()
    daty = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    return set(zip(daty, df["home"].astype(str), df["away"].astype(str)))


def _wiersz_z_odpowiedzi(para: Para, surowe: dict) -> dict:
    """Odpowiedź /fixtures/statistics → wiersz pliku. Fail-closed przy wątpliwości."""
    pusty = {
        "date": para.date, "league": para.league,
        "home": para.home, "away": para.away,
        "hs": None, "as_": None, "hst": None, "ast": None,
        "xg_home": None, "xg_away": None,
        "af_fixture_id": para.af_fixture_id,
        "status": "brak_statystyk",
        "pobrano": datetime.now().isoformat(timespec="seconds"),
    }
    dom = surowe.get(para.af_home)
    goscie = surowe.get(para.af_away)
    if not isinstance(dom, dict) or not isinstance(goscie, dict):
        # Nie zgadujemy, która strona jest gospodarzem — pomyłka odwróciłaby
        # atak z obroną w ratingach ligowych i nic by nie padło.
        return pusty

    d, g = statystyki_druzyny(dom), statystyki_druzyny(goscie)
    wiersz = dict(pusty)
    wiersz.update({
        "hs": d["st_wszystkie"], "as_": g["st_wszystkie"],
        "hst": d["st_celne"], "ast": g["st_celne"],
        "xg_home": d["xg"], "xg_away": g["xg"],
    })
    if not wiersz_sensowny(wiersz):
        return pusty
    wiersz["status"] = "ok"
    return wiersz


def backfill(
    pary: list[Para],
    pobierz: Callable[[str, int], tuple[dict, int | None]],
    api_key: str,
    sciezka: Path | None = None,
    zapis_co: int = ZAPIS_CO,
    budzet: int = 3000,
) -> dict:
    """Dociąga statystyki dla par, zapisując przyrostowo. Wznawialny.

    `pobierz(api_key, fixture_id)` zwraca `(statystyki, pozostalo)`, gdzie
    `pozostalo` to `x-ratelimit-requests-remaining` Z TEJ odpowiedzi. Licznik
    zbiorczy `/status` ma opóźnienie (po ~61 zapytaniach pokazywał +5, chwilę
    później +43), więc bramkowanie na nim przestrzeliłoby limit. `None` znaczy
    "nie wiem" i NIE zatrzymuje — nieznane pozostało to nie to samo co zero.

    `powod_stopu` ∈ {koniec, budzet_przebiegu, rezerwa_potoku, bramka}.
    """
    from footstats.core.apisports_gate import wlaczone

    sciezka = Path(sciezka or af_stats.SCIEZKA_AF_STATS)
    zebrane = af_stats.wczytaj_af_stats(sciezka)
    istniejace = _klucze_pobrane(zebrane)
    nowe: list[dict] = []
    podsumowanie = {"pobrane": 0, "ok": 0, "bez_statystyk": 0,
                    "pominiete": 0, "powod_stopu": "koniec"}

    def _zrzuc() -> None:
        if not nowe:
            return
        laczne = pd.concat([zebrane, pd.DataFrame(nowe)], ignore_index=True)
        af_stats.zapisz_af_stats(laczne, sciezka)

    try:
        for para in pary:
            klucz = (pd.Timestamp(para.date).normalize(), para.home, para.away)
            if klucz in istniejace:
                podsumowanie["pominiete"] += 1
                continue
            if podsumowanie["pobrane"] >= budzet:
                podsumowanie["powod_stopu"] = "budzet_przebiegu"
                break
            if not wlaczone():
                podsumowanie["powod_stopu"] = "bramka"
                break

            surowe, pozostalo = pobierz(api_key, para.af_fixture_id)
            wiersz = _wiersz_z_odpowiedzi(para, surowe or {})
            nowe.append(wiersz)
            istniejace.add(klucz)
            podsumowanie["pobrane"] += 1
            podsumowanie["ok" if wiersz["status"] == "ok" else "bez_statystyk"] += 1

            if len(nowe) % zapis_co == 0:
                _zrzuc()

            # Sprawdzenie PO odpowiedzi — nagłówek jest jedynym wiarygodnym
            # źródłem i istnieje dopiero wtedy.
            if pozostalo is not None and pozostalo <= REZERWA_POTOKU:
                log.warning("Zostalo %s zapytan — zatrzymuje backfill, reszta"
                            " nalezy do potoku produkcyjnego", pozostalo)
                podsumowanie["powod_stopu"] = "rezerwa_potoku"
                break
    finally:
        _zrzuc()

    return podsumowanie
