# Obserwacja modelu — dziennik pomiarów

Model jest **zamrożony od 2026-09-10** (patrz `CLAUDE.md`). Ten plik zbiera **pomiary**,
nie zmiany: czy potok codziennie liczy predykcje, czy model mówi prawdę o swojej
pewności i czy po miesiącu jest powód, żeby go kalibrować.

Narzędzie pomiaru: `python -m scripts.stan_uczenia` (tylko odczyt) — sekcja
„OBCIĄŻENIE MODELU” to test na całej próbie naraz (1 stopień swobody, dużo większa moc
niż kubełki). Kubełki bez błędu standardowego kłamią — dwa fałszywe wnioski z 26.08.

---

## Reguła decyzji o kalibracji — ustalona Z GÓRY (2026-09-22)

Zapisana przed zobaczeniem danych z okna testowego, żeby nie dopasować progu do wyniku.

- **Okno testowe:** wyłącznie wiersze `model_log` utworzone **2026-09-22 … 2026-10-22**.
  Dane sprzed 22.09 posłużyły do postawienia hipotezy i **nie liczą się** do jej
  potwierdzenia (replikacja przed ustaleniem).
- **Mierzymy osobno `poisson-dc`** (nasz model). `bzzoiro-ml` to zewnętrzne ramię —
  jego obciążenie nie jest argumentem za kalibracją naszego modelu.
