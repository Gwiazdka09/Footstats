# FotMob jako źródło team-news (składy, kontuzje, sędzia)

**Data:** 2026-08-30
**Status:** projekt zatwierdzony, przed implementacją
**Kontekst:** ścieżka B z `docs/PREDICTION_ROADMAP.md` (edge informacyjny)

---

## Problem

Cała warstwa enrichmentu — składy i sędzia — wisi na jednym wywołaniu API-Football
w `core/daily_phases.py::_enrichuj_finalna_faza`. Konto jest zawieszone od 01.08
(nie limit — `suspended`), więc `lineup_ok`, `lineup_star_penalty`,
`lineup_strength_*` i `referee_signal` są puste, a DECISION SCORE ma sufit 70/100.

**Problem jest głębszy niż zawieszone konto.** Job `footstats-final` chodzi o 11:00
UTC, a oficjalny `startXI` API-Football publikuje ~20-40 min przed gwizdkiem. Mecze
grane wieczorem → o 11:00 `get_lineup` zwracał `None` dla większości kandydatów
**także wtedy, gdy konto działało**. Zawieszenie dobiło coś, co strukturalnie nie
mogło działać w tym harmonogramie.

Konsekwencja: `core/availability_edge.py` — cała ścieżka B, „potwierdzona absencja
gwiazdy rusza fair-value zanim miękkie booki zareagują" — nigdy nie dostała danych
wejściowych.

## Decyzje przyjęte przed projektem

| decyzja | wybór | uzasadnienie |
|---|---|---|
| typ danych | team news rano (kontuzje + przewidywany XI) | mieści się w harmonogramie 11:00; oficjalny startXI wymagałby nowego joba T-45min |
| budżet | **tylko darmowe** | projekt nie zarabia (zero monetyzacji), więc nie kosztuje |
| podejście | adapter we wzorcu `scrapers/sources/` | jeden adapter zdejmuje zależność od AF w czterech miejscach naraz |

## Pomiar źródeł (2026-08-29/30)

Sonda `requests` ze zwykłym User-Agentem, bez logowania:

| źródło | HTTP | Cloudflare | werdykt |
|---|---|---|---|
| **FotMob `/api/data/*`** | **200** | **nie** | wybrane |
| Transfermarkt `/verletztespieler/` | 200 | nie | 145 KB, ale **0 linków do profili graczy** — serwowany inny layout, parsowanie niepewne |
| TheSportsDB (klucz `3`) | 200 | tak | `lookuplineup.php` → 15 B, pusto |
| Sofascore `api.sofascore.com` | 403 | — | anti-bot, znane z D1b |
| worldfootball.net `/injuries/` | 403 | tak | — |
| physioroom | 404 | tak | — |

**Uwaga:** `https://www.fotmob.com/api/matches?...` zwraca 404 (stara ścieżka).
Działa `https://www.fotmob.com/api/data/matches?date=YYYYMMDD`.

### Pokrycie FotMoba, n=14 meczów z 30.08 w naszych ligach

| oś | pokrycie |
|---|---|
| przewidywany XI (22 graczy) | 14/14 |
| lista niedostępnych (kontuzje) | 14/14 |
| sędzia + statystyki | 14/14 |

147 lig w jednym dniu (482 mecze). Z 30 zgadywanych nazw naszych lig trafiło 18 —
reszta to najpewniej brak meczów tego dnia albo inna nazwa. **Mapowanie po ID ligi,
nie po nazwie** — ten sam błąd co `LIGI_DATASETU` vs whitelist, gdzie belgijski mecz
wypadł na samej nazwie mimo pełnej historii.

### Co oddaje jeden request na mecz

```
lineup.lineupType            "predicted" | "lastStarting11"
lineup.{home,away}Team
  .formation                 "3-4-2-1"
  .starters[11]              {name, positionId, marketValue,
                              performance.{seasonGoals, seasonAssists, seasonRating}}
  .unavailable[]             {name, unavailability:{type:"injury",
                              expectedReturn:"Doubtful" | "Mid September 2026"}}
  .coach
matchFacts.infoBox.Referee   {text, stats:[matches, yellowCards perMatch + średnia ligi,
                              redCards total, fouls perMatch, penalties]}
```

Trzy rzeczy poza samymi składami:

- `expectedReturn` **rozróżnia** „Doubtful" od twardego „Mid September 2026" →
  `availability_edge` może ważyć absencję zamiast traktować binarnie
- `performance.seasonGoals` daje `goal_share` wprost → `core/player_db.py` przestaje
  zależeć od topscorers API-Football
- statystyki sędziego są bogatsze niż obecny `scrapers/referee_db.py`

## Architektura

