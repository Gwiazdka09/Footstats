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
