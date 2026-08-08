"""Buduje aliasy nazw drużyn: nazwa ze źródła predykcji → nazwa z datasetu.

PO CO: źródło i football-data.co.uk piszą nazwy inaczej ("Club Brugge KV" vs
"Club Brugge", "Wolverhampton" vs "Wolves", "Wisła Kraków" vs "Wisla").
Zmierzone 08.08 na 14 realnych kandydatach: tylko 4 dały się połączyć z naszym
datasetem, mimo że pokrywa on ich ligi. Bez połączenia nie ma ani λ Poissona,
ani formy liczonej z historii — a wtedy trzeba jej szukać u scraperów, które
są zablokowane (SofaScore 403 z Cloud Run) albo popsute (FlashScore).

REGUŁA — celowo zachowawcza, bo aliasy działają globalnie przez
`normalize_team_name`, także przy rozliczaniu kuponów. Zły wpis rozliczyłby
kupon cudzym meczem, więc brak aliasu jest tańszy niż alias błędny:

  1. dokładne dopasowanie po normalizacji wygrywa i kończy sprawę — nie
     generujemy dla niego aliasu, bo i tak działa;
  2. rozmyte tylko gdy zwycięzca jest JEDEN i przewyższa drugiego o `MARGINES`;
  3. dwie różne nazwy nie mogą wskazać tej samej drużyny.

Punkt 1 jest tym, co rozdziela Wisłę Płock od Krakowa: Płock ma w datasecie
swoje dokładne "Wisla Plock", więc nie trafia do rozmytego, gdzie oba miały
identyczne 0.800 do "Wisla".

Użycie:
    python -m scripts.generuj_aliasy_druzyn           # podglad propozycji
    python -m scripts.generuj_aliasy_druzyn --zapisz  # dopisz do team_mappings.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Nazwy drużyn niosą znaki spoza cp1250 (Bodø, Örgryte, América) — bez tego
# samo ich wypisanie wywala skrypt na polskiej konsoli Windows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from footstats.utils.normalize import normalize_team_name, team_similarity  # noqa: E402

# Minimalne podobieństwo, przy którym w ogóle rozważamy dopasowanie.
PROG = 0.80
# O ile zwycięzca musi przewyższać drugiego, żeby wybór nie był zgadywaniem.
MARGINES = 0.10

# Człony prawne/organizacyjne w nazwach klubów. Różnica WYŁĄCZNIE o takie tokeny
# znaczy ten sam klub zapisany inaczej ("Club Brugge KV" = "Club Brugge").
#
# Bez tego warunku sam próg 0.80 z marginesem proponował m.in.:
#     wynnum wolves -> wolves      (klub z Queensland na Wolverhampton)
#     gremio novorizontino -> gremio
#     botafogo sp -> botafogo rj   (dwa rozne kluby)
#     algeria -> almeria, peru -> perugia  (reprezentacje na kluby)
# Krótka nazwa w datasecie przyciąga dowolną dłuższą o wspólnym rdzeniu.
CZLONY_PRAWNE = frozenset({
    "fc", "cf", "sc", "ac", "as", "afc", "kv", "vv", "sv", "bv", "bk", "ik",
    "if", "is", "ff", "fk", "nk", "hk", "jk", "sk", "ks", "mks", "gks",
    "cs", "us", "aif", "iff", "bik", "gif", "ogc", "rcd", "ssc", "ssv",
    "ca", "cd", "ud", "sd", "rc", "cr", "ec", "sad", "sa", "srl", "club",
    "clube", "fotball", "fotboll", "calcio", "futbol", "sport", "sportif",
    "sporting", "athletic", "atletico", "association", "team",
})

PLIK_MAPOWAN = Path(__file__).resolve().parents[1] / "data" / "team_mappings.json"

# Pary PRZEJRZANE RĘCZNIE z listy, której automat nie rozstrzygnął (08.08.2026).
# Każda to ta sama drużyna, tylko dataset skraca nazwę albo gubi diakrytyki —
# różnica jest większa niż człon prawny, więc reguła słusznie ich nie wpuściła.
#
# Z tej samej listy ODRZUCONE świadomie, jako różne kluby:
#   Algeria~Almeria, Peru~Perugia, England~New England Revolution (reprezentacje)
#   Botafogo-SP~Botafogo RJ, Grêmio Novorizontino~Gremio
#   Wynnum Wolves~Wolves, Moreton City Excelsior~Excelsior (Australia)
#   Union Sportive Yacoub El Mansour~Le Mans (Maroko), San Diego Wave~San Diego FC
#   Cambridge/Gold Coast/JEF United Chiba/Magic United/Oxford United ~ DC United
#     — "DC United" przyciągało KAŻDY klub z członem "United"; to sam artefakt
#       krótkiej nazwy w datasecie, nie podobieństwo klubów.
#
# NIEMIECKIE (dopisane 09.08.2026): wzięte z The Odds API, a nie z dziennika —
# kalendarz Bundesligi jest znany PRZED pierwszą kolejką, więc nie było powodu
# czekać z nimi do meczu. Wszystkie to skrót nazwy po stronie datasetu
# ("Borussia Dortmund" → "Dortmund"), nie inny klub.
# ODRZUCONE z tej samej listy: FC Viktoria Köln 1904 (≠ 1. FC Köln),
# TSG Hoffenheim II (rezerwy), oraz kluby spoza datasetu: FC Energie Cottbus,
# 1. FC Saarbrücken, Hallescher FC, Rot-Weiss Essen, SC Verl, Alemannia Aachen,
# Waldhof Mannheim, SG Sonnenhof Großaspach.
ALIASY_RECZNE: dict[str, str] = {
    "accrington stanley":      "accrington",
    "america mineiro":         "america mg",
    "arminia bielefeld":       "bielefeld",
    "athletico":               "athletico pr",
    "borussia dortmund":       "dortmund",
    "borussia monchengladbach": "mgladbach",
    "bristol rovers":          "bristol rvs",
    "crewe alexandra":         "crewe",
    "de graafschap":           "graafschap",
    "dynamo dresden":          "dresden",
    "eintracht braunschweig":  "braunschweig",
    "eintracht frankfurt":     "ein frankfurt",
    "estoril praia":           "estoril",
    "estudiantes de la plata": "estudiantes l p",
    "1 fc kaiserslautern":     "kaiserslautern",
    "1 fc koln":               "koln",
    "1 fc nurnberg":           "nurnberg",
    "bayern munchen":          "bayern munich",
    "fagiano okayama":         "okayama",
    "fsv mainz 05":            "mainz",
    "hamburger":               "hamburg",
    "hannover 96":             "hannover",
    "hertha berlin":           "hertha",
    "karlsruher":              "karlsruhe",
    "kyoto sanga":             "kyoto",
    "machida zelvia":          "machida",
    "msv duisburg":            "duisburg",
    "nottingham forest":       "nottm forest",
    "preston north end":       "preston",
    "sheffield wednesday":     "sheffield weds",
    "tsv 1860 munchen":        "munich 1860",
    "wehen wiesbaden":         "wehen",
}


def dopasuj_nazwe(nazwa: str, dataset: list[str]) -> tuple[str | None, str]:
    """Zwraca (nazwa z datasetu albo None, powód).

    Powody: "dokladne", "rozmyte", "remis", "brak".
    """
    n = normalize_team_name(nazwa)
    if not n or not dataset:
        return None, "brak"

    znormalizowane = [(d, normalize_team_name(d)) for d in dataset]

    for oryginal, norma in znormalizowane:
        if norma == n:
            return oryginal, "dokladne"

    oceny = sorted(
        ((team_similarity(n, norma), oryginal) for oryginal, norma in znormalizowane),
        reverse=True,
    )
    if not oceny or oceny[0][0] < PROG:
        return None, "brak"
    drugi = oceny[1][0] if len(oceny) > 1 else 0.0
    if oceny[0][0] - drugi < MARGINES:
        return None, "remis"

    zwyciezca = oceny[0][1]
    if not _rozni_sie_tylko_czlonem_prawnym(n, normalize_team_name(zwyciezca)):
        return None, "rdzen"
    return zwyciezca, "rozmyte"


def _rozni_sie_tylko_czlonem_prawnym(a: str, b: str) -> bool:
    """Czy dwie znormalizowane nazwy to ten sam klub zapisany inaczej.

    Warunek: tokeny różniące je muszą być WYŁĄCZNIE członami prawnymi.
    Wspólna część nie może być pusta — inaczej "fc" pasowałoby do wszystkiego.
    """
    ta, tb = set(a.split()), set(b.split())
    if not (ta & tb):
        return False
    return (ta ^ tb) <= CZLONY_PRAWNE


def propozycje_do_przegladu(
    nazwy_zrodla: list[str], dataset: list[str]
) -> list[tuple[str, str]]:
    """Pary odrzucone przez warunek rdzenia — do OCENY CZŁOWIEKA, nie do zapisu.

    Siedzą tu przypadki, w których nazwy różnią się czymś więcej niż członem
    prawnym: raz to ten sam klub ("Wisła Kraków" vs "Wisla", bo dataset skraca
    nazwę), a raz dwa różne ("Gremio Novorizontino" vs "Gremio"). Automat tego
    nie rozstrzygnie, a zły alias psuje rozliczenia — więc pokazujemy zamiast
    zgadywać, żeby nie ginęły po cichu.
    """
    pary = []
    for nazwa in dict.fromkeys(nazwy_zrodla):
        _, powod = dopasuj_nazwe(nazwa, dataset)
        if powod == "rdzen":
            n = normalize_team_name(nazwa)
            oceny = sorted(
                ((team_similarity(n, normalize_team_name(d)), d) for d in dataset),
                reverse=True,
            )
            if oceny:
                pary.append((nazwa, oceny[0][1]))
    return pary


def zbuduj_aliasy(
    nazwy_zrodla: list[str], dataset: list[str]
) -> tuple[dict[str, str], dict[str, int]]:
    """Mapa {znormalizowana nazwa źródła: znormalizowana nazwa datasetu} + licznik powodów.

    Do mapy trafiają WYŁĄCZNIE dopasowania rozmyte — dokładne działają bez aliasu,
    a zbędny wpis to tylko koszt utrzymania i ryzyko przy przyszłych zmianach.
    """
    mapa: dict[str, str] = {}
    raport = {"dokladne": 0, "rozmyte": 0, "remis": 0, "rdzen": 0, "brak": 0}

    for nazwa in dict.fromkeys(nazwy_zrodla):
        trafienie, powod = dopasuj_nazwe(nazwa, dataset)
        raport[powod] += 1
        if powod == "rozmyte" and trafienie is not None:
            mapa[normalize_team_name(nazwa)] = normalize_team_name(trafienie)

    # Dwie różne nazwy wskazujące ten sam klub sklejałyby jego mecze z cudzymi.
    # Nie zgadujemy, która jest prawdziwa — odrzucamy obie.
    licznik: dict[str, int] = {}
    for cel in mapa.values():
        licznik[cel] = licznik.get(cel, 0) + 1
    sporne = {cel for cel, ile in licznik.items() if ile > 1}
    if sporne:
        for klucz in [k for k, v in mapa.items() if v in sporne]:
            del mapa[klucz]
            raport["rozmyte"] -= 1
            raport["remis"] += 1

    return mapa, raport


# ─────────────────────────── wykonanie ────────────────────────────────────

def _nazwy_ze_zrodla() -> list[str]:
    """Drużyny, które REALNIE przeszły przez pipeline — z dziennika i predykcji."""
    from footstats.utils.db import connect

    # Zapytania wypisane wprost, bez skladania nazwy tabeli — sa tylko dwa,
    # a interpolacja identyfikatora to ta sama klasa co B608 przy imporcie.
    zapytania = (
        "SELECT team_home, team_away FROM model_log",
        "SELECT team_home, team_away FROM predictions",
    )
    nazwy: list[str] = []
    with connect() as conn:
        for zapytanie in zapytania:
            for r in conn.execute(zapytanie).fetchall():
                nazwy += [r["team_home"], r["team_away"]]
    return [n for n in nazwy if n]


def _nazwy_z_datasetu() -> list[str]:
    from footstats.data.historical_loader import load_cached

    df = load_cached()
    return sorted(set(df["home"].dropna()) | set(df["away"].dropna()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zapisz", action="store_true",
                        help="dopisz aliasy do data/team_mappings.json")
    args = parser.parse_args()

    zrodlo = _nazwy_ze_zrodla()
    dataset = _nazwy_z_datasetu()
    mapa, raport = zbuduj_aliasy(zrodlo, dataset)

    print(f"nazwy ze zrodla: {len(set(zrodlo))} | druzyny w datasecie: {len(dataset)}")
    print(f"  dokladne (alias zbedny): {raport['dokladne']}")
    print(f"  rozmyte  (nowy alias):   {raport['rozmyte']}")
    print(f"  remis    (odrzucone):    {raport['remis']}")
    print(f"  rdzen    (inny klub):    {raport['rdzen']}")
    print(f"  brak     (poza danymi):  {raport['brak']}")
    print()
    for k, v in sorted(mapa.items()):
        print(f"  {k:34} -> {v}")

    do_przegladu = propozycje_do_przegladu(zrodlo, dataset)
    if do_przegladu:
        print(f"\nDO PRZEGLADU ({len(do_przegladu)}) — automat NIE rozstrzyga,"
              f" te same roznice raz znacza skrot nazwy, a raz inny klub:")
        for zrod, cel in sorted(do_przegladu):
            print(f"  {zrod:34} ~ {cel}")

    if not args.zapisz:
        print("\nPODGLAD — nic nie zapisano. Powtorz z --zapisz.")
        return

    istniejace = json.loads(PLIK_MAPOWAN.read_text(encoding="utf-8"))
    razem = {**mapa, **ALIASY_RECZNE}
    nowe = {k: v for k, v in razem.items() if k not in istniejace}
    istniejace.update(nowe)
    PLIK_MAPOWAN.write_text(
        json.dumps(istniejace, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nZAPISANO {len(nowe)} nowych aliasow do {PLIK_MAPOWAN.name}"
          f" ({len(mapa)} automatycznych + {len(ALIASY_RECZNE)} przejrzanych recznie,"
          f" pominieto {len(razem) - len(nowe)} juz obecnych)")


if __name__ == "__main__":
    main()
