"""
normalize.py — Normalizacja nazw drużyn piłkarskich.

Usuwa popularne prefiksy/sufiksy klubowe (FC, KS, AS, itp.) i znaki specjalne,
a następnie stosuje opcjonalne mappingi z data/team_mappings.json.

Użycie:
    from footstats.utils.normalize import normalize_team_name
    normalize_team_name("KS Lechia Gdańsk")   # -> "lechia gdansk"
    normalize_team_name("FC Augsburg")         # -> "augsburg"
    normalize_team_name("Paris Saint-Germain") # -> "psg"
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

# Ścieżka do pliku mappingów (data/team_mappings.json względem katalogu projektu)
_MAPPINGS_PATH = Path(__file__).parents[3] / "data" / "team_mappings.json"

# Prefiksy usuwane z POCZĄTKU nazwy (case-insensitive, całe słowo)
_PREFIXES = {
    "fc", "fk", "fk", "ac", "as", "rc", "sc", "sk", "sv",
    "ks", "mks", "lks", "rks", "gks", "tps", "jk", "nk",
    "ss", "us", "ud", "cd", "cf", "sd", "rcd", "ced",
    "bsc", "vfb", "vfl", "tsg", "rb", "rsb",
    "pfc", "csk", "fcs", "ssk",
    "al",           # al-taawoun -> taawoun
    "afc", "asc",
    "atletico", "sporting", "deportivo",  # tylko gdy pierwszy token
}

# Sufiksy usuwane z KOŃCA nazwy (case-insensitive, całe słowo).
#
# Tylko SZUM — skróty formy prawnej klubu. Nic, co odróżnia dwa kluby od siebie.
_SUFFIXES = {
    "fc", "fk", "ac", "sc", "sk", "sv", "if", "bk", "gf",
    "cf", "bc", "ut",
}

# Człony, które NALEŻĄ do tożsamości klubu — nigdy ich nie obcinamy.
#
# Do 2026-07-31 siedziały w `_SUFFIXES` i były wycinane jak szum, przez co:
#   Manchester United -> "manchester" == Manchester City -> "manchester"
#   Dundee United     -> "dundee"     == Dundee FC       -> "dundee"
# `team_similarity` dawało wtedy 1.00, a próg w rozliczeniach to 0.6
# (`evening_agent.py:87`) — wynik jednego meczu mógł rozliczyć kupon na drugi.
# Przed pomyłką ratowała tylko punktacja parowa, czyli przypadek.
_ROZROZNIAJACE = {
    "city", "town", "united", "rovers", "wanderers",
    "athletic", "athletics", "hotspur", "albion", "county",
    # Dopisane 2026-08-25. "Wednesday" jest czlonem tozsamosci dokladnie tak samo
    # jak "United" — bez niego Sheffield United i Sheffield Wednesday dostawaly
    # 0.800, czyli POWYZEJ progow rozliczen (0.6 w evening_agent, 0.70 w
    # _znajdz_wynik). Ten sam blad co w lipcu, tylko innymi drzwiami.
    "wednesday",
}

# Bazy, dla których SAM SKRÓT nie mówi, o który klub chodzi.
#
# Reguła „różne człony = różne kluby" (niżej w `team_similarity`) rozstrzyga
# przypadek, w którym OBIE strony mają człon i te człony sobie przeczą
# (United vs City). Gdy jedna strona nie ma go wcale, to zwykle skrócona pisownia
# tej samej drużyny — „Colchester" to Colchester United, bo innego Colchester nie ma.
#
# Ale nie zawsze. Zmierzone 2026-09-03 na 1063 nazwach z
# `data/hist_cache/full_dataset.parquet`: SIEDEM baz nosi w danych więcej niż
# jeden klub —
#
#   bristol    Bristol City  vs Bristol Rovers
#   dundee     Dundee        vs Dundee United
#   edinburgh  FC Edinburgh  vs Edinburgh City
#   guangzhou  Guangzhou FC  vs Guangzhou City
#   man        Man City      vs Man United
#   oxford     Oxford        vs Oxford City
#   sheffield  Sheffield United vs Sheffield Weds
#
# UWAGA NA PIERWSZY POMIAR: dał pięć, bez `bristol` i `sheffield`, bo grupował
# tokeny po surowym `t in _ROZROZNIAJACE`, z pominięciem `_ROZ_SKROTY`. Dataset
# zapisuje „Sheffield Weds", więc `weds` nie liczyło się jako człon tożsamości
# i baza wychodziła „sheffield weds" zamiast „sheffield". Wniosek do kopiowania
# przy każdym podobnym wyliczeniu: grupuj przez `_czlony_rozrozniajace`, nie
# przez samą przynależność do zbioru — inaczej pomiar wygląda czysto i mierzy
# co innego. Skutkiem byłoby dopasowanie „Sheffield" do Sheffield United.
#
# Dla tych baz zostaje fail-closed. Listę odtwarza z datasetu test
# `test_lista_baz_dwuznacznych_zgadza_sie_z_danymi` — żeby przy kolejnej lidze
# dopisać wpis, a nie dowiedzieć się o braku z kuponu rozliczonego cudzym wynikiem.
#
# Czego ta lista NIE obejmuje: klubów spoza datasetu. „Newcastle" jest tu
# jednoznaczne, bo Newcastle Jets w danych nie występuje. Gdy wejdzie, test to
# pokaże — ale dopiero wtedy.
_BAZY_WIELOZNACZNE = {
    "bristol", "dundee", "edinburgh", "guangzhou", "man", "oxford", "sheffield",
}

# Skróty tych samych członów — "Dundee Utd" to nadal Dundee United.
# Bez tego reguła "różne człony = różne kluby" rozdzielałaby klub od jego
# własnego skrótu.
_ROZ_SKROTY = {
    "utd": "united", "athl": "athletic", "wdrs": "wanderers",
    # Skroty uzywane przez `_DEFAULT_MAPPINGS` i przez football-data.co.uk.
    # Bez nich alias SKRACAJACY nazwe rozbrajal regule odrozniania klubow:
    # "bristol rovers" -> "bristol rvs", a "rvs" nie bylo czlonem odrozniajacym,
    # wiec para z "Bristol City" spadala do zwyklego SequenceMatchera (0.696).
    "rvs": "rovers", "weds": "wednesday",
}

# Znaczniki drużyn rezerw i młodzieżowych.
#
# `team_similarity` dawało parze ("Legia", "Legia II") wynik 0.80 — regułą
# token-prefix, tą samą, która słusznie dopasowuje ("Legia Warszawa", "Legia").
# Progi w produkcji są niżej: 0.70 w `_znajdz_wynik`, 0.6 w `evening_agent`,
# więc rezerwy przechodziły jako pierwszy zespół. Rezerwy grają zwykle w ten
# sam weekend, więc oba mecze bywają w tej samej puli wyników.
#
# Samo podobieństwo nazw tego nie rozstrzygnie — potrzebny osobny znacznik.
#
# Czego tu NIE MA i dlaczego:
#   * "juniors" — "Boca Juniors" to pierwszy zespół, nie młodzież;
#   * "atletico" — rozdzieliłoby "Club Atletico Boca Juniors" od "Boca Juniors"
#     (Sevilla Atletico zostaje na aliasach w team_mappings.json).
ZNACZNIKI_REZERW = {
    "ii", "iii", "iv", "b", "c",
    "u18", "u19", "u20", "u21", "u23",
    "res", "reserve", "reserves", "rezerwy",
    "youth", "academy", "castilla", "amateure",
    "jong",          # holenderskie rezerwy: Jong Ajax, Jong PSV
}


# Próg dopasowania drużyn do konkretnego meczu (fixture'a) u dostawcy danych.
#
# 0.80 to wynik, jaki `team_similarity` daje legalnemu skrótowi nazwy
# ("Legia" ~ "Legia Warszawa") — niżej schodzić nie ma po co, a wyżej odcięłoby
# właśnie te warianty.
#
# NIE JEST WSPÓLNY DLA WSZYSTKICH, wbrew temu, co pisało tu do 2026-09-03.
# Ścieżka rozliczeń ma własne progi: `results_updater._znajdz_wynik` używa 0.70,
# `evening_agent` 0.6. Komentarz twierdzący coś przeciwnego był gorszy niż jego
# brak, bo zniechęcał do sprawdzenia.
#
# ZMIERZONE 03.09 na 32 zaległych kuponach — te rozjazdy nic nie zmieniają:
#
#     próg 0.60 -> 31/32      próg 0.80 -> 31/32
#     próg 0.70 -> 31/32      próg 0.85 ->  4/32
#
# Powód: po aliasach trafienia mają 1.00, a nietrafienia ≤0.30, więc przedział
# 0.60-0.80 jest pusty. Ochronę daje REGUŁA (`_tylko_rodzajowe`,
# `_BAZY_WIELOZNACZNE`), nie wysokość progu — token-prefix zwraca dokładnie 0.80,
# więc żaden próg ≤0.80 go nie odsiewa.
#
# Dlatego progi zostają jak są: ujednolicenie nie kupuje niczego mierzalnego,
# a podniesienie do 0.80 na ścieżce rozliczeń grozi utratą przypadków spoza tej
# próbki — czyli dokładnie tym, co naprawiamy.
PROG_DOPASOWANIA_MECZU = 0.80


def _czlony_rozrozniajace(tokeny: set[str]) -> set[str]:
    """Człony tożsamości klubu z tokenów, ze skrótami sprowadzonymi do formy pełnej."""
    return {
        _ROZ_SKROTY.get(t, t)
        for t in tokeny
        if _ROZ_SKROTY.get(t, t) in _ROZROZNIAJACE
    }

# Znaki zamieniane przed normalizacją: litery diakrytyczne → ASCII
_DIACRITICS_MAP = str.maketrans({
    "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n",
    "ó": "o", "ś": "s", "ź": "z", "ż": "z",
    "Ą": "a", "Ć": "c", "Ę": "e", "Ł": "l", "Ń": "n",
    "Ó": "o", "Ś": "s", "Ź": "z", "Ż": "z",
    # Litery nierozk\u0142adalne przez NFKD \u2014 niemieckie, nordyckie, tureckie, ba\u0142ka\u0144skie.
    # NFKD rozk\u0142ada tylko znaki z\u0142o\u017cone z litery i znaku \u0142\u0105cz\u0105cego (\u00fc \u2192 u + \u00a8).
    # Litery B\u0118D\u0104CE osobnymi znakami przechodz\u0105 przez ni\u0105 nietkni\u0119te i dopiero
    # filtr `[^a-z0-9 ]` zamienia je w SPACJ\u0118 \u2014 a spacja rozbija nazw\u0119 na cz\u0142ony
    # i zabija dopasowanie: "Preu\u00dfen M\u00fcnster" \u2192 "preu en munster".
    "\u00df": "ss", "\u1e9e": "ss",
    "\u00f8": "o", "\u00d8": "o", "\u00e6": "ae", "\u00c6": "ae",
    "\u0153": "oe", "\u0152": "oe",
    "\u0111": "d", "\u0110": "d", "\u00f0": "d", "\u00d0": "d",
    "\u00fe": "th", "\u00de": "th",
    "\u0131": "i", "\u0130": "i", "\u014b": "n", "\u0127": "h",
    "-": " ", "_": " ", ".": " ", "'": "", "\u2019": "",
})


def _strip_diacritics(s: str) -> str:
    """Usuwa znaki diakrytyczne przez unicode normalization + zastępowanie polskich liter."""
    # Najpierw podmień polskie i znane litery przez mapę
    s = s.translate(_DIACRITICS_MAP)
    # Następnie normalizacja unicode NFD → stripuj combining marks
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _remove_prefixes_suffixes(tokens: list[str]) -> list[str]:
    """Usuwa znane prefiksy z początku i sufiksy z końca listy tokenów."""
    # Prefiks: usuń wszystkie pasujące tokeny z przodu
    while tokens and tokens[0] in _PREFIXES:
        tokens = tokens[1:]
    # Sufiks: usuń jeden pasujący token z końca (tylko jeden, żeby nie przegiąć)
    if tokens and tokens[-1] in _SUFFIXES and len(tokens) > 1:
        tokens = tokens[:-1]
    return tokens


_DEFAULT_MAPPINGS: dict[str, str] = {
    # ── Aliasy wyprowadzone z kuponów, ktore sie NIE rozliczyly (2026-09-03) ──
    #
    # Kierunek jest istotny: mapujemy SKROT NA NAZWE IDENTYFIKUJACA, nie odwrotnie.
    # "wolves" -> "wolverhampton" usuwa kolizje z "Chattanooga Red Wolves" (0.80,
    # oba kluby graly 29.08 i wpadaja do jednej puli `_fetch_fixtures_by_date`).
    # Mapowanie w druga strone by ja STWORZYLO.
    "wolves":              "wolverhampton",
    "wolverhampton wanderers": "wolverhampton",
    # TPS i Inter Turku sa z tego samego miasta, graja w Veikkausliidze i oba
    # mialy mecz 31.08. Bez tego aliasu "Turku PS" vs "Inter Turku" = 0.80, czyli
    # POWYZEJ progu 0.70 — kupon na TPS mogl dostac wynik Interu.
    "turku ps":            "turun palloseura",
    "tps turku":           "turun palloseura",
    "kups":                "kuopion palloseura",
    # Rezerwy Celty wystepuja pod wlasna nazwa. Alias sprowadza obie pisownie do
    # formy ZE ZNACZNIKIEM rezerw, wiec `ZNACZNIKI_REZERW` dalej odroznia je od
    # pierwszego zespolu.
    "celta fortuna":       "celta de vigo ii",
    # CELOWO NIE MA TU aliasu "shanghai sipg" -> "shanghai port", choc to ta sama
    # druzyna po zmianie nazwy (2021). Dodalem go i cofnalem: dataset historyczny
    # zawiera OBIE pisownie jako osobne druzyny, wiec alias zlewa ich wiersze —
    # a `normalize_team_name` karmi takze historie modelu (lambda per druzyna),
    # nie tylko rozliczenia. Zlapal to `test_zadne_dwie_rozne_druzyny_z_datasetu_
    # sie_nie_zlewaja`. Para i tak dostaje 0.77, czyli powyzej progu 0.70, wiec
    # alias nie naprawial NICZEGO zmierzonego — a kosztowalby zmiane danych modelu.

    "barca":               "barcelona",
    "paris saint germain": "psg",
    "paris sg":            "psg",
    "psg":                 "psg",
    "manchester united":   "man utd",
    "man united":          "man utd",
    "manchester city":     "man city",
    "atletico madrid":     "atletico",
    "inter milan":         "inter",
    "internazionale":      "inter",
    "bayer leverkusen":    "leverkusen",
    "rb leipzig":          "leipzig",
    "rasenball leipzig":   "leipzig",
    "wisla plock":         "wisla plock",
    "ks lechia gdansk":    "lechia gdansk",
    # Warianty nazw reprezentacji (World Cup 2026) - FIFA vs popularne nazwy z roznych API
    "south korea":         "korea",
    "korea republic":      "korea",
    "korea dpr":           "north korea",
    "north korea":         "north korea",
    "czechia":             "czechia",
    "czech republic":      "czechia",
    "usa":                 "usa",
    "united states":       "usa",
    "united states of america": "usa",
    "ivory coast":         "ivory coast",
    "cote divoire":        "ivory coast",
    "iran":                "iran",
    "ir iran":             "iran",
    "islamic republic of iran": "iran",
    "cape verde":          "cabo verde",
    "cabo verde":          "cabo verde",
    "macedonia":           "north macedonia",
    "north macedonia":     "north macedonia",
    "dr congo":            "dr congo",
    "congo dr":            "dr congo",
    "democratic republic of congo": "dr congo",
}


def _seed_mappings_file() -> None:
    """Tworzy team_mappings.json z domyślnymi aliasami, jeśli plik nie istnieje."""
    if _MAPPINGS_PATH.exists():
        return
    _MAPPINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _MAPPINGS_PATH.write_text(
        json.dumps(_DEFAULT_MAPPINGS, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@lru_cache(maxsize=1)
def _load_mappings() -> dict[str, str]:
    """Aliasy drużyn: `_DEFAULT_MAPPINGS` jako baza, plik JSON jako nadpisanie.

    Wcześniej czytany był WYŁĄCZNIE plik. Ponieważ `_seed_mappings_file()` tworzy
    go tylko gdy nie istnieje, każdy nowy alias dopisany do `_DEFAULT_MAPPINGS`
    był MARTWY na każdej maszynie, która plik już miała — poprawka w kodzie
    nie zmieniała niczego po wdrożeniu.

    Efekt uboczny: `data/team_mappings.json` nie jest w repo ani w obrazie
    Dockera, więc każde środowisko dopasowywało nazwy inaczej. CI (świeży seed,
    pełne defaults) rozróżniało Manchester United od City, a lokalna maszyna
    ze starym plikiem 28-wpisowym — nie. Ten sam kod, dwa zachowania.

    Scalanie czyni to deterministycznym: defaults zawsze obowiązują, a plik
    służy do ręcznych nadpisań i dopisków użytkownika.
    """
    scalone = {
        _strip_diacritics(k).lower(): v.lower()
        for k, v in _DEFAULT_MAPPINGS.items()
    }
    _seed_mappings_file()
    try:
        data = json.loads(_MAPPINGS_PATH.read_text(encoding="utf-8"))
        scalone.update({
            _strip_diacritics(k).lower(): v.lower() for k, v in data.items()
        })
    except (json.JSONDecodeError, OSError, AttributeError):
        pass
    return scalone


def normalize_team_name(name: str, use_mappings: bool = True) -> str:
    """
    Normalizuje nazwę drużyny do postaci porównywalnej.

    Kroki:
      1. Zamień diakrytyki i znaki specjalne
      2. Lowercase
      3. Usuń znane prefiksy (FC, KS, al-, TSG, itp.) i sufiksy (United, City, itp.)
      4. Usuń zduplikowane spacje
      5. Zastosuj mappingi z data/team_mappings.json (jeśli istnieją)

    Args:
        name:         Oryginalna nazwa drużyny
        use_mappings: Jeśli True, stosuje mappingi z team_mappings.json

    Returns:
        Znormalizowana nazwa w lowercase, bez prefiksów i znaków specjalnych.

    Examples:
        >>> normalize_team_name("KS Lechia Gdańsk")
        'lechia gdansk'
        >>> normalize_team_name("FC Augsburg")
        'augsburg'
        >>> normalize_team_name("TSG Hoffenheim")
        'hoffenheim'
        >>> normalize_team_name("Al-Taawoun")
        'taawoun'
        >>> normalize_team_name("Paris Saint-Germain")
        'psg'
    """
    if not name:
        return ""

    # Krok 1-2: Diakrytyki + lowercase
    cleaned = _strip_diacritics(name).lower()

    # Krok 3: Usuń wszystko co nie jest literą/cyfrą/spacją
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", cleaned)

    # Krok 4: Tokenizuj + usuń prefiksy/sufiksy
    tokens = [t for t in cleaned.split() if t]
    tokens = _remove_prefixes_suffixes(tokens)

    result = " ".join(tokens)

    # Krok 5: Mappingi (np. "wisla plock" -> "wisla plock" lub aliasy API)
    if use_mappings:
        mappings = _load_mappings()
        if result in mappings:
            result = mappings[result]

    return result


def _norm_ascii(s: str) -> str:
    """Normalizuje tekst: Unicode → ASCII, lowercase, tylko alfanumeryczne.

    Przechodzi przez tę samą mapę co `normalize_team_name` — inaczej `ascii/ignore`
    kasuje ß i ø BEZ ŚLADU ("Preußen" → "preuen"), a ta funkcja paruje właśnie
    nazwy drużyn z The Odds API z nazwami z datasetu.
    """
    s = _strip_diacritics(str(s))
    s = s.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def team_similarity(a: str, b: str) -> float:
    """
    Podobieństwo nazw drużyn 0–1.
    Obsługuje skróty (PSG = Paris Saint-Germain) i warianty (Lyon ~ Lyonnais).
    """
    from difflib import SequenceMatcher

    na, nb = normalize_team_name(a), normalize_team_name(b)

    if na == nb:
        return 1.0

    # Pusta nazwa po normalizacji nie moze pasowac do niczego.
    # "FC" / "AC" to same prefiksy — po ich zdjeciu zostaje "", a regula
    # token-prefix nizej zwracala wtedy 0.80 wobec DOWOLNEJ nazwy (patrz komentarz
    # przy `_znaczace`). Przy progu rozliczen 0.6 obcieta nazwa w kuponie
    # dopasowalaby sie do pierwszego lepszego meczu z listy.
    if not na or not nb:
        return 0.0

    # Ta sama baza + RÓŻNE człony odróżniające = różne kluby.
    #
    # Bez tej reguły "manchester united" i "manchester city" dostają 0.81 od
    # SequenceMatcher (wspólny przedrostek "manchester " przeważa), czyli powyżej
    # progu rozliczeń 0.6. Samo zdjęcie sufiksów z `_SUFFIXES` tego NIE załatwia.
    #
    # Fail-closed: przy wątpliwości wolimy nie rozliczyć i to zauważyć, niż
    # rozliczyć kupon wynikiem cudzego meczu. Legalne aliasy ("Bolton" jako
    # Bolton Wanderers) dopisuje się jawnie do `team_mappings.json`.
    tokeny_a, tokeny_b = set(na.split()), set(nb.split())

    # Rezerwy/młodzież to osobny zespół. Rozstrzygamy PRZED regułami skrótów,
    # bo to właśnie one dawały "Legia II" 0.80 wobec "Legia" — patrz komentarz
    # przy `ZNACZNIKI_REZERW`. Różne znaczniki (II vs III) też znaczą różne
    # zespoły; identyczne przechodzą dalej do normalnego porównania.
    if (tokeny_a & ZNACZNIKI_REZERW) != (tokeny_b & ZNACZNIKI_REZERW):
        return 0.0

    roz_a, roz_b = _czlony_rozrozniajace(tokeny_a), _czlony_rozrozniajace(tokeny_b)
    baza_a = {t for t in tokeny_a if _ROZ_SKROTY.get(t, t) not in _ROZROZNIAJACE}
    baza_b = {t for t in tokeny_b if _ROZ_SKROTY.get(t, t) not in _ROZROZNIAJACE}
    if roz_a != roz_b and baza_a == baza_b:
        # BRAK członu to SKRÓT, nie sprzeczność. Do 2026-09-03 pusty zbiór był
        # tu traktowany jak konkurencyjna wartość, więc "Colchester United" wobec
        # "Colchester" dostawało 0.0 zamiast ~1.0. Zmierzony skutek: `_znajdz_wynik`
        # (próg 0.70 na obu stronach) nie dopasował ANI JEDNEGO z 32 zaległych
        # kuponów, mimo że wyniki były w API-Football — dopasowanie przewracała
        # druga strona pary, np. sim(gospodarz)=1.00 przy sim(gość)=0.00.
        #
        # Sprzeczność wymaga DWÓCH członów, które sobie przeczą (United vs City).
        # Wyjątek: bazy z `_BAZY_WIELOZNACZNE`, gdzie skrót naprawdę nie wskazuje
        # klubu — tam zostaje fail-closed, bo lepiej nie rozliczyć i zauważyć,
        # niż rozliczyć kupon wynikiem cudzego meczu.
        if roz_a and roz_b:
            return 0.0
        if baza_a & _BAZY_WIELOZNACZNE:
            return 0.0

    def _initials(s: str) -> str:
        """Inicjały — TYLKO dla nazw wielowyrazowych.

        Dla jednowyrazowej nazwy inicjały to jedna litera, co dopasowywało
        "B" do "Barcelona" z wynikiem 0.85 (i "L" do "Legia", itd.). Skrót ma
        sens dopiero przy 2+ słowach: "PSG" ↔ "Paris Saint Germain".
        """
        slowa = s.split()
        return "".join(w[0] for w in slowa) if len(slowa) >= 2 else ""

    ini_a, ini_b = _initials(na), _initials(nb)
    if (ini_b and na == ini_b) or (ini_a and nb == ini_a):
        return 0.85

    tokens_a = na.split()
    tokens_b = nb.split()

    # Reguła token-prefix: każdy ZNACZĄCY token (>=3 znaki) jednej nazwy ma
    # przedrostek w drugiej ("Man United" ~ "Manchester United").
    #
    # `_znaczace` musi być NIEPUSTE. Wcześniej filtr `if len(ta) >= 3` siedział
    # w generatorze, więc dla nazwy bez tokenów >=3 znaków `all()` leciało po
    # pustym generatorze i zwracało True — a funkcja 0.80 wobec DOWOLNEJ nazwy.
    # Skutek: "A", "X", a nawet "FC" (normalizuje się do "") pasowały do
    # wszystkiego powyżej progu rozliczeń 0.6 i progu 0.70 w `_znajdz_wynik`.
    znaczace_a = [t for t in tokens_a if len(t) >= 3]
    znaczace_b = [t for t in tokens_b if len(t) >= 3]

    # Wspólny token RODZAJOWY to nie dopasowanie, dodane 2026-09-03.
    #
    # Reguła niżej uznaje dopasowanie, gdy znaczące tokeny krótszej nazwy mają
    # przedrostek w dowolnym tokenie dłuższej. To jest potrzebne i działa:
    # "Legia" ~ "Legia Warszawa", "Lyon" ~ "Olympique Lyonnais" (człon
    # identyfikujący bywa DRUGIM słowem, więc wymaganie zaczepienia od początku
    # byłoby za ostre — sprawdzone, psuje Lyon).
    #
    # Ale gdy jedynym łącznikiem jest wyraz RODZAJOWY, to nie jest ta sama drużyna:
    #
    #   City    vs  Manchester City    = 0.80
    #   United  vs  Newcastle United   = 0.80
    #
    # Oba powyżej progu rozliczeń 0.70, a `_znajdz_wynik` bierze PIERWSZY fixture
    # powyżej progu, nie najlepszy. `_ROZROZNIAJACE` mamy już zdefiniowane jako
    # dokładnie te wyrazy, które nie identyfikują klubu w pojedynkę.
    #
    # Czego to NIE łapie: wspólnego tokenu identyfikującego dwóch różnych klubów
    # ("Turku PS" vs "Inter Turku" = 0.80, oba z Turku, ta sama liga, ten sam
    # dzień). Tam potrzebny jest jawny alias — patrz `_DEFAULT_MAPPINGS` i
    # `tests/test_aliasy_nazw_z_zaleglosci.py`. Reguła ogólna tego nie rozstrzygnie,
    # bo "turku" niesie tożsamość tak samo jak "bristol".
    def _tylko_rodzajowe(znaczace: list[str]) -> bool:
        """Czy nazwa nie wnosi NIC poza wyrazem rodzajowym (City, United, ...)."""
        return bool(znaczace) and all(
            _ROZ_SKROTY.get(t, t) in _ROZROZNIAJACE for t in znaczace
        )

    if not _tylko_rodzajowe(znaczace_a) and znaczace_a and all(
        any(tb.startswith(ta) for tb in tokens_b) for ta in znaczace_a
    ):
        return 0.80
    if not _tylko_rodzajowe(znaczace_b) and znaczace_b and all(
        any(ta.startswith(tb) for ta in tokens_a) for tb in znaczace_b
    ):
        return 0.80

    return SequenceMatcher(None, na, nb).ratio()


def reload_mappings() -> None:
    """Wyczyść cache mappingów (przydatne po edycji team_mappings.json)."""
    _load_mappings.cache_clear()
