# Pełne kadry zamiast czołówki strzelców, 2026-09-07

Ciąg dalszy `goal_share_zmyslony_2026-09-07.md`. Tam próg `MIN_SKLAD` przestał
przepuszczać zmyślone udziały; tutaj chodzi o to, żeby było **co** przepuścić.

## Stan wyjściowy

Po nałożeniu progu kanał team-news działa, ale prawie nic nie waży:

```
udzialy absencji 3/24 dopasowane w player_db
```

Znamy nazwisko nieobecnego, nie znamy jego znaczenia. Powód: jedyne źródło
pełnych składów (Understat) padło tego samego dnia — `GET
understat.com/league/EPL/2026` oddaje HTTP 200 i 4684 bajty bez `playersData`,
to samo na 2025. Zostawało `/players/topscorers`, czyli **20 nazwisk na całą
ligę**, 1-4 na drużynę.

## Sprawdzone i odrzucone: FotMob

FotMob `/api/data/teams?id=` oddaje pełny skład z golami, pozycjami i ratingiem.
Nie nadaje się mimo to, i to z dwóch powodów:

* **Tylko bieżący sezon.** Parametr `season` jest ignorowany — sprawdzone na
  `2025/2026` i `2024/2025`, każde żądanie zwraca to samo. Zmierzone na
  Liverpoolu: **29 osób, 6 goli łącznie**. To dokładnie ten szum, przed którym
  ostrzega `core/absencje.py` („udział jednego strzelca wyszedłby 0,4").
* **Zapytanie na drużynę**, a historię trzeba by dociągać per gracz.

## Wybrane: API-Football `/players`

`/players?league=&season=&page=` oddaje całą ligę stronami po 20, z golami per
klub. Zmierzone: Premier League 2025 to 34 strony, Ekstraklasa 2025 — 36 zapytań
i 687 graczy. Przy planie Pro (7500/dzień) koszt jest do zapłacenia.

Różnica wobec `parse_topscorers` jest jedna, ale zasadnicza: **nie odrzucamy
graczy z zerem goli**. Mianownik `goal_share` to suma graczy zapisanych, więc
kompletność tabeli JEST mianownikiem — i to po ich liczbie `MIN_SKLAD` odróżnia
skład od czołówki.

Gracz po transferze ma kilka wpisów w `statistics`, po jednym na klub. Bierzemy
każdy: gole strzelone w innym klubie nie mogą wejść do udziału w tym.

## Sezon: ostatni pełny, nie bieżący

`team_goal_shares_recent` cofa się sam (próg `MIN_SKLAD` odrzuca cienki sezon
bieżący), więc wystarczy wypełnić 2025.

## Pokrycie — liczba, która zmienia plan

Pomiar `model_log` z 21 dni:

```
ocen lacznie: 765,  lig: 58,  rozklad PLASKI (najwieksza 6%)
  w naszych 16 ligach fixture'owych:  158  (21%)
  POZA nimi:                          607  (79%)
```

Największe nieobjęte: Liga Konferencji (44), National League (38), J1 (34),
K League (26), Puchar Polski (25), Ligue 2 (24), Liga Europy (24), Chinese Super
League (24), Carabao Cup (24), League One/Two (43 razem).

**Ale liczyć trzeba po DRUŻYNACH, nie po lidze meczu.** `goal_share` kluczuje po
`team_norm`, więc mecz Ligi Konferencji dostaje wagi z ligi krajowej swoich
uczestników. Widać to wprost na Lidze Mistrzów: jedno pobranie `id=2` dało
**69 drużyn** z całej Europy. Puchary europejskie są najgęstszym źródłem, jakie
mamy — jedno zapytanie na ligę, kilkadziesiąt drużyn z kilkunastu krajów.

Stąd `_LIGI_SKLADOW` w `scripts/refresh_players.py`: lista rozgrywek, z których
**nie bierzemy meczów**, ale których drużyny oceniamy. Świadomie osobna od
`_APISPORTS_LIGI`, bo to inne pytanie.

ID sprawdzone pojedynczo przez `/leagues?search=`, zgodnie z ostrzeżeniem
z `data/af_league_ids.json`. To nie jest ostrożność teoretyczna: „National
League" to również Mjanma (588), „Ligue 2" również Algieria (187) i Tunezja
(828), „League One" również Szkocja (183) i Chiny (170). Błędny wybór jest
**cichy** — statystyki z innych rozgrywek weszłyby w drużyny, których nie
dotyczą.

## Backfill zablokował się na własnym cache

31 lig × ~34 strony to ~1100 zapytań. Po sześciu ligach pobieranie zwolniło do
**7 minut na ligę** — i czas szedł na **dysk**, nie na sieć.

Disk cache API-Football to JEDEN plik JSON. Każde zapytanie czyta go i parsuje
w całości, po odpowiedzi czyta drugi raz (żeby porównać ze starym) i zapisuje
w całości. Plik urósł do **30 MB**, więc jedno zapytanie kosztowało ~90 MB I/O,
a koszt rósł kwadratowo. Dla pierwotnego użycia (`/players/topscorers`, jedno
zapytanie na ligę) to było bez znaczenia.

```
z cache:   ~34 zapytania / 7 minut   =  0.08 req/s
bez cache:  57 zapytan / 75 sekund   =  0.76 req/s     10x
```

`bez_cache=True` pomija cache, ale **nie** ochronę konta: budżet i bramka
`apisports_gate` działają normalnie.

## Drugi problem: 66% nazwisk było w formie skróconej

Po backfillu sanity pokazał to wprost:

```
Liverpool     'Hugo Ekitike', 'H. Ekitike', 'Cody Gakpo', 'C. Gakpo', ...
Real Madrid   'Kylian Mbappe-Lottin', 'Kylian Mbappé', 'J. Bellingham', ...
```

**16 093 z 24 417 nazwisk (66%)** to forma `H. Ekitike` — tak oddaje je
API-Football. FotMob, źródło absencji, pisze pełne imię. To rodzi dwie osobne
szkody:

1. **Mianownik podwojony.** Ten sam człowiek jako dwa wiersze, a `goal_share`
   dzieli przez sumę graczy zapisanych. Bayern wychodził z 38 nazwiskami przy
   kadrze ~30.
2. **Absencje się nie dopasowują.** `absencje._dopasuj` znało dwie reguły:
   równość i prefiks. Skrót **nie jest** prefiksem pełnego imienia, więc żadna
   ich nie łączy. To jest prawdziwa przyczyna produkcyjnego
   `udzialy absencji 3/24 dopasowane` — sam backfill by jej nie naprawił,
   dokładał tylko więcej nazwisk w formie, która i tak nie pasuje.

Naprawa to jeden klucz w jednym miejscu: `klucz_skrocony` (inicjał + nazwisko,
obok `klucz_gracza` w `teamnews/base.py`), użyty po obu stronach.

* **`absencje._dopasuj`** dostaje trzecią regułę, po równości i prefiksie.
  Zachowawczą jak tamte: minimum dwa człony i **jednoznaczność** — dwóch
  kandydatów oznacza odrzucenie, bo cudzy udział jest gorszy niż brak udziału.
* **`player_db._scal_duplikaty`** scala wiersze, ale tylko gdy jedna pisownia
  jest SKRÓTEM drugiej i pełna wersja jest dokładnie jedna. „Moussa Diallo"
  i „Mamadou Diallo" zostają osobno — żaden nie jest skrótem, to mogą być dwie
  różne osoby. Zostaje pełna pisownia (lepiej pasuje do FotMoba), a gole to
  **maksimum, nie suma**: źródła mogą pokrywać różne rozgrywki.

## Wynik

```
zrzut         2913 -> 10175 graczy,  252 -> 692 druzyny,  212 KB -> 716 KB
sezon 2025     83 -> 516 uzytecznych druzyn (>= 8 strzelcow), mediana 14
pokrycie       8.6% -> 38% druzyn z realnego ruchu (model_log, 14 dni)
udzialy        max 9-25% zamiast 100%
```

Dopasowanie absencji na próbie 10 dużych klubów, nazwiska pisane pełnie jak
w FotMobie: **16/24 (67%)** wobec produkcyjnego `3/24`. To była **górna
granica**, nie prognoza — próba to najlepiej pokryta część.

### Pomiar na ŻYWYM źródle, 08.09 — 161 meczów, 144 absencje

```
z waga (dopasowane):          44  (31%)      bylo 3/24 = 12.5%
druzyna znana, brak gracza:   57  (40%)
brak skladu druzyny:          43  (30%)

druzyn ze skladem: 25, bez: 13
```

**31% wobec 12.5%** — dwuipółkrotnie, na prawdziwych absencjach z FotMoba, a nie
na ręcznie dobranej próbce. To jest liczba do cytowania.

Osiem niedopasowanych to w większości bramkarze i obrońcy z zerem goli, więc
poprawnie nie mają udziału w ATAKU. `udzialy_absencji` wkłada ich do
`nietrafione` („nie wiem"), a nie do udziałów jako zero — konserwatywnie, ale
dla zawodnika, który JEST w składzie z zerem goli, wiemy więcej niż „nie wiem".
Do rozważenia osobno; dzisiejsza zmiana tego nie rusza.