- **Kalibrację proponujemy tylko, gdy na tym samym wyjściu jednocześnie:**
  1. |z| ≥ 2,64 (poprawka Šidáka na 6 testowanych wyjść, p < 0,0085),
  2. |różnica| ≥ 3 pp (minimalny rozmiar efektu — sam próg z nie mierzy ważności),
  3. kierunek zgodny z próbą odkrywczą (dla Over 2.5 i typu #1: model **zaniża**).
- **Dodatkowy warunek:** dopasowany kalibrator musi poprawić NLL **out-of-sample**
  (chronologiczny holdout). 27.08 dopasowanie kalibratora pogorszyło NLL — wtedy nie
  było czego kalibrować.
- **Nawet przy spełnieniu warunków** wdrożenie kalibratora to zmiana modelu, czyli
  zdjęcie zamrożenia — decyzja właściciela projektu, nie krok automatyczny.

---

## 2026-09-22 — punkt wyjścia

**Potok:** evening 21.09 ✅, draft/settle/kalibracja 22.09 rano ✅, obraz jobów
z commita `91417bd77` (świeży zbiór 140 919 meczów do 17.09). Draft dał kupony #677, #678.

**Obciążenie na całej próbie `model_log`** (n=1279 rozliczonych, oba ramiona razem):

| wyjście | deklaruje | zaszło | różnica | z | werdykt |
|---|---|---|---|---|---|
| 1 | 43,8% | 44,2% | +0,4 pp | +0,27 | szum |
| X | 25,0% | 23,1% | −1,8 pp | −1,53 | szum |
| 2 | 31,2% | 32,7% | +1,5 pp | +1,21 | szum |
| Over 2.5 | 52,9% | 56,4% | **+3,5 pp** | **+2,55** | istotne bez korekty |
| BTTS | 53,5% | 56,0% | +2,5 pp | +1,80 | szum |
| typ #1 | 50,5% | 53,2% | +2,7 pp | +1,99 | istotne bez korekty |

Po poprawce Šidáka na 6 wyjść (|z| ≥ 2,64) **żadne nie przechodzi.**

**Rozbicie — gdzie siedzi sygnał:**

| grupa | n | Over 2.5 różnica / z | typ #1 różnica / z |
|---|---|---|---|
| do 27.08 | 446 | +3,4 pp / 1,48 | +2,3 pp / 1,02 |
| po 27.08 | 833 | +3,5 pp / 2,08 | +2,9 pp / 1,72 |
| **poisson-dc** | 426 | +1,9 pp / 0,79 | +3,0 pp / 1,26 |
| bzzoiro-ml | 850 | **+4,2 pp / 2,46** | +2,6 pp / 1,58 |

**Odczyt:**
- Kierunek jest stabilny w czasie (obie połowy zaniżają Over 2.5 o ~3,5 pp) — to nie
  jednorazowe wahnięcie, ale też jeszcze nie dowód.
- Obciążenie Over 2.5 siedzi głównie w **bzzoiro-ml**, nie w naszym `poisson-dc`
  (z=0,79). Możliwe też wyjaśnienie bez błędu modelu: sezon po prostu bramkowy
  (56,4% Over wobec ~52% deklarowanych).
- Typ #1 zaniżony o ~3 pp w obu ramionach: model jest raczej **niedopewny** niż
  przepewny — w kubełkach 50–60% i 60–70% trafia o 5,5 i 8,3 pp więcej, niż deklaruje.
- Krzywe rosną na wszystkich rynkach (1X2 rozpiętość 48,7 pp, Over 31,3 pp) — liczby
  rozróżniają mecze.
- Przewaga nad kursem bukmachera: brak. Over 2.5 ROI −10,8%, Under −15,0%, BTTS −18,3%,
  1X2 +3,8% przy p=0,79 (szum).

**Werdykt na dziś:** nie kalibrować. Hipoteza do sprawdzenia 22.10: *`poisson-dc` zaniża
Over 2.5 i pewność typu #1*. Sprawdzenie według reguły wyżej.

**Następny pomiar:** 2026-10-22.

---

## 2026-09-24 — potok trzyma się po naprawie

Dwa zaplanowane przebiegi `footstats-final` po naprawie normalizacji kuponu (`985dfd8be`)
zakończone sukcesem: **22.09 (`trl69`)** i **23.09 (`cdm59`)**, oba ~09:03 UTC. `footstats-evening`
22.09 i 23.09 również zielone. Dla porównania 21.09 dwa przebiegi padły (`hxg5f`, `776mz`)
na dokładnie tym samym warunku — dzień bez typów. Regresja zamknięta.

Obraz jobów: commit `91417bd77` (zbiór do 17.09).

## 2026-10-22 — pomiar decyzyjny: kalibracji NIE proponujemy

Okno `model_log` 2026-09-22…2026-10-22, tylko `poisson-dc`, rozliczone: **n=267**
(277 wierszy w oknie; 8 nierozliczonych — 7 z 22.10 i Osasuna – Racing z 18.10;
2 wyniki po dogrywce/karnych nierozliczalne). Pierwszy wiersz `poisson-dc` w oknie: 25.09.
Zero duplikatów. Liczone tymi samymi funkcjami co `scripts.stan_uczenia`
(`sprawdz_obciazenie`, `oblicz_tip_correct`), w transakcji READ ONLY.

| wyjście | deklaruje | zaszło | różnica | z | W1 \|z\|≥2,64 | W2 ≥3 pp | W3 kierunek |
|---|---|---|---|---|---|---|---|
| 1 | 43,7% | 46,1% | +2,4 pp | +0,81 | nie | nie | tak |
| X | 24,6% | 21,3% | −3,3 pp | −1,24 | nie | tak | tak |
| 2 | 31,7% | 32,6% | +0,9 pp | +0,32 | nie | nie | tak |
| Over 2.5 | 55,0% | 60,3% | +5,3 pp | +1,75 | nie | tak | tak |
| BTTS | 55,3% | 56,2% | +0,8 pp | +0,28 | nie | nie | tak |
| typ #1 | 48,7% | 55,4% | +6,7 pp | +2,23 | nie | tak | tak |

**Werdykt wg reguły: żadne wyjście nie spełnia warunku 1 → nie kalibrujemy, model
zostaje zamrożony.**

**Odczyt:**
- Kierunek hipotezy się utrzymał i efekt urósł (Over 2.5 +1,9 → +5,3 pp, typ #1
  +3,0 → +6,7 pp), ale przy n=267 błąd standardowy różnicy to ~3 pp, więc próg
  z=2,64 wymaga ~7,9 pp. Próba za mała na potwierdzenie — progu nie przesuwamy po fakcie.
- NLL out-of-sample (chronologicznie 70/30, n=186/81): przesunięcie w logit poprawia
  test dla Over 2.5 (0,6566 → 0,6484) i typu #1 (0,7124 → 0,6965); Platt też. Bez
  znaczenia dla decyzji, bo warunek 1 nie przeszedł.
- `bzzoiro-ml` (kontekst, n=562): wszystkie wyjścia |z| < 1,6; jego obciążenie
  Over 2.5 z 22.09 (+4,2 pp) zniknęło (+0,6 pp).
- Ramiona nie mają wspólnych meczów — z założenia: mecz trafia do `poisson-dc`,
  a gdy Poisson go nie policzy, do fallbacku `bzzoiro-ml`.
- 7 wierszy z 22.10 rozliczy się po kolejnych przebiegach; z typu #1 mogłoby przekroczyć
  2,64 tylko przy trafieniu praktycznie wszystkich 7 — do potwierdzenia powtórką skryptu.

**Następny pomiar:** do decyzji właściciela (nowe okno trzeba ustalić Z GÓRY).

---

## 2026-10-23 — krok 1: linie goli czystego Poissona (próba ODKRYWCZA)

Narzędzie: `raport_linii_goli` w `scripts/stan_uczenia.py`. Linie Over 0.5–4.5 liczone
z `lambda_h`/`lambda_a` tą samą macierzą co predykcja (`core/poisson.prob_linii_goli`).

**Ważne o danych:** `prob_*` wierszy `poisson-dc` w `model_log` to mieszanka z Bzzoiro
(`core/ensemble`, `ENSEMBLE_MARKET_WEIGHT=0.70` na obu jobach → 70% Bzzoiro, 30% Poisson);
lambdy są sprzed mieszania. Over 2.5 z lambd vs zapisane: średnio 6,1 pp (382/420 > 1 pp).
**Pomiar decyzyjny z 22.10 dotyczył więc mieszanki, nie samego Poissona.** Surowych
prawdopodobieństw Poissona nikt nie zapisuje.

Okres 2026-09-11 … 2026-10-22, n=418 rozliczonych (2 wyniki po dogrywce/karnych odpadają):

| linia | deklaruje | zaszło | różnica | z |
|---|---|---|---|---|
| Over 0.5 | 92,4% | 96,4% | +4,0 pp | +3,11 |
| Over 1.5 | 75,3% | 78,5% | +3,1 pp | +1,52 |
| Over 2.5 | 51,4% | 58,1% | +6,7 pp | +2,82 |
| Over 3.5 | 30,4% | 38,8% | +8,4 pp | +3,85 |
| Over 4.5 | 15,7% | 20,8% | +5,2 pp | +2,98 |

Suma λ średnio 2,77, gole 3,09: **+0,32 gola na mecz (SE 0,088)**. Obie połowy okresu
w tę samą stronę (Over 3.5: +6,7 pp z=2,18 do 07.10; +10,1 pp z=3,26 po 07.10).

**Odczyt:** czysty Poisson zaniża sumę goli o ~11%. To próba odkrywcza — nie traktujemy
jej jako ustalenia (zasada: replikacja przed ustaleniem). Możliwe przyczyny bez błędu
modelu: sezon bramkowy (22.09 też 56,4% Over przy ~52% deklarowanych), selekcja lig
przez whitelistę.

**Reguła replikacji — ustalona Z GÓRY (2026-10-23):**
- Okno: wiersze `model_log` `poisson-dc` z lambdami, utworzone **2026-10-24 … 2026-11-23**.
- Test główny: średnia (gole − λ_h − λ_a) > 0, z ≥ 2,58 i efekt ≥ +0,15 gola.
- Warunek kierunku: Over 2.5 i Over 3.5 czystego Poissona — obie różnice > 0.
- Równolegle offline: walk-forward na `full_dataset.parquet` (sezon 2025/26) — czy
  estymator λ zaniża sumę goli także na danych historycznych.
- Spełnione → propozycja korekty λ (rynki golowe, zasady odmrożenia) z warunkiem poprawy
  NLL out-of-sample; decyzja właściciela.

**Następny pomiar:** 2026-11-23.


## 2026-10-25 — krok 2: pokrycie Poissona

**Diagnoza** (wiersze `model_log` 23.09–22.10, ligi z whitelisty mające dane w zbiorze):
398 unikalnych meczów, Poisson policzył 244 (**61,3%**), 154 poszło na fallback `bzzoiro-ml`.
We WSZYSTKICH 154 przynajmniej jedna drużyna nie była rozpoznana przez
`poisson._kanoniczne_nazwy` (106 różnych nazw: „SG Dynamo Dresden” vs „Dresden”,
„Atlético Madrid” vs „Ath Madrid”, „Levante UD”, Ligue 2, Allsvenskan, Superliga RO,
Argentyna, National League, J1…). Przyczyna to pisownia, nie brak danych.

**Zmiana:** `data/team_mappings.json` +99 par (klucz = nazwa źródła znormalizowana bez
mapowań, wartość = nazwa ze zbioru), każda zatwierdzona ręcznie jako ten sam klub w tej
samej lidze. Bez zmian w kodzie; `_kanoniczne_nazwy` nadal bez dopasowania rozmytego.
Kontrole przed zapisem: brak konfliktu z istniejącymi kluczami, brak łańcuchów, klucz nie
równa się nazwie innego klubu ze zbioru; po zapisie liczba unikalnych postaci
kanonicznych nazw zbioru bez zmian (1072 → 1072), zero nowych kolizji.

**Pomiar przed/po** (te same 398 meczów, `predict_match` z opcjami domyślnymi):

| | przed | po |
|---|---|---|
| (a) obie nazwy rozpoznane | 244 (61,3%) | 383 (96,2%) |
| (b) `predict_match` != None | 244 (61,3%) | 382 (96,0%) |

**Brak w zbiorze** (nie mapowane): Oxford United, Peterborough United, Plymouth Argyle,
Queens Park Rangers (angielskie League One/Championship — etykieta ligi zlana z
szkocką/aliasem, zbiór nie ma tych klubów), Celta Fortuna (rezerwy).
**Wątpliwe / konflikt z testami** (celowo pominięte): „Wisła Kraków” → „Wisla” psuje
`test_af_backfill` (dwie nazwy źródła na jedną drużynę), „Turun Palloseura” → „TPS”
zeruje `team_similarity` do „Turku PS” w `test_aliasy_nazw_z_zaleglosci` (rozliczenia).
Reszta niedopasowań: „PK-35|FF Jaro” — nazwy OK, za mało świeżej historii.

**REGUŁA AKCEPTACJI NA ŻYWO — ustalona Z GÓRY (2026-10-25):**
- Okno: 7 dni od wdrożenia.
- W ligach whitelisty z danymi udział meczów policzonych przez `poisson-dc` ≥ **85%**
  (przed: 61,3%).
- Zmiana zostaje, jeśli próg spełniony ORAZ ręczna kontrola 20 losowych nowych
  dopasowań nie znajdzie pomyłki; inaczej revert pomyłkowych wpisów.

**Pewność linii goli ≠ 2.5 (2026-10-26).** Od #51 (22.10) `prob_modelu` zwracał None dla
Over/Under ≠ 2.5, więc `pewnosc_z_modelu` zapisywał do `predictions.ai_confidence` stałe
Groq-fallback/50 zamiast prawdopodobieństwa modelu, a filtr longshot (`_MIN_PROB_MODELU`)
przepuszczał takie nogi. Poprawka liczy te linie z λ (`prob_linii_goli`), Over/Under 2.5
bez zmian. Wiersze `predictions` z linią ≠ 2.5 zapisane 22.10–26.10 mają „pewność” bez
pokrycia w modelu — w raportach kalibracji odcinać datą (match_date/created ≥ 2026-10-27)
albo wykluczać te linie.
