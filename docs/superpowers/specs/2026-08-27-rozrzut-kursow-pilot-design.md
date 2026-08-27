# Rozrzut kursów między bukmacherami — pilot tygodniowy

**Data:** 2026-08-27
**Status:** projekt zatwierdzony, do implementacji
**Powiązane:** `.claude/rules/wypuszczenie-pl.md`, pamięć `project_model_nie_bije_rynku`, `project_model_jest_skalibrowany`

## Pytanie

Czy **którykolwiek konkretny bukmacher** jest systematycznie do pobicia?

To jest inne pytanie niż to, na które już mamy odpowiedź. Cztery niezależne pomiary
(walk-forward n=15 460, kupony vs kurs n=133, ROI per model n=118, BTTS n=134) mówią,
że nasz model nie bije **rynku**. Nigdy nie mierzyliśmy, czy da się bić pojedynczą
książkę — a to poprzeczka niższa i zupełnie niezależna od jakości modelu.

## Własność, która czyni ten pomiar tanim

**Nie potrzebuje wyników meczów.**

Dla każdego wyniku liczymy cenę uczciwą z książki referencyjnej (zdewigowany Pinnacle),
a potem dla każdego bukmachera `b`:

```
edge_b = kurs_b × p_uczciwe − 1
```

Książka z systematycznie dodatnią medianą `edge_b` jest do pobicia. Widać to w chwili
zebrania kwot. Dlatego tydzień wystarcza tam, gdzie pomiary oparte na wynikach meczów
potrzebowały tysięcy obserwacji — wariancja wyniku meczu w ogóle nie wchodzi do równania.

## Przesłanka

Jedno zapytanie do The Odds API (EPL, 2026-08-27) zwróciło **25 bukmacherów** w regionie
`eu`, w tym `pinnacle`, `betfair_ex_eu` i `matchbook`. Crystal Palace vs Manchester City,
wynik „Crystal Palace": od **4.50** (everygame) do **5.30** (betfair_ex_eu). Zdewigowany
Pinnacle daje cenę uczciwą **4.99**, czyli 5.30 to `edge` **+6.2%** bez udziału modelu.

To jest jedna migawka jednego meczu — **hipoteza, nie znalezisko**. Może być nieodświeżoną
ofertą albo ceną bez płynności. Pilot ma to rozstrzygnąć.

## Stan wyjściowy

- `scrapers/odds_api.py` **już pobiera** kwoty wszystkich bukmacherów. `_ceny_rynku`
  zbiera je do `{outcome: [ceny]}`, gubiąc nazwę książki, a `mapuj_wydarzenie` bierze
  medianę. Rozrzut jest więc liczony i wyrzucany przy każdym zapytaniu, dzisiaj.
- Brak jakiejkolwiek tabeli kursów w bazie (12 tabel, żadna nie trzyma kwot per książka).
  Historycznie rozrzutu nie policzymy — pomiar narasta do przodu.
- `SPORT_KEYS` mapuje 12 lig (same duże europejskie). Nasze faktyczne ligi — chińska, J1,
  K League, MLS, Allsvenskan, Brasileirão B, Saudi Pro, Ligue 2, Libertadores, Carabao —
  **są dostępne w API** (46 lig na darmowej liście), tylko niezmapowane.

## Zakres pilota

Tydzień, trzy ligi:

| liga | sport_key | rola |
|---|---|---|
| Premier League | `soccer_epl` | **kontrola** — Pinnacle na pewno jest, rura musi tu działać |
| Chinese Super League | `soccer_china_superleague` | nasza, 25 meczów/30 dni, egzotyczna |
| J1 League | `soccer_japan_j_league` | nasza, 27 meczów/30 dni, egzotyczna |

Rynki: `h2h` (1X2) i `totals` na linii 2.5. Region: `eu`. Jedna migawka dziennie.

Brak Pinnacle'a w chińskiej lub J1 **jest wynikiem**, nie awarią — chcemy to wiedzieć od razu.

## Architektura

### Zasada nadrzędna: zbieraj surowo, interpretuj później

Tabela przechowuje to, co powiedziało API — bez dopasowania do naszych meczów.
Dopasowanie nazw drużyn jest najbardziej awaryjną częścią całości; siedząc w kolektorze
trwale zatruwałoby zebrane dane. Trzymamy je w warstwie raportu, żeby lepszy matcher dało
się puścić na starych danych ponownie.

