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

## Wynik

(uzupełniane po przebiegu — patrz sekcja niżej)
