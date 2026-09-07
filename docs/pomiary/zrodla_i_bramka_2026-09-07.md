# Trzy martwe źródła i brama, której nie było, 2026-09-07

Znalezione przy audycie „czy wszystko jest podłączone i działa". Nie pomiary
hipotez — stan faktyczny sprawdzony na żywych źródłach i produkcyjnych logach.

## 1. SofaScore — 146 zapytań, 146 blokad, zero sukcesów

```
[SofaScore] HTTP 403: /search/all   x146   (25.08 - 07.09, wszystkie przebiegi)
```

Sprawdzone tego dnia bezpośrednio, z przeglądarkowym User-Agentem:

```
api.sofascore.com/api/v1/search/all?q=Arsenal        403
www.sofascore.com/api/v1/search/all?q=Arsenal        403
api.sofascore.com/api/v1/sport/football/events/live  403
```

Blokada obejmuje **każdy** endpoint, nie tylko wyszukiwarkę.

### Wyłącznik istniał i nie działał

`_SOFA_ZABLOKOWANY` powstał 30.08 dokładnie po to, żeby po pierwszym 403 nie
uruchamiać przeglądarki dla kolejnych drużyn. Trafił jednak **wyłącznie** do
`pobierz_forme` (jedna drużyna), a potok dzienny woła `pobierz_forme_meczu`
(`daily_phases:175`, `analyzer_helpers:93`) — i ta funkcja wyłącznika nie
czytała.

Koszt: KROK 2 dla 4 meczów to 8 blokad i **39.7 s** w przebiegu z 07.09. Przez
14 dni każdy przebieg trwał od 30 do 63 s dłużej za zero danych.

To ten sam kształt błędu co „reguła singla żyjąca w czterech kopiach": jedna
zasada w dwóch miejscach, poprawka w jednym.

### Naprawa

Wyłącznik w `pobierz_forme_meczu`, w obu funkcjach otwierających własną sesję
(`find_team_id`, `get_form_sofascore`) oraz **między gospodarzem a gościem** —
bez tego ostatniego każdy mecz kosztowałby dwa pewne 403 zamiast jednego.

Strażnik `test_kazde_wejscie_sprawdza_wylacznik` sam wylicza wejścia z kodu, więc
piąte też złapie. Kluczowe zawężenie: markerem jest **wywołanie SofaScore**
(`_sofa_fetch`, `find_team_id`, `get_form_sofascore`), a nie `_sofa_session` —
ta ostatnia mimo nazwy jest generyczną fabryką przeglądarki i używa jej także
`get_form_flashscore`, czyli **fallback**. Wyłączenie go razem z SofaScore
odcięłoby jedyne działające źródło formy. Pierwsza wersja strażnika ten błąd
popełniła i test go pokazał.

Wyłącznik zostaje flagą procesu: każdy przebieg próbuje raz, więc odblokowanie
po stronie SofaScore odzyskamy sami.

## 2. Understat — HTTP 200 i pusta strona

`refresh_players.py --understat` zwracał `0 graczy` po cichu (`if not rows:
continue`). Przyczyna:

```
GET https://understat.com/league/EPL/2026  ->  200, 4684 bajty, bez playersData
GET https://understat.com/league/EPL/2025  ->  200, 4684 bajty, bez playersData
```

Fallback na Playwright też nic nie znajduje. Źródło padło **po** zebraniu
obecnych danych (sezon 2025 w bazie ma pełne składy właśnie stamtąd), więc dziś
nie ma czym odświeżyć składów — patrz `goal_share_zmyslony_2026-09-07.md`.

## 3. football-data.co.uk — HTTP 503 na całej witrynie

```
mmz4281/2627/E0.csv   503    mmz4281/2526/E0.csv   503    englandm.php   503
```

Także strony HTML, więc to awaria serwisu, nie blokada na nas. Może być
przejściowa — serwis działa od lat.

**Konsekwencja:** naprawiony tego dnia tor CLV (patrz `clv_martwy_2026-09-07.md`)
nie dał się zweryfikować na danych. Pierwszy realny pomiar CLV zależy od
powrotu tego źródła.

**Znaleziony przy okazji koszt:** `_pobierz_csv` zapisuje do cache plikowego
wyłącznie **udane** pobranie, więc przy martwym hoście każde wywołanie znów
wychodzi do sieci (zmierzone 11.9 s i 7.5 s na dwa kolejne). `kursy_zamkniecia`
iteruje 13 lig, a CLV liczy się teraz per noga — czyli 30 nóg dałoby 390 zapytań
z timeoutem 15 s. Naprawione `lru_cache` na `_csv_ligi`.

## 4. CD wdrażał bez zielonego CI

`ci.yml`, `cd.yml` i `cd-jobs.yml` to trzy osobne workflow na tym samym
triggerze `push: branches: [main]`. Żaden CD nie miał `needs:` ani
`workflow_run` — bo GitHub Actions **nie ma jak** wyrazić `needs:` między
workflow. Czerwona suita wdrażała się tak samo jak zielona.

Jedyną kontrolą przed podmianą obrazu jobów był smoke-import, który łapie błąd
importu, nie błąd logiki. A ten projekt zapłacił już za wdrożenie złego
artefaktu: 30.07-02.08 pipeline stał **trzy dni** na uszkodzonym obrazie przy
`exit=0`.

Bramka pyta `gh run list --workflow CI --commit $GITHUB_SHA` i czeka do 20 minut.
Trzy stany kończą się odmową: CI czerwone, brak przebiegu CI, przekroczony czas.
Bramka, która przy braku odpowiedzi przepuszcza, byłaby gorsza niż jej brak —
wyglądałaby na kontrolę i nią nie była.

`workflow_dispatch` omija ją świadomie: ręczne wdrożenie to furtka awaryjna
(rollback), a dla ręcznego przebiegu CI może w ogóle nie być. Furtka jest jawna
i zawężona — pilnuje tego `test_reczne_wdrozenie_omija_bramke_swiadomie`.

**Pierwsza realna weryfikacja bramki nastąpi przy najbliższym pushu na `main`.**
Testy sprawdzają kształt YAML-a, nie zachowanie GitHuba.

## 5. RAG semantyczny — sprostowanie

Pierwsza wersja tego audytu nazwała brak `sentence-transformers` w obrazie
awarią. **To była decyzja**, udokumentowana 09.08 przy `except ImportError`
w `rag.retrieve_relevant_lessons`: torch ciągnie gigabajty i zimny start Cloud
Run dla ~150 krótkich lekcji. Pętla zwrotna działa — `analyzer.py` schodzi na
`pobierz_ostatnie_wnioski(3)`. Brakuje wyłącznie wyszukiwania semantycznego.

Uzasadnienie przeniesione do nagłówka `ai/rag_embeddings.py`, czyli tam, gdzie
się go szuka, i dopisane do CLAUDE.md.

Gdyby wracać do tematu: zastrzeżenie dotyczyło torcha, a `scikit-learn` **jest
już** w `requirements-jobs.lock`, więc TF-IDF liczony w pamięci kosztuje zero
megabajtów obrazu. Ale najpierw trzeba naprawić zapytanie: `analyzer.py` buduje
je jako `f"Liga: {ligi} | Markety: {markety}"` — same nazwy lig i etykiety
kuponów, bez drużyn i typu. Lekcje to eseje o konkretnych meczach, więc przy
takim zapytaniu każde wyszukiwanie dopasowuje głównie nazwę ligi. Sam embedder
tego nie naprawi.
