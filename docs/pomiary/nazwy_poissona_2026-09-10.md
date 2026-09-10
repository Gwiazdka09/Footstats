# Pokrycie Poissona: pisownia nazw, 2026-09-10

## Stan wyjściowy

Log jobu `footstats-final` z trzech kolejnych dni:

```
08.09  Poisson policzyl 12 z 48 meczow (25%) — powody: predict_match: brak wyniku: 36
09.09  Poisson policzyl 17 z 46 meczow (36%) — powody: predict_match: brak wyniku: 29
10.09  Poisson policzyl  6 z 36 meczow (16%) — powody: predict_match: brak wyniku: 30
```

W `model_log` od 20.08: 219 z 851 ocen (26%) z `poisson-dc`. „Nasz model”
na żywo to w trzech czwartych fallback Bzzoiro-ML.

## Przyczyna: pisownia, nie brak danych

Odtworzone lokalnie na parquecie produkcyjnym (140 221 meczów, 40 lig,
dane do 03.09):

```
'Bayer 04 Leverkusen' -> 'bayer 04 leverkusen' -> brak   dataset: 'Leverkusen'   n=341
'Stoke City'          -> 'stoke city'          -> brak   dataset: 'Stoke'
'1. FSV Mainz 05'     -> '1 fsv mainz 05'      -> brak   dataset: 'Mainz'
'Real Sociedad'       -> 'real sociedad'       -> brak   dataset: 'Sociedad'
'Rayo Vallecano'      -> 'rayo vallecano'      -> brak   dataset: 'Vallecano'
'Preston North End'   -> 'preston'             -> 'Preston'        OK
'1. FC Köln'          -> 'koln'                -> 'FC Koln'        OK
```

`poisson._kanoniczne_nazwy` szukało wyłącznie **dokładnego** klucza
`normalize_team_name`. Z 887 nazw w `model_log` (sierpień–wrzesień) 499 nie
miało mapowania. `predict_match` odrzuca parę, gdy brakuje choć jednej strony.

## Druga dziura tego samego kształtu: ramię Dixon-Coles

`quick_picks` woła z tymi samymi `g, a` dwie funkcje:

```
predict_match(g, a, df_mecze)          -> tłumaczy nazwę przez _kanoniczne_nazwy
blend_dixon_coles(_p_pois, g, a, df)   -> _compute_ratings: df["gospodarz"] == g
```

Druga porównywała nazwę **dokładnie**, z pominięciem nawet aliasów
z `utils/normalize`. „Manchester United” to w datasecie „Man United” — classic
liczył, ramię DC po cichu oddawało `p_model` bez zmian. Walk-forward, na
którym strojono `W_BAYESIAN`, podaje nazwy wprost z datasetu, więc tam ramię
działa zawsze. Produkcja miała inny model niż zmierzony.

## Naprawa — w `poisson.py`, celowo nie w `utils/normalize`

Aliasy w `utils/normalize` działają globalnie: rozliczenia kuponów,
dopasowanie meczów u dostawców, klucze `player_db`. „Stoke City” ma tam
zostać „stoke city”, bo człon `city` odróżnia kluby w `team_similarity`.
Precedens: `data/rozszczepienia.py` i cofnięty alias `shanghai sipg`.

Reguły zapasowe, wszystkie deterministyczne, **bez podobieństwa nazw**
(to ono myliło Wisłę Kraków z Wisłą Płock):

1. **Cyfry to szum** — „SC Paderborn 07” → `paderborn`, „Bayer 04 Leverkusen”
   → `bayer leverkusen` → istniejący alias → `leverkusen`.
2. **Słowa-szum** (`bayer`, `borussia`, `real`, `kaa`, `krc`, `aif`, `fsv`) —
   „Borussia M'gladbach” → `mgladbach`. „Real Madrid” trafia dokładnym kluczem
   wcześniej, więc lista go nie dotyka.
3. **Człon tożsamości, którego dataset nie pisze** — „Stoke City” → `stoke`.
   Ta sama reguła, której ufają rozliczenia, z tym samym wyjątkiem:
   `_BAZY_WIELOZNACZNE` (Bristol City / Bristol Rovers) zostają bez mapowania.
