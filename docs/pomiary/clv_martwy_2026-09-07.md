# CLV nie powstał ani razu w historii projektu, 2026-09-07

Nie pomiar hipotezy — naprawa. Znalezione przy audycie „czy wszystko jest
podłączone".

## Stan zastany

```sql
SELECT COUNT(*) FROM predictions;                              -- 295
SELECT COUNT(*) FROM predictions WHERE clv_closing_odds IS NULL; -- 295
```

Zero na 295, mimo że wszystkie części działały:

* `core/clv_tracker.record_closing_odds` — ma własne testy;
* `scrapers/closing_odds.kursy_zamkniecia` — ma własne testy, CSV
  football-data z kolumnami closing Pinnacle;
* `evening_agent` **woła** `record_closing_odds` (linia 438);
* joby `footstats-evening` kończą się `exit=0` codziennie.

## Trzy przyczyny, jedna pod drugą

### 1. Bramka na kluczu, którego nikt nie zapisuje

```python
pred_id = leg.get("prediction_id")
if pred_id:
    ...cały blok CLV...
```

`grep prediction_id` po całym `src/` pokazuje **wyłącznie odczyty** — jedyne
trafienie poza `clv_tracker` to ta linia. Pomiar: **0 z 82** nóg w 60
rozliczonych kuponach ma ten klucz.

### 2. Dopisanie klucza by nie wystarczyło

Główne źródło kuponów, `system_paper.build_single_leg_coupons`, **nie przechodzi
przez `predictions` w ogóle** — bierze typ prosto z modelu (`najlepszy_typ`),
bez LLM-a. To **429 z 439** rozliczonych kuponów. CLV oparte na `predictions`
nie miałoby ich jak objąć.

Ten sam fakt jest już udokumentowany kilka linii wyżej w `system_paper`:
„z 243 rozliczonych kuponów ligę udało się odtworzyć dla 25, bo `predictions`
zapisuje wyłącznie typy, które przeszły przez LLM-a".

### 3. Cena brana z niewłaściwego zdarzenia

Fallback football-data brał `kursy.get("home")` **dla każdego typu**. Komentarz
bronił tego zgodnością z istniejącymi CLV — a tych było zero.

Rozkład typów w 531 rozliczonych nogach:

```
Over 2.5    159      1     83      1X        14      Over 1.5   27
Under 2.5   139      2     22      X2         8      BB: ...     9
BTTS         62                    BTTS nie   3      Under 3.5   1
```

Mapowalnych na kursy zamknięcia (`home/draw/away/over_2_5/under_2_5`) jest 403
nóg = **76%**. Czyli 76% CLV liczyłoby się z ceny innego zdarzenia, a pozostałe
24% i tak nie ma odpowiednika.

## Naprawa

* `closing_odds.kurs_dla_typu(kursy, typ)` — mapa typ → cena, **celowo wąska**.
  `Over 1.5` NIE dostaje ceny `2.5`: to inne zdarzenie i CLV wyszłoby dodatnie
  z samej różnicy linii.
* `evening_agent._kurs_zamkniecia_nogi(...)` — liczone dla **każdej** nogi,
  nie pod bramką `pred_id`. Wynik ląduje w `legs_json` jako `clv_closing`;
  `record_closing_odds` zostaje jako dodatek, gdy `pred_id` istnieje.
* Kolejność źródeł odwrócona: CSV najpierw. `_fetch_closing_odds` pyta API-Football
  o `bet=1` (Match Winner) i oddaje **wyłącznie stronę gospodarza**, więc dla
  `2` czy `Over 2.5` powtarzałby ten sam błąd w drugim źródle. Oba mierzą wobec
  Pinnacle, więc wyniki zostają porównywalne.
* `clv_tracker.raport_clv_z_kuponow` + `scripts/clv_raport.py` — czytnik. Bez
  niego CLV byłoby telemetrią wyłącznie do zapisu, czyli dokładnie tym, co ten
  audyt znalazł w trzech innych miejscach.
* Licznik `nowe_clv` w podsumowaniu wieczornym i WARNING, gdy przy niezerowej
  liczbie rozliczonych nóg nie powstało ani jedno CLV. Zero bez licznika wygląda
  identycznie jak brak meczów — tak ten błąd przeżył całą historię projektu.

## Straż

`test_blok_clv_nie_stoi_pod_bramka_prediction_id` czyta ŹRÓDŁO
`run_evening_agent` i sprawdza, że liczenie CLV nie wróciło pod `if pred_id:`.
Test na sam wynik nie odróżnia „policzone" od „policzone dla nogi, która
akurat miała id" — a każdy kawałek tego łańcucha miał zielone testy przez cały
czas trwania błędu.

Strażnik przy pierwszym uruchomieniu wywrócił się na **własnym uzasadnieniu**:
komentarz opisujący naprawiony błąd zawiera literał `if pred_id:`. Filtruje
teraz linie komentarza.

## Czwarta rzecz, znaleziona przy próbie weryfikacji

**Nie udało się dziś potwierdzić CLV na danych, bo źródło jest padnięte.**
football-data.co.uk oddaje HTTP 503 na **całej witrynie**, także na stronach
HTML — to awaria serwisu, nie blokada na nas:

```
mmz4281/2627/E0.csv   kod=503 rozmiar=489
mmz4281/2526/E0.csv   kod=503 rozmiar=489
englandm.php          kod=503 rozmiar=489
```

Przy okazji wyszedł problem, który sam bym wprowadził: `FootballDataSource.
_pobierz_csv` zapisuje do cache plikowego **wyłącznie udane** pobranie. Porażka
nie zostawia śladu, więc każde kolejne wywołanie znów wychodzi do sieci —
zmierzone 11.9 s i 7.5 s na dwa kolejne wywołania. `kursy_zamkniecia` iteruje
13 lig, a CLV liczy się teraz dla każdej nogi, więc przy 30 nogach wieczornych
byłoby to **390 zapytań do martwego hosta z timeoutem 15 s**. Rozliczanie
kuponów wisiałoby na telemetrii.

Naprawione `functools.lru_cache` na `_csv_ligi` — pamięć procesu, a joby są
krótkotrwałe, więc „raz na proces" znaczy „raz na przebieg". Pilnuje
`tests/test_closing_odds_cache.py`, w tym przypadek 20 nóg → 13 zapytań.

Konsekwencja dla oceny: pierwszy realny pomiar CLV zależy od tego, czy
football-data wróci. Jeśli nie wróci, zostaje API-Football, ale tylko dla typu
`1` — czyli 83 z 531 nóg. Warto to sprawdzić przy najbliższej okazji zamiast
zakładać, że dane popłyną.

## Czego to NIE mierzy

CLV powstaje tylko dla typów z odpowiednikiem w CSV. Brak wiersza dla BTTS czy
podwójnej szansy nie znaczy „ten typ był zły" — znaczy „nie ma z czym porównać".
Raport mówi to wprost, bo cichy brak 24% próby to gotowy fałszywy wniosek.