### Tabela

```sql
CREATE TABLE odds_snapshots (
  id            SERIAL PRIMARY KEY,
  captured_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  sport_key     TEXT NOT NULL,
  event_id      TEXT NOT NULL,      -- stabilne id z The Odds API
  commence_time TIMESTAMP,
  team_home     TEXT NOT NULL,
  team_away     TEXT NOT NULL,
  market        TEXT NOT NULL,      -- h2h | totals
  line          REAL,               -- 2.5 dla totals, NULL dla h2h
  outcome       TEXT NOT NULL,      -- nazwa druzyny | Draw | Over | Under
  bookmaker     TEXT NOT NULL,
  price         REAL NOT NULL
);
CREATE INDEX ix_odds_snapshots_event ON odds_snapshots (event_id, market, captured_at);
```

Migracja przez `db/migrations.py`, wzorem istniejących wpisów.

### Moduły

**`src/footstats/scrapers/odds_snapshot.py`**
- `pobierz_migawke(sport_key, markets="h2h,totals", regions="eu") -> list[dict]`
- Zwraca płaskie wiersze per bukmacher. **Nie agreguje, nie liczy mediany.**
- Loguje `x-requests-remaining` z nagłówka odpowiedzi.
- `KREDYTY_MINIMUM = 50` — poniżej tego progu odmawia startu i loguje WARNING.
  Pula jest dzielona z produkcyjną ścieżką kursów i eksperyment nie ma prawa jej zjeść.

**`src/footstats/core/odds_store.py`**
- `zapisz_migawke(wiersze, dry_run=False) -> dict` — statystyki jak `uzupelnij_rynki_golowe`.
- Idempotentne po `(event_id, market, line, outcome, bookmaker, captured_at)`.

**`src/footstats/core/rozrzut_kursow.py`** — czyste funkcje, zero I/O, zero dostępu do bazy
- `devig_proporcjonalny(ceny: dict[str, float]) -> dict[str, float]`
  Proporcjonalny (multiplikatywny) devig: `p_i = (1/kurs_i) / suma(1/kurs)`.
  Znany jego mankament: przy skrajnych faworytach zawyża longshoty (favourite-longshot bias).
  Na pilota wystarcza; gdyby pomysł przeżył, do rozważenia Shin albo power devig.
- `cena_referencyjna(migawka) -> tuple[str, dict]` — wybór książki referencyjnej
  z jawnym łańcuchem: `pinnacle` → `betfair_ex_eu` → `matchbook` → mediana wszystkich.
  Zwraca też, która została użyta — raport musi to pokazywać, bo mediana miękkich książek
  jest referencją znacznie słabszą i wniosek trzeba czytać inaczej.
- `edge_bukmacherow(migawka, p_uczciwe) -> list[dict]` — `edge_b` per książka.
- `rozrzut(migawka) -> dict` — min, max, mediana, rozpiętość w %.

**Raport w `scripts/stan_uczenia.py`** — `raport_rozrzutu_kursow(conn)`

Per liga i rynek:
- **skuteczność dopasowania** — ile zebranych meczów udało się połączyć z naszym `model_log`
- liczba książek kwotujących, obecność Pinnacle'a, użyta referencja
- mediana rozpiętości w %
- książki z najwyższą medianą `edge`, z liczebnością

Skuteczność dopasowania jest **obowiązkowa, nie ozdobna**. Bez niej „brak rozrzutu"
i „nie trafiliśmy meczu" wyglądają identycznie — a to ten rodzaj cichej porażki, który
w tym projekcie kosztował już sześć dni stojącego potoku.

Liczby raportujemy z przedziałem ufności przez `core/bledy_pomiaru.py`. Gołe różnice
w punktach procentowych dwa razy 26.08 doprowadziły do fałszywego wniosku.

### Gdzie chodzi

Wpięte w istniejący job **`footstats-final`** (11:00 UTC). Zero nowej infrastruktury,
`ODDS_API_KEY` już tam jest.