4. **Świeżość** — trafienie zapasowe tylko przy historii młodszej niż 400 dni.
   λ z meczów sprzed lat to λ innej drużyny.

Świadomie **bez** dopasowania po podzbiorze słów: Independiente del Valle
(Ekwador) to nie Independiente (Argentyna), Tokyo Verdy to nie FC Tokyo.

`blend_dixon_coles` tłumaczy teraz nazwy tą samą funkcją co classic.

## Wynik

Te same 1231 par z `model_log` (od 01.08), ten sam parquet, `predict_match`
przed i po zmianie:

```
                      przed         po
Poisson liczy     347 (28,2%)   514 (41,8%)

Championship         6/37         35/37
League Two           7/32         32/32
League One           5/33         25/33
National League      6/38         27/38
Carabao Cup         13/56         50/56
Conference League   13/74         17/74
```

Ramię Dixon-Coles na tych samych 514 parach, na których classic liczy:

```
predict_match_bayesian z SUROWYMI nazwami (stan do 10.09):  141 (27%)
predict_match_bayesian z nazwami KANONICZNYMI:              514 (100%)
```

Czyli nawet tam, gdzie Poisson działał, w trzech przypadkach na cztery
produkcja liczyła 1X2 bez ramienia, na którym strojono `W_BAYESIAN = 0.49`.
To największa zmiana zachowania w tej poprawce: rozkład 1X2 zmienia się na
~370 parach, dotąd liczonych samym classic. Kierunek zgodny z pomiarem
walk-forward (tam ramię działa zawsze), ale **na żywo niezmierzony** —
do sprawdzenia w kalibracji `model_log` po kilkudziesięciu rozliczonych.

### Przegląd ręczny — dwa błędy złapane, zanim weszły

Wszystkie 70 nowo zmapowanych nazw przejrzane jedna po drugiej. 68 było
poprawnych (Stoke City → Stoke, KAA Gent → Gent, VfL Bochum 1848 → Bochum...).
Dwa **nie**:

* `Real Racing Club` (Santander) → `Racing Club` — **Racing z Argentyny**.
  Po zdjęciu `real` nazwa się zgadza, a świeżość historii niczego nie
  odsiewa, bo Argentyńczycy grają. Słowo-szum wymaga teraz kraju ligi
  trafienia (`real` → ESP); Racing Santander dostał jawny alias na
  `Santander` (w datasecie, ESP-La Liga).
* `Cambridge City` (poza ligami, Puchar Anglii) → `Cambridge`, czyli
  **Cambridge United**. Dataset zna jeden klub z tą bazą, więc
  `_BAZY_WIELOZNACZNE` liczona z danych tego nie widzi. Lokalna lista baz
  wieloznacznych spoza danych.

Po korekcie diff mapowań zmienia **tylko** te dwie nazwy. Pokrycie zostaje
514: oba mecze Racingu (z Villarrealem i Elche) liczyły się już wcześniej —
tylko z cudzą drużyną — a mecz Cambridge City z Maldon & Tiptree nie liczył
się wcale, bo rywala nie ma w danych.

Wniosek do powtarzania: reguła, która **wygląda** na deterministyczną,
dalej potrafi skleić dwa kluby. Przegląd listy trafień to część zmiany,
nie jej opcjonalny dodatek.

## Co zostaje

Ligi, których w datasecie nie ma wcale — ocen z `model_log` od 01.08:
K League 1 (41), Brasileirão Serie B (40), Saudi Pro League (38), Liga
Portugal 2 (32), Categoría Primera A (20), Parva Liga (12). Razem ~15% ocen.
Wymaga backfillu meczów z API-Football i przebudowy datasetu — osobny projekt.

Fortress, H2H i heurystyki zmęczenia w `quick_picks` też dostają surowe
nazwy. Zwracają wtedy neutralne mnożniki, więc λ jest poprawna, tylko bez
tych korekt. Nie ruszane w tej zmianie.