Kopia wzorca `scrapers/sources/`, który już działa dla wyników. Protocol + jeden
adapter. **Agregatora nie ma** — jedno źródło, budowanie agregatora dla jednego
źródła to YAGNI. Protocol istnieje po to, żeby drugie źródło było dopisaniem klasy,
nie przepisaniem fazy.

```
scrapers/teamnews/
  base.py      Absencja + TeamNews (DTO, frozen) + TeamNewsSource (Protocol)
  fotmob.py    FotMobTeamNews
```

### DTO

```python
@dataclass(frozen=True)
class Absencja:
    nazwisko: str
    typ: str                    # "injury" / "suspension"
    powrot: str | None          # "Doubtful" | "Mid September 2026"
    pewna: bool                 # patrz regula nizej
    gole_sezon: int | None      # performance.seasonGoals

@dataclass(frozen=True)
class TeamNews:
    source: str
    home: str
    away: str
    date: str                   # YYYY-MM-DD
    typ_skladu: str | None      # "predicted" | "lastStarting11" | None
    xi_home: list[str]
    xi_away: list[str]
    absencje_home: list[Absencja]
    absencje_away: list[Absencja]
    sedzia: str | None
    sedzia_stats: dict[str, float | None]   # klucze ustalone nizej
```

**Reguła `pewna`** (bez niej dwie różne rzeczy wpadłyby do jednego `False`):

| `powrot` | `pewna` | znaczenie |
|---|---|---|
| `"Doubtful"` | `False` | zawodnik **może** zagrać — absencja niepewna |
| data, np. `"Mid September 2026"` | `True` | nie zagra na pewno |
| `None` (źródło nie podało) | `False` | **nie wiadomo** — nie zgadujemy |

Wiersz trzeci jest tu po to, żeby brak danych nie udawał niepewnej absencji przy
liczeniu edge'u. `availability_edge` waży tylko `pewna=True`; reszta idzie do logu,
nie do lambdy.

**Klucze `sedzia_stats`** — zamknięty zbiór, dokładnie kolumny tabeli `referees`:
`avg_yellow`, `avg_red`, `avg_goals`, `home_win_pct`, `n_matches`. Klucza nieobecnego
u FotMoba **nie ma w słowniku wcale** — nie ma go z wartością `0`.

`typ_skladu` jest w DTO **celowo**. `lastStarting11` to ostatni skład, nie prognoza.
Zlanie tych dwóch w jedno pole to ten sam kształt błędu, co naprawiony 29.08
w `scrapers/api_football.py`: mieszanie wartości zmierzonej z domyślną w jednym polu,
gdzie odbiorca nie widzi różnicy.

### Przepływ

`_enrichuj_finalna_faza` przestaje być funkcją API-Football, staje się funkcją
enrichmentu:

```
kandydaci --+-> FotMobTeamNews.fetch(data)   1 req/dzień + 1 req/mecz
            |      indeks (norm_home, norm_away) -> TeamNews
            |      dopasowanie: team_similarity + PROG_DOPASOWANIA_MECZU (istnieje)
            |
            +-> xi_*        -> core/lineup_strength   -> lineup_star_penalty, lineup_strength_*
            +-> absencje_*  -> core/availability_edge -> skorygowana lambda, edge vs kurs
            +-> sedzia      -> scrapers/referee_db    -> referee_signal
            +-> gole_sezon  -> core/player_db         -> goal_share bez topscorers AF
```

Stary tor API-Football **zostaje** pod `api_key`, jako drugi w kolejce. Jeśli konto
wróci — cross-walidacja za darmo. Jeśli nie wróci — nic nie pada.

To nie jest agregator w sensie `sources/aggregator.py`: nie ma głosowania ani
uzgadniania rozjazdów, jest zwykłe pierwszeństwo — pole wypełnione przez FotMoba
nie jest nadpisywane przez API-Football. Kolejność żyje w fazie enrichmentu, nie
w osobnym module.

### Pułapka: kolumny `referees`

Tabela ma `avg_yellow`, `avg_red`, `avg_goals`, `home_win_pct`. FotMob daje żółte jako
**średnią na mecz**, czerwone jako **sumę sezonu**, a `avg_goals` i `home_win_pct`
nie daje wcale.

Twarda zasada:

- `avg_yellow` — brane wprost (`valueType: "perMatch"`)
- `avg_red` — liczone jawnie: `redCards_total / matches_total`
- `avg_goals`, `home_win_pct` — **`None`**, nigdy `0`

Wpisanie sumy do kolumny „średnia" albo dosypanie zera w brakujące pole to ten sam
błąd co `50/50/50` w `api_football`: odbiorca dostaje liczbę i nie wie, że to nie
pomiar.

## Obsługa błędów

Kontrakt `TeamNewsSource` jest graceful jak `ResultsSource` — ale graceful nie znaczy
cichy.