Opakowane tak, żeby **nigdy nie wywróciło potoku**: wyjątek łapiemy, logujemy przez
`log.error` z pełnym kontekstem i jedziemy dalej. To jedyne miejsce w tym projekcie,
gdzie połknięcie wyjątku jest zamierzone — eksperyment nie ma prawa zatrzymać produkcji.
Głośno, ale nieblokująco.

Jeśli pilot przeżyje, przenieść na własny endpoint `/cron/odds-snapshot` ze Schedulerem,
wzorem `/cron/draft`.

### Budżet

3 ligi × 2 rynki × 1 region = **6 kredytów dziennie, 42 na tydzień**. Pozostało 473
z 500 miesięcznie. Bezpiecznik `KREDYTY_MINIMUM` chroni ścieżkę produkcyjną.

## Testy

- `rozrzut_kursow.py` — czyste funkcje, pełne pokrycie. Devig sumuje się do 1; referencja
  schodzi łańcuchem gdy Pinnacle'a brak; `edge` dodatni gdy kurs powyżej ceny uczciwej.
- `odds_snapshot.py` — **zapisane odpowiedzi API jako atrapy, zero żywych zapytań w testach**
  (reguła `.claude/rules/tests-no-prod.md`). Test bezpiecznika: przy `x-requests-remaining`
  poniżej progu kolektor nie wykonuje zapytania.
- `odds_store.py` — idempotencja: dwukrotny zapis tej samej migawki nie duplikuje wierszy.
- Test antyregresyjny: kolektor **nie może** agregować. Migawka z trzema bukmacherami
  o różnych cenach musi dać trzy wiersze, nie jeden uśredniony.

## Kryterium zakończenia

Po tygodniu:

Mierzona wielkość, żeby nie było dwuznaczności: dla każdego *(mecz, rynek, wynik)*
bierzemy **najwyższy `edge` spośród wszystkich książek** w tej migawce, a potem liczymy
**medianę po meczach** osobno dla każdej ligi. Czyli: „gdybym w każdym meczu wziął
najlepszą dostępną cenę, jaka byłaby typowa przewaga".

- **ta mediana w chińskiej i J1 poniżej +2%** → pomysł umiera, wracamy do dziennika.
  Dwa procent to mniej więcej prowizja giełdy; poniżej tego nie ma czego zbierać, choćby
  rozpiętość wyglądała efektownie.
- **powyżej +2%** → rozszerzamy na pozostałe nasze ligi i dokładamy drugą migawkę przy
  kickoffie, czyli CLV.
- **skuteczność dopasowania poniżej 50%** → wynik nierozstrzygnięty, naprawiamy matcher
  zanim cokolwiek orzekniemy. Skuteczność liczona jako: ile zebranych wydarzeń
  `odds_snapshots` udało się połączyć z wierszem `model_log` o tej samej dacie i drużynach,
  podzielone przez liczbę zebranych wydarzeń, których datę pokrywa nasz `model_log`.
  Mianownik jest ważny — mecze z dni, w których w ogóle nie zbieraliśmy danych, nie są
  porażką dopasowania.

Werdykt raportujemy z przedziałem ufności. Przy ~20 meczach na ligę tygodniowo pojedyncza
mediana ma szeroki przedział i „+2,3%" może nie różnić się istotnie od „+1,7%" — próg
stosujemy do dolnej granicy przedziału, nie do punktu.

## Ograniczenia prawne

`.claude/rules/wypuszczenie-pl.md`, art. 29 ustawy o grach hazardowych: zakaz reklamy
i promocji zakładów wzajemnych, dotyczy osoby fizycznej tak samo jak spółki.

To jest **pomiar wewnętrzny**. Nazwy bukmacherów zostają polem danych w bazie i w raporcie
dla nas. Do produktu nie trafia ani lista książek, ani wskazanie „tu jest lepszy kurs" —
to byłaby zachęta do gry.

## Poza zakresem (YAGNI)

- CLV i druga migawka przy kickoffie — dopiero jeśli pilot przeżyje.
- Pozostałe ligi — dopiero po pilocie.
- Cokolwiek w GUI.
- Zmiany w modelu, w selekcji, w `ENSEMBLE_MARKET_WEIGHT`. Ten pilot **nie dotyka modelu**;
  jego teza brzmi, że przewaga, jeśli istnieje, leży w cenie, nie w prognozie.
- Automatyczne stawianie czegokolwiek.