| stan | poziom | uzasadnienie |
|---|---|---|
| mecz nie znaleziony u FotMoba | DEBUG | 147 lig, nasz mecz bywa poza pokryciem — stan normalny |
| pusta lista absencji przy pełnym XI | DEBUG | drużyna bez kontuzji to stan normalny |
| HTTP 403 / 429 / zmiana kształtu JSON-a | **ERROR** | nie degradacja, tylko śmierć całej ścieżki B |

Trzeci wiersz jest sednem projektu. W ciągu miesiąca: konto AF zawieszone po cichu,
Groq wycofał model po cichu, joby stały 3 dni na martwym obrazie przy `exit=0`.
FotMob jako nieoficjalne API padnie kiedyś tak samo — jedyne, co możemy zrobić, to
żeby padł **głośno**.

Licznik na przebieg:

```
team_news: 34/41 kandydatów wzbogaconych (5 predicted / 29 lastStarting11)
```

Zerowe pokrycie przy zdrowym HTTP to **osobny alarm** — tak wykryjemy zmianę schematu,
która nie rzuca wyjątkiem.

## Flaga

`FOOTSTATS_TEAM_NEWS=1`, domyślnie **OFF** na pierwszy deploy, flip po smoke na żywym
potoku.

Musi trafić w **trzy miejsca**: API + `footstats-final` + `footstats-evening`.
`ENSEMBLE_MARKET_WEIGHT` rozjechało się dokładnie tak (API `0.70`, joby brak), więc
częścią zadania jest test spójności flag, a nie poleganie na pamięci.

## Testy

`.claude/rules/tests-no-prod.md`: zewnętrzne źródła mockować. Pytest **nigdy** nie
dotyka FotMoba. Fikstury to przycięty, **prawdziwy** JSON zapisany z sond 29-30.08,
nie ręcznie zmyślony kształt.

- parser: pełny mecz → pełny `TeamNews`; brak `lineup` → DTO z `None`, nie wyjątek
- `lastStarting11` nie może wyjść z DTO jako `predicted`
- `avg_red` liczone jako iloraz; `avg_goals` i `home_win_pct` zostają `None` —
  test, że zero nigdy nie wchodzi do bazy
- dopasowanie drużyn: nazwa FotMoba różna od naszej → `team_similarity` łączy
- kontrola ciszy: nowy moduł startuje z **zerem** cichych handlerów, bez baseline'u
- kontrola hałasu: zdrowy przebieg nie loguje nic na WARNING
- spójność flagi w trzech miejscach
- `scripts/smoke_team_news.py` — poza pytestem, ręcznie, na żywym źródle

## Krok 0 — pomiar przed budową

Jeden `SELECT` na prod: w ilu z 427 rozliczonych predykcji `lineup_ok` było niepuste.

- wynik bliski 0 → potwierdza diagnozę; FotMob to nie ulepszenie, tylko **pierwsze**
  realne włączenie ścieżki B
- wynik wysoki → diagnoza błędna, projekt do przemyślenia

Read-only, bez importu `footstats.api.main` (odpala `run_migrations()` przy imporcie).

## Czego ten projekt NIE obiecuje

Nie ma dowodu, że to poprawi trafność. Danych historycznych o kontuzjach nie ma ani
u nas, ani u FotMoba, więc walk-forward tego nie zmierzy — `availability_edge.py` sam
to zapisuje: „forward-only: brak historycznych składów/kontuzji → nie backtestujemy
ROI, walidujemy logikę".

Wartość jest mierzalna dopiero forward, po kilkudziesięciu meczach z zapisanym `edge`
i rozliczonym wynikiem. Zapisane tutaj, żeby za miesiąc nikt — łącznie z autorem —
nie policzył tego jako wygranej bez liczb.

Kontekst, dlaczego ta ostrożność: 14.08 na `n=15 460` żaden z 52 podzbiorów nie
przeżył holdoutu; 27.08 na `n=424` model okazał się już skalibrowany, więc wąskim
gardłem jest **rozdzielczość**, nie kalibracja. Team news to zakład na to, że
rozdzielczość przyjdzie z danych, których rynek jeszcze nie wycenił — nie zmierzona
poprawa.

## Ryzyka

| ryzyko | skutek | mitygacja |
|---|---|---|
| FotMob to nieoficjalne API | zniknie bez ostrzeżenia | ERROR + licznik pokrycia; Protocol gotowy na drugi adapter |
| brak ToS na dostęp maszynowy | dostęp może zostać odcięty | wolumen mały (1 req/dzień + 1 na mecz), throttle 0,7 s |
| `predicted` XI bywa błędne | zła korekta lambdy | `typ_skladu` w DTO; `lastStarting11` traktowany słabiej |
| nazwy drużyn i lig się rozjeżdżają | cicha utrata meczów | `team_similarity`; mapowanie lig po ID, nie po nazwie |
