# Changelog

> Archiwum ukończonych prac (przeniesione z TODO.md przez `footstats-scribe`).
> Aktywne zadania: `TODO.md`. Pełna historia commitów: `git log`.

## Wcześniejsze (bez daty w opisie)

- [x] **J1 — Agregat statystyk usera** ✅ `core/user_stats.py` read-only (ROI/win-rate/profit-PLN/streak/best-worst). 25 testów. `get_user_stats`+`get_progress_series`. (per-liga POMINIĘTE — legi niespójne między źródłami.)

- [x] **J2 — GUI Profil/Statystyki** ✅ `GET /api/stats/me` + `StatsView.jsx` (win-rate/ROI/profit/streak/best-worst). Etykiety PLN + disclaimer "papierowy bankroll, nie prawdziwe pieniądze". Playwright PASS.

- [x] **J3 — Krzywa postępu** ✅ `get_progress_series` + `GET /api/stats/progress` + `ProgressChart.jsx` (recharts, profit indigo / win-rate pink). Data = `created_at` (schemat bez `settled_at`). Playwright PASS.

- [x] **J4 — Ręczny wpis kuponu** ✅ kolumna `bookmaker` (migracja 9→Supabase deploy) + `POST /api/coupon/manual` (free-form, ACTIVE, bankroll-neutral) + `PATCH /api/coupon/{id}/result` (owner-check, CAS, guard `kupon_type=='manual'`) + `ManualCouponForm.jsx` + WON/LOST/VOID w `HistoryCouponRow`. **Manual WYKLUCZONY z auto-settle** (hybryda: co mamy=my, reszta=user ręcznie). Playwright PASS.

- [x] **J5 — Leaderboard v2** ✅ `GET /leaderboard` + ROI/profit/win-rate + `sort` (win_rate/roi/profit, nieznany→400) + filtr czasu `days` (cache vary_by) + `LeaderboardView` v2 (selektory, design-system inline-token, disclaimer PLN). Liga/sezon POMINIĘTE (legi niespójne). **Ranking = shared-only (opt-in); statystyki osobiste = WSZYSTKIE kupony (decyzja 2026-07-21).** Playwright PASS.

- [x] **J6 — Predykcja jako sygnał w dzienniku** ✅ `POST /api/coupon/preview-signal` + podgląd "Nasz typ @conf%" w `ManualCouponForm` (indigo zgoda / pink rozjazd / muted brak typu). Kalibracja OFF → pewność=model (przepływa przez `calibrate_confidence` gdy włączą). Playwright PASS.

- [x] **A — `core/match_linker.py`** ✅ `link_leg(home,away,date)` STRICT `_norm_ascii` (NIE `normalize_team_name` — ono koliduje City==United!). Konserwatywny: exact-only, swap/ambiguous/pusta-norma → brak matchu. 11 testów. Ograniczenie: `ł` daje false-negative (bezpieczne).

- [x] **C — J4c `settle_manual_coupons`** ✅ auto-settle nóg manual TYLKO gdy match+nasz `actual_result`; all-legs-or-nothing; ZERO zewn. API; CAS-guard; bankroll-neutralny; guard pustych nóg. `POST /cron/settle-manual` (X-Cron-Secret, **NIE wpięty w scheduler**). reviewer APPROVED + data-guard GREEN. 13 testów.
  - ⏳ **Decyzja usera:** enablement `/cron/settle-manual` — dodać do Cloud Scheduler (dry-run first) czy manualny trigger?
  - Follow-up (opcj.): aliasy PSG/Man City (kontrolowana lista), per-leg result w legs_json dla UI.

- [x] ~~**Parquet na cloud**~~ ✅ w obrazie (`Dockerfile.jobs` + `Dockerfile.api`).

- [x] ✅ Model → `openai/gpt-oss-120b`. ⚠️ **Korekta w trakcie:** najpierw ustawiłem
  `gpt-oss-20b` po teście na uproszczonym prompcie; na realnym okazał się niestabilny
  (top3 = 1, 1, **0**; przy `reasoning_effort=medium` spalił 3750 tokenów na rozumowanie
  i nie zwrócił nic). 120b: top3=3, po polsku, ~1550 tokenów.

- [x] ✅ `reasoning_effort: low` dla rodziny gpt-oss — model płaci za myślenie z tego
  samego budżetu wyjścia (330/400 tokenów przy domyślnym wysiłku).

- [x] ✅ **`GROQ_MODEL` ustawiony JAWNIE** na obu jobach i na API. To była przyczyna
  źródłowa: nazwa modelu żyła wyłącznie jako wartość domyślna w kodzie, a lokalny `.env`
  wskazywał już co innego niż produkcja.

- [x] ✅ Alarm o zaległościach wykluczał porzucone (97 → 48) — palił się wiecznie
  i **zagłuszył prawdziwą awarię**.

## 2026-08-23

- [x] ✅ **A1 — ZROBIONE 23.08.** Zapis predykcji odcięty od odpowiedzi LLM-a.
  Typy powstają z modelu (Poisson/ensemble) niezależnie od tego, czy Groq
  cokolwiek zwrócił — to była najgroźniejsza pojedyncza zależność w potoku
  i przyczyna obu awarii (15.08 zepsuty JSON, 16-22.08 wycofany model).
  - **Zatkane były TRZY dziury, nie jedna** — wszystkie kończyły się zerem predykcji:
    1. odpowiedź nie do sparsowania → `top3` nie istniało (15.08),
    2. `top3` puste mimo poprawnego JSON-a (Groq nie znajdował nic powyżej progu),
    3. do analizy w ogóle nie dochodziło — brak `GROQ_API_KEY` kończył przebieg
       przez `sys.exit(1)`, a wyjątek transportowy (404/413/timeout) zwracał `{}`
       mimo komunikatu „przebieg degraduje do części modelowej".
  - **Selekcja awaryjna to `najlepszy_typ()`** z paper-tradingu System — CELOWO nie
    nowy algorytm. Typ zapisany bez LLM-a jest tym samym typem, który system i tak
    by postawił, a nie trzecim wariantem selekcji do osobnego pomiaru. Dziedziczy
    jego filtry (próg `SELECTION_MIN_CONF`, kurs 1.2–4.0) i jego znaną stronniczość
    ku rynkom 2-way — awaryjna ścieżka nie jest miejscem na jej naprawę.
  - **Rozpoznawalne w bazie:** `kupon_type='model'` + `prompt_version='model_bez_llm'`.
    Bez tego nie dałoby się zmierzyć, czy typy bez warstwy opisowej zachowują się
    inaczej. Reszta potoku (weryfikacja kursów w KROKU 4, uzgodnienie, Kelly,
    decision score) działa na nich bez zmian — wchodzą tym samym `top3`.
  - **Cisza dalej bywa poprawna:** gdy żaden mecz nie ma kursu albo wszystkie
    odpadają na filtrach, nie zapisujemy nic i logujemy ERROR. Nie wymyślamy typu
    na siłę tylko po to, żeby dzień nie był pusty.
  - **Przy okazji zamknięte ostatnie ciche miejsce w ścieżce zapisu:** `save_prediction`
    było owinięte w `except Exception: pass` z komentarzem „optional telemetry".
    `predictions` to nie telemetria — to jedyny zapis tego, co system wytypował.
    Awaria zapisu nadal nie przerywa przebiegu (kolejne nogi mają się zapisać),
    ale trafia do logu jako ERROR zamiast znikać.
  - Odwracalne bez redeploya: `TYPY_BEZ_LLM=0`. +27 testów (`tests/test_typy_bez_llm.py`),
    w tym przejście typu przez KROK 4 (weryfikacja kursów) i uzgodnienie z bazą.
  - `.env.example` miał dalej `GROQ_MODEL=llama-3.1-8b-instant` — model wycofany
    przez Groqa 16.08. Poprawione na `openai/gpt-oss-120b`.

- [x] ✅ **Fałszywy alarm „ZERO predykcji zapisanych". ZROBIONE 23.08.**
  Alarm krzyknął o zerze, gdy w bazie leżało 5 wierszy.
  - **Mechanizm:** `ma_typy` czytało `dane["top3"]` **PO** weryfikacji kursów (KROK 4),
    a zapis dzieje się **PRZED** nią (KROK 3). Groq wytypował trzy rynki, których źródło
    nie wycenia (`Over 1.5`, `Handicap +1 Gość`, `2 (wygrana gościa)`) → weryfikacja
    słusznie wycięła komplet → `top3` puste → alarm uznał to za dzień bez predykcji.
  - ⚠️ **Moja wpadka z tej samej sesji:** treść komunikatu zmieniona rano na
    „selekcja modelu nic nie wybrała" jest w tym scenariuszu **myląca**. Założyłem, że
    po A1 pusty `top3` może już oznaczać tylko porażkę selekcji modelu — nie przewidziałem
    trzeciej drogi: LLM odpowiada → A1 nie wchodzi → weryfikacja czyści.
  - **Fix:** `_auto_zapisz_backtest` liczy wiersze, które NAPRAWDĘ poszły do bazy
    (`dane["_zapisanych"]`), i to jest teraz `ma_typy`. Komplet wycięty przez weryfikację
    dostał **własny, inaczej nazwany sygnał** — bo to nie cisza (predykcje są), ale też
    nie zdrowy dzień (zero typów do postawienia). +11 testów.

- [x] ✅ **Dzienna wiadomość na Telegram nie doszła. ZROBIONE 23.08.**
  `HTTP 400 — can't parse entities: Unsupported start tag "1.20."` — pole `ostrzezenia`
  szło do wiadomości **surowe**, jako jedyne (nazwy drużyn i typy przechodzą przez `_esc`).
  Tekst zawierał `<1.20).`, Telegram w trybie HTML uznał `<` za początek tagu i odrzucił
  CAŁOŚĆ. To ta sama awaria, którą `_esc` opisuje w swoim docstringu dla nazw drużyn (06-22)
  — jedno pole zostało pominięte.
  - **Fix dwuwarstwowy:** `_esc` na ostrzeżeniach + **jedno ponowienie bez formatowania**
    po odmowie parsera. Escapujemy każde pole, ale wystarczy jedno przeoczone, żeby
    wiadomość przepadła; brzydsza wiadomość jest lepsza niż cisza. Ponowienie tylko dla
    błędu PARSERA — blokada bota czy zły chat_id nie naprawią się powtórką. +6 testów.

- [x] ✅ **A2 + A3 — ZROBIONE 23.08. Zapis przeniesiony ZA weryfikację.**
  Oba znaleziska miały jeden korzeń: zapis szedł w KROKU 3, weryfikacja w KROKU 4.
  - **A2** — `2 (wygrana gościa)` to zwykła „2" z dopiskiem od Groqa, ale
    `oblicz_tip_correct` zwraca dla niej `None`: wiersz martwy od chwili zapisu.
    Słownictwo LLM-a lądowało w bazie nietknięte.
  - **A3** — noga, która nie przeżyła weryfikacji, zostawała z kursem od Groqa
    (`odds_verified=0`); uzgodnienie z KROKU 4b poprawia tylko ocalałe.
  - **Fix:** potok dzienny NIE zapisuje w KROKU 3 (`zapisz_predykcje=False`), tylko
    w nowym KROKU 4a, po weryfikacji. Weryfikacja jest przy okazji **bramką
    słownikową** — przepuszcza wyłącznie rynki z `_TYP_DO_ODDS_KEY`, czyli te, które
    źródło wycenia i które rozliczenie umie policzyć. Do bazy trafia więc tylko to,
    co system naprawdę wystawił, z prawdziwym kursem.
  - **A1 dostał drugą szansę.** Skoro typy LLM-a mogą wyparować dopiero na
    weryfikacji, model wchodzi PO niej. Bez tego dzień, w którym Groq wytypował same
    rynki bez kursu (dokładnie 23.08), kończyłby się zerem predykcji mimo gotowych
    liczb modelu. Typy z modelu przechodzą tę samą bramkę — nie są z niej zwolnione.
  - `cli_commands` nie ma kroku weryfikacji, więc dla niego zapis w analizie
    zostaje domyślnie włączony. `_uzgodnij_predykcje` zmienia rolę z naprawy kursu
    na domknięcie: stawia `odds_verified` i pilnuje rozjazdu nazw.
  - Bramka ogólna w testach: **cokolwiek wejdzie do bazy, musi mieć rozstrzygnięcie**
    przy jakimkolwiek wyniku meczu. +12 testów.
  - Sprawdzone przy okazji i **czyste**: `Handicap +1 Gość` to wspierany rynek z reguł
    BetBuilder ([betting.py:241](src/footstats/utils/betting.py#L241)) i liczy się poprawnie.

- [x] ✅ **F6 — ZROBIONE 23.08.** Baner zasłaniał link „Masz już konto? Zaloguj się" na mobile.
  - **Zmierzone w przeglądarce, nie na oko** (390px, widok rejestracji): dół linku na 703px,
    góra banera na 648px → **zasłonięty o 55px**. Po fiksie dół linku na 507px, czysto.
  - **Przyczyna:** baner jest `fixed bottom-0`, więc nie zajmuje miejsca w układzie.
    Na 390px rozwija się do dwóch wierszy (196px wysokości) i przykrywa to, co najniżej.
  - **Fix celowo GLOBALNY, nie lokalny:** baner wisi nad KAŻDYM ekranem, więc margines
    dorzucony w widoku rejestracji załatwiłby jeden i zostawił resztę. Rezerwujemy na dole
    strony tyle, ile baner realnie zajmuje, i oddajemy po zamknięciu. Wysokość mierzona,
    bo zależy od szerokości ekranu — potwierdzone: 196px przy 390px, 124px przy 1440px,
    przeliczane przy zmianie rozmiaru okna.
  - **Cykl sprawdzony w przeglądarce:** baner widoczny → miejsce zarezerwowane; zgoda →
    baner znika, miejsce oddane (`padding-bottom` czyszczony). Desktop 1440 bez regresji.
  - `ResizeObserver` nie istnieje w jsdom ani w starszych przeglądarkach — wtedy zostaje
    sam nasłuch `resize`. +4 testy (front: 38 → 42).

- [x] ✅ **B2 — ZROBIONE 23.08. Potwierdzone jako FAKT i naprawione.**
  - **Dowód bez sondowania produkcji:** logi dostępowe uvicorna pokazują adres,
    który widzi aplikacja. 36 kolejnych żądań z zupełnie różnych źródeł (Cloud
    Scheduler, curl z sieci domowej, sondy zdrowia) → **wszystkie `169.254.169.126`**,
    czyli link-local pośrednika Cloud Run. Odpowiedź leżała w logach, które już
    mieliśmy — nie trzeba było testu z dwóch sieci.
  - **Skutek gorszy niż mówił opis:** to nie tylko brak ochrony. Jedno wspólne wiadro
    znaczy, że **dowolny klient mógł wyczerpać limit logowania (10/min) i odciąć
    wszystkich pozostałych**. Mechanizm chroniący dostępność sam ją psuł.
  - **Fix:** `klucz_klienta()` bierze **OSTATNI** wpis `X-Forwarded-For`, nie pierwszy.
    Klient może wysłać własny nagłówek — Cloud Run go zachowa i dopisze na końcu
    adres, z którego faktycznie przyszło połączenie. Pierwszy wpis czyniłby limit
    trywialnie omijalnym (wystarczy losować nagłówek). Test to pilnuje wprost.
  - **Założenie zapisane w kodzie:** usługa stoi bezpośrednio na `run.app`, bez
    własnego load balancera. Gdyby kiedyś stanął przed nią LB, ostatnim wpisem
    byłby JEGO adres i decyzję trzeba przeliczyć.
  - +10 testów. **B7 (blokada konta) zmienia wagę:** limit per-IP znowu realnie
    działa, więc blokada konta przestaje być jedyną obroną.

- [x] ✅ **B3 — ZROBIONE 23.08. python-jose → PyJWT, `--ignore-vuln` zdjęte.**
  - **Zmierzone:** `python-jose`, `ecdsa`, `rsa`, `pyasn1` wypadły z obu locków;
    `pip-audit` **bez żadnych wyciszeń** → `No known vulnerabilities found`.
  - **Zakres mniejszy niż się wydawał:** kod produkcyjny wołał `jose` w **jednym**
    pliku (`api/auth.py`), a PyJWT był już w obrazie jako zależność przechodnia —
    podmiana niczego nie dokłada, tylko zdejmuje.
  - **Największe ryzyko było w zgodności, nie w kodzie:** gdyby tokeny wystawione
    starą biblioteką nie weryfikowały się nową, samo wdrożenie **wylogowałoby
    wszystkich zalogowanych**. Test wystawia token dokładnie tak jak `python-jose`
    i czyta go przez PyJWT — przeszedł, zanim tknąłem zależności. Pomija się sam,
    gdy `jose` zniknie ze środowiska, bo pilnował momentu przejścia.
  - **Odrzucenia zachowane:** obcy podpis, wygasły token, `alg: none`, śmieć —
    każde nadal jest odrzuceniem. `PyJWTError` zastąpiło `JWTError` jako wspólna
    klasa, inaczej część odrzuceń leciałaby jako 500 zamiast 401.
  - **Pułapka złapana przez istniejący test:** `import jwt` pochodzi z paczki `pyjwt`,
    ale na PyPI istnieje TEŻ osobna, niepowiązana paczka o nazwie `jwt`. Bez
    mapowania obraz wciągnąłby cudzy projekt. Dopisane do `test_dependencies_declared`.
  - Strażnik pilnuje, żeby `--ignore-vuln` nie wróciło do CI bez daty i powodu. +10 testów.

- [x] ✅ **B4 — ZROBIONE 23.08. Zależności przypięte lockiem.**
  - **Korekta opisu:** `requirements.txt` (26 pozycji, 0 przypiętych) **nie jest używany
    przez obrazy** — to lustro dla skanera CVE w CI. Obrazy instalowały
    `.[api,ai,scraper]` prosto z `pyproject.toml`, czyli z zakresów `>=`.
  - **Realne ryzyko:** dwa buildy tego samego commita mogły dostać różne wersje,
    a nowa wersja z góry wchodziła na produkcję po cichu. Ta sama rodzina awarii
    co wycofany model Groqa: zmiana po stronie kogoś innego, niewidoczna aż do skutku.
  - **Fix:** `requirements-jobs.lock` (85 przypiętych) i `requirements-api.lock` (65),
    generowane **na platformę kontenera**, nie hosta — lock z Windowsa opisywałby
    inne zależności warunkowe. Obrazy instalują `-r <lock>` + sam pakiet `--no-deps`.
  - **Smoke-import w buildzie:** przy `--no-deps` brakująca paczka wychodzi dopiero
    przy imporcie, czyli na produkcji. Nowy krok w `cloudbuild_jobs.yaml` importuje
    ciężkie warstwy zaraz po zbudowaniu — przesuwa wykrycie do buildu.
  - **Zweryfikowane realnym buildem** (nie tylko testem): obraz buduje się i przechodzi
    smoke-import. API ma to od dawna w CI (`docker run` + `/health`).
  - `tests/test_lockfile_zgodny.py` pilnuje, żeby lock nie zdryfował od `pyproject`,
    żeby nie było w nim luźnych zakresów i żeby był zbudowany dla linuxa. +7 testów.

- [x] ✅ **B9 — ZROBIONE 23.08. Trzy listy zależności → dwie.** `requirements.txt`
  usunięty, `pip-audit` w CI czyta teraz oba locki (`-r requirements-api.lock
  -r requirements-jobs.lock`), czyli dokładnie to, co instalują obrazy.
  **HIPOTEZA SIĘ NIE POTWIERDZIŁA — zmierzone przed zmianą:** podejrzenie było takie,
  że `pip-audit` rozwiązuje zakresy `>=` do nowszych wersji niż te w obrazie. Porównanie
  zbiorów dało **83 pakiety w obu wypadkach, zero różnic w nazwach, zero w wersjach**
  (to samo dla `requirements-api.lock`, 63 pakiety). **Żadnej dziury nie było.**
  Zmiana broni się czym innym: ta zgodność to własność ŚWIEŻOŚCI locka, nie projektu —
  locki są przypięte celowo, a zakresy `>=` dryfują ku nowszym wydaniom, więc z czasem
  skan zacząłby dotyczyć wersji, których nikt nie uruchamia. Lustro było w dodatku
  przepisywane ręcznie i raz już zdryfowało (wypadły `beautifulsoup4`, `psycopg2-binary`,
  `sentry-sdk`, `langfuse`, `tenacity`). +6 testów — strażnik pilnuje NIEZMIENNIKA
  („CI skanuje dokładnie te listy, z których instalują obrazy"), nie nazw plików,
  więc przetrwa dołożenie trzeciego obrazu. Skasowany `test_requirements_odwzorowuje_
  obraz_produkcyjny` zastąpiony przez `test_lockfile_zgodny` + nowy strażnik.

- [x] ✅ **D6 — ZROBIONE 23.08. Pytaliśmy źródła o daty, których z definicji nie oddadzą.**
  Wyszło przy rozpoznaniu D5. Ślad z produkcji (`/api/cron/settle`, 06:00):
  `{'settled': 0, 'partial': 21}` + `Free plans do not have access to this date,
  try from 2026-08-22 to 2026-08-24` + `flashscore.mobi: offset -8`.
  - **Oba źródła mają horyzont wstecz:** darmowy plan API-Football to okno `dziś ±1 dzień`,
    `flashscore.mobi` ~7 dni. FlashScore **sam się pilnuje od początku**; API-Football
    progu nie miał, więc przy każdym z dwóch dziennych przebiegów pytaliśmy o daty
    skazane na odmowę: 21 kuponów × 2 daty (mecz i mecz+1) × 2 przebiegi.
  - **Gorsze:** `coupon_settlement` miał WŁASNĄ kopię tego zapytania, wołaną surowym
    `requests.get` z pominięciem licznika budżetu — zużycie limitu z tej ścieżki było
    dla nas **niewidoczne**. Kopia usunięta, deleguje do wspólnej, strzeżonej funkcji.
  - **Fix:** `data_w_zasiegu_af()` + próg `AF_HORYZONT_DNI` (default 1, env-strojony —
    płatny plan nie ma tego ograniczenia).
  - ⚠️ **Pierwsze wdrożenie NIE naprawiło problemu, mimo zielonej suity.** Przebieg
    rozliczenia dalej zbierał 19 odmów. `_find_leg_result` ma **PIĘĆ** źródeł wyników,
    nie dwa — Źródło 5 (agregator multi-source) idzie do tego samego API osobną drogą,
    przez `af_source` do klienta budżetowego. Potem znalazły się jeszcze dwa wejścia.
    Zamiast szukać szóstego po kolejnym wdrożeniu: test przechodzi po plikach
    źródłowych i wymaga progu przy każdym zapytaniu o `/fixtures` z parametrem `date`
    (trzy miejsca wyłączone świadomie — pytają tylko o dziś/jutro).
  - **Zmierzone na produkcji, ten sam przebieg przed i po:**

    | | przed | po |
    |---|---|---|
    | odmowy z API-Football | 19 | **0** |
    | zapytania pominięte przez próg | 0 | **45** |

    45 × 2 przebiegi = **90 ze 100 dziennego limitu odzyskane**. Uwaga: „19" to tylko
    tyle, ile było WIDAĆ — dwa z pięciu wejść nie logowały nic, więc realne zużycie
    było wyższe i niewidoczne.
  - **Koszt uboczny:** próg uzależnia zachowanie od „dziś", więc 8 testów w 4 plikach
    z zaszytą datą stało się kruche. Część **przechodziła z niewłaściwego powodu** —
    oczekiwały pustej listy po błędzie sieci, a dostawały ją z progu. To groźniejsze
    niż jawna porażka, bo wygląda jak zieleń. Wszystkie przestawione na daty względne.
  - **Wniosek, który zostaje:** zielona suita mówiła „naprawione", gdy problem był
    ruszony w jednej piątej. Wykrycie wymagało pomiaru na żywym przebiegu. +17 testów.
  - ⚠️ **Korekta mojej atrybucji w trakcie:** linie `Budzet AF 42/100` NIE pochodziły
    z rozliczania — to licznik klienta `api_football.py`, którego na tej ścieżce nie ma.
    To był równoległy cron w tym samym oknie czasowym.

- [x] ✅ **D8 — ZROBIONE 23.08. Alarm o stojącym rozliczaniu.** Osiem dni
  `settled: 0` przy 20+ kuponach czekających przeszło bez sygnału; skutek zauważył
  dopiero `pipeline-health`, i to pośrednio (`26 predykcji bez rozliczenia`).
  - **Warunek CELOWO nie brzmi „rozliczono 0 przy niepustej kolejce".** Dziś to
    prawda i będzie prawdą codziennie, bo w kolejce siedzą kupony poza horyzontem
    źródeł. Taki alarm wyłby bez powodu — czyli powtórzyłby dokładnie błąd
    naprawiany rano tego samego dnia, gdzie alarm o „ZERO predykcji" palił się
    wiecznie i przez to przestał cokolwiek znaczyć.
  - **Właściwy warunek:** rozliczono 0, **choć coś czekającego jest jeszcze
    w zasięgu** (`HORYZONT_ZRODEL_DNI = 7`, najdłużej sięgające źródło). 16.08
    alarm by się zapalił (kupony jednodniowe), dziś milczy (wszystko 8-9 dni) —
    bo milczenie jest wtedy poprawną odpowiedzią, nic się już nie da zrobić.
  - `settle_active_coupons` liczy `czekajace_w_zasiegu` osobno od `partial`.
    Alarm wychodzi z `/cron/settle`, ERROR do logu + Telegram; padnięty Telegram
    nie wywala crona. +15 testów.

- [x] ✅ **I1 — ZROBIONE 23.08. Joby mają CD.** Nowy `.github/workflows/cd-jobs.yml`:
  build `Dockerfile.jobs` → smoke-import → przypięcie obu jobów do digestu → weryfikacja
  stanu faktycznego. **`provenance: false` gasi pułapkę u źródła** — BuildKit przestaje
  tworzyć wpisy atestacji BEZ TAGU, czyli nie ma już czego pomylić z obrazem
  (to one zatrzymały pipeline 30.07–02.08). Tag wyłącznie immutable SHA, nigdy `:latest`
  (awaria 29.07). Osobny plik od `cd.yml`, bo chromium buduje się kilkanaście minut
  i nie ma blokować wdrożeń API.
  **Świadoma zmiana wcześniejszej decyzji:** `cloudbuild_jobs.yaml` mówił „podmiana
  obrazu ma być OSOBNĄ decyzją" — słuszne wobec awarii 29.07, gdzie obraz podmieniał
  się PRZYPADKIEM, ale deterministyczne wdrożenie z merge'a to co innego. **Koszt
  zostaje:** każdy merge na `main` zmienia teraz produkcyjny pipeline — dlatego
  smoke-import stoi PRZED podmianą. Ręczny `cloudbuild_jobs.yaml` został jako droga
  awaryjna. +9 testów (`tests/test_cd_joby.py`), w tym strażnik kolejności smoke↔podmiana.

- [x] ✅ **B5 — ZROBIONE 23.08. Content-Security-Policy w trybie raportowania.**
  Polityka domyka `default-src`/`object-src`/`base-uri`/`frame-ancestors`/`form-action`,
  `script-src 'self'` BEZ `'unsafe-inline'` (zbudowany pakiet nie ma ani jednego skryptu
  inline — sprawdzone w `dist/index.html`). Google Fonts jako jedyne zewnętrzne
  pochodzenie. Flip przez `CSP_ENFORCE=1` **bez wdrażania nowego obrazu** — moment,
  w którym trzeba wycofać złą politykę, to dokładnie ten, w którym nie chcemy czekać
  na build. +16 testów.
  **ZMIERZONE, nie zgadnięte:** lokalnie przy `CSP_ENFORCE=1` Playwright załadował
  `/`, `/preview`, `/app` i `/polityka-prywatnosci` — **zero naruszeń CSP, zero błędów
  konsoli**, font `Inter` aktywny. Zastrzeżenie: to ekran logowania (brak bazy lokalnie),
  więc widoki po zalogowaniu (wykresy `recharts`) NIE są przetestowane — dlatego
  domyślnie zostaje raportowanie.
  **Dług świadomy:** `style-src 'unsafe-inline'` jest konieczne, bo front używa
  atrybutów `style={{...}}` (**to samo miejsce co F9**). Dopóki tam jest, `style-src`
  realnie nie broni przed wstrzyknięciem stylu. Sprzątnięcie F9 pozwoli go usunąć —
  `test_style_inline_dozwolone_swiadomie` spadnie wtedy i o tym przypomni.

- [x] ✅ **B7 — ZROBIONE 23.08. Blokada konta po serii błędnych haseł.**
  Migracja 15 (`failed_attempts`, `locked_until`) w obu dialektach.
  - **Decyzja 1 — zablokowane konto NIE SPRAWDZA HASŁA** i odpowiada identycznie jak
    przy złym haśle. Kuszące jest powiedzieć „konto zablokowane", ale żeby wiedzieć,
    komu to powiedzieć, trzeba najpierw zweryfikować hasło — a to odtwarza wyrocznię:
    napastnik dalej testuje hasła, tylko wolniej, i poznaje trafione po treści
    odpowiedzi. **Blokada, która sprawdza hasło, nie jest blokadą.** Test pilnuje
    też KOLEJNOŚCI w kodzie, bo tu kolejność jest bezpieczeństwem, nie stylem.
  - **Decyzja 2 — okno rośnie wykładniczo (1 → 15 min), nie jest trwałe.** Stałe okno
    daje napastnikowi stałą przepustowość; trwała blokada zamienia lukę na inną —
    znając czyjś login, można go zamknąć na stałe. **Koszt zostaje i jest świadomy:**
    napastnik nadal potrafi komuś utrudnić logowanie.
  - Licznik zeruje się po udanym logowaniu — bez tego konto zamyka się po kilku
    pomyłkach rozłożonych na tygodnie. Awaria zapisu licznika **nie blokuje logowania**.
  - **Test-strażnik zadziałał:** `test_BRAK_blokady_konta_po_serii_bledow` był celowo
    zielony wobec luki i padł w dniu naprawy, wymuszając aktualizację audytu. Przepisany
    na opis nowego stanu. Ten sam mechanizm zadziałał 17.08 przy B1. +16 testów.

## 2026-08-17

- [x] ✅ **D1 — dogrywka/karne. ZROBIONE 17.08.** ⚠️ **KOREKTA pierwotnego znaleziska:** napisałem „kupon stoi ACTIVE NA ZAWSZE" — **nieprawda**. Jest siatka `VOID_AFTER_DAYS=10` ([coupon_settlement.py:346](src/footstats/core/coupon_settlement.py#L346)) i działa: **zero** kuponów ACTIVE starszych niż 10 dni na produkcji.
  - **Realna szkoda była subtelniejsza i częściowo GORSZA.** Zachowanie zależało od ZAPISU źródła: `2-1aet` → `None` (10 dni limbo → VOID bez wyjaśnienia), ale `2-1 (AET)` → **rozliczane jako wygrana gospodarza**. Ten sam mecz, dwa werdykty. Druga ścieżka to **ciche BŁĘDNE rozliczenie** — po 90 min mógł być remis.
  - **Dlaczego nie rozliczamy po dogrywce:** rynki 90-minutowe wymagają wyniku regulaminowego, a tego zapisu w danych nie ma. Wnioskowanie „była dogrywka → po 90 remis" jest zawodne (w dwumeczu dogrywkę wymusza remis w DWUMECZU, sam mecz mógł skończyć się 1-0).
  - **Fix:** `powod_nierozliczalny()` rozpoznaje dogrywkę/karne (dopasowanie po całych słowach — „Openda" nie myli); `oblicz_tip_correct` zwraca `None` **z WARNINGIEM** dla obu zapisów; kupon dostaje **VOID od razu z podanym powodem** zamiast 10 dni ciszy. Trzy stare testy kodowały obcinanie sufiksu — przepisane wraz z uzasadnieniem zmiany intencji. +30 testów.

- [x] ✅ **F1 — reset CSS zabijał kolory przycisków. ZROBIONE 17.08.** Bug **udowodniony w przeglądarce** (Playwright, styl wyliczony), nie tylko z lektury pliku:
  - przed: `<button class="text-rose-400">` → `rgb(248,250,252)`, `<button class="bg-emerald-500">` → `rgba(0,0,0,0)`; ten sam `text-rose-400` na `<span>` **działał**
  - po: przycisk i span dają identyczny kolor; przycisk bez klasy dalej dziedziczy i jest przezroczysty; `.btn-primary` dalej wygrywa gradientem (brak regresji)
  - **Zmieniło wygląd 6 przycisków** — wszystkie na lepsze. Najboleśniejsze były niewidoczne: przycisk **rejestracji** (`bg-indigo-500`) był PRZEZROCZYSTY, a **usunięcia konta** (`bg-rose-500`) nie miał czerwieni ostrzegawczej.
  - Zrzuty desktop 1440 + mobile 390 po fiksie: bez regresji. `tests/test_css_warstwy.py` pilnuje warstwy (i tego, że `.btn-primary` ma zostać POZA warstwami — to celowe).

- [x] ✅ **F7 — ZROBIONE 17.08 (wariant A: analityka usunięta).** `<Analytics />` i `<SpeedInsights />` wyjęte z `main.jsx`, zależności `@vercel/*` usunięte z `package.json` + lockfile. Zweryfikowane w przeglądarce po zmianie: **zero** skryptów analityki w DOM. Treść banera („wyłącznie niezbędne") jest teraz prawdziwa. Rewert = jeden commit.

- [x] ✅ **F8 — ZROBIONE 17.08.** Trzy zaszyte na sztywno adresy Cloud Run (baner + dwa linki w stopce) zastąpione helperem `legalUrl()` w `lib/api.js`. **Zweryfikowane, że nie psuje produkcji:** żywy bundle na Vercelu ma `VITE_API_BASE = https://footstats-api-…run.app/api`, a helper wylicza z niego dokładnie ten sam URL, który był zaszyty. Teraz linki dzielą los aplikacji — jeśli `API_BASE` jest zły, i tak nic nie działa.

- [x] ✅ **F2 — pierwsza warstwa dostępności ZROBIONA 17.08.** ⚠️ **KOREKTA audytu:** napisałem „0× `onClick` na `div`/`span`, klikalne są `<button>`, baza jest dobra" i wpisałem to jako **plus**. To było fałszywe trafienie regexa jednolinijkowego — te tagi rozbijają się na wiele linii. **Realnie jest ich sześć.**
  - **Naprawione:** etykiety w `LoginView` nie były powiązane z polami (brak `htmlFor`/`id`) — wizualnie wyglądało dobrze, ale czytnik odczytywał wyłącznie `placeholder`, który znika po pierwszym znaku, a kliknięcie w etykietę nie ustawiało fokusu. Dowód przed fiksem prosto z Testing Library: *„Found a label … however no form control was found associated to that label"*.
  - **Nazwane trzy przyciski z samą ikoną:** zamknięcie formularza kuponu, otwarcie i zamknięcie menu mobilnego. Wcześniej czytnik anonsował je jako „przycisk" i nic więcej. Ikony dostały `aria-hidden`.
  - **Strażnik `src/test/dostepnosc.test.jsx`:** żaden przycisk bez nazwy, każdy obrazek z `alt`, a liczba klikalnych `<div>` ma **tylko spadać** (próg bazowy 6 — wzorem `test_broad_except_audit.py`).

- [x] ✅ **F3 — ZROBIONE 17.08. Front ma pierwsze 29 testów i bramkę w CI.** Vitest + Testing Library + jsdom; `npm test` / `npm run test:watch`; osobny job `frontend` w `ci.yml` (`npm ci --legacy-peer-deps` — ten sam przełącznik co build na Vercelu — plus `npm test` i `npm run build`). Zweryfikowane czystym `npm ci`, tak jak zrobi to CI.
  - **Setup pilnuje izolacji jak `tests-no-prod.md` po stronie backendu:** domyślny `fetch` wybucha z czytelnym komunikatem, więc zapomniany mock widać od razu zamiast cichego strzału w API.
  - Pokryte: `lib/api.js` (`legalUrl`, `decodeJwtPayload` — śmieciowy token nie może wywalić apki białym ekranem), `HistoryCouponRow` (ręczne rozliczanie: widoczne TYLKO dla `manual`+ACTIVE, właściwy endpoint i payload, błąd trafia na ekran, podwójne kliknięcie nie wysyła dwóch rozliczeń, licznik nóg), `CookieConsent`, `main.jsx` (strażnik: analityka nie może wrócić po cichu).
  - Zostaje do pokrycia: `ManualCouponForm`, `CouponWizard`, `StatsView`, `LeaderboardView`.

- [x] ✅ **M1 — ZMIERZONE 17.08. Hipoteza z audytu BŁĘDNA, mechanizm inny i groźniejszy.** Nie chodzi o filtr kursu, tylko o **argmax po surowym prawdopodobieństwie**.
  - Walk-forward, 1755 meczów z 8 lig: selekcja wybiera **Under 2.5 34% · BTTS 28% · Over 2.5 15%** — razem **77% rynki 2-way**; 1X2 tylko 23%, a **remis NIGDY** (`p(X)` nie sięga 50% w żadnym meczu, średnio 23,8%).
  - **Mechanizm:** rynek dwustronny ma zawsze jedną stronę ≥50% z definicji; trzystronny dzieli prawdopodobieństwo na trzy i faworyt ma średnio 44,7%. Najlepszy typ 1X2 = 51,9%, najlepszy 2-way = 60,0%; **2-way wygrywa argmax w 74% meczów**. Selekcja wybiera więc rynek o **najmniejszej liczbie wyników**, nie ten z przewagą.
  - **Skutek uboczny na lewar M1 #1:** progu `SELECTION_MIN_CONF` **nie da się** zastosować do rynku 2-way — jeśli jedna strona jest słaba, druga jest o tyle silna. Próg filtruje wyłącznie 1X2, więc jego podniesienie **jeszcze mocniej** przechyli selekcję ku rynkom golowym.
  - ⚠️ **„Oczywiste" poprawki są GORSZE** (te same dane, realne wyniki, podatek 12%): argmax p (produkcja) **−10,7%** · argmax EV **−13,5%** · argmax przewagi nad rynkiem **−14,7%**. Powód spójny z resztą pomiarów: model przegrywa tam, gdzie rozjeżdża się z rynkiem, a EV selekcjonuje dokładnie ten rozjazd. **Zmiana reguły przetasowuje straty, nie usuwa ich.**
  - Stronniczość przypięta testami (`tests/test_selekcja_stronniczosc_rynkow.py`), żeby nie była odkrywana od nowa co kilka miesięcy.

- [x] ✅ **B1 — ZROBIONE 17.08.** Migracja 14 (`users.token_version`) + claim `tv` w tokenie. Zmiana i reset hasła podbijają wersję → **wszystkie wydane tokeny przestają działać**. Zmieniający hasło dostaje świeży token w odpowiedzi, żeby nie wylogować samego siebie.
  - **Przy okazji domknięta druga luka, której audyt nie zauważył:** `require_auth` **w ogóle nie sprawdzało `is_active`**. Token konta zdezaktywowanego lub zanonimizowanego przechodził strażnika, a odsiew zależał od tego, czy konkretny endpoint sam o to zapyta. Teraz sprawdzane raz, w jednym miejscu.
  - **Własna dziura wprowadzona i zamknięta w trakcie:** pierwsza wersja zwracała `None` zarówno przy awarii bazy, jak i przy braku wiersza — czyli traktowała **usunięte konto jak awarię i wpuszczała jego token**. Rozdzielone: wyjątek → przepuść (fail-open), brak wiersza → odrzuć.
  - **Świadome kompromisy** (oba przypięte testami): brak `tv` = wersja 0, żeby wdrożenie nie wylogowało wszystkich; błąd bazy przepuszcza token, bo podpis jest już zweryfikowany, a przy niedostępnej bazie żaden endpoint i tak nie odda danych.
  - Koszt: jedno zapytanie do bazy na uwierzytelnione żądanie. Próg `except Exception` dla `api/auth.py` podniesiony 2 → 3 z uzasadnieniem.
  - **Zostaje z B1:** token nadal nie jest związany z urządzeniem (brak `jti`), więc skradziona kopia działa do unieważnienia albo wygaśnięcia. Wersja rozwiązuje „odbierz dostęp", nie „wykryj kopię".

## 2026-08-14

- [x] ~~**Backfill Neon → Supabase + rotacja hasła**~~ ✅ **14.08 zamknięte** — backfill był już wykonany, kupony/bankroll/users odpuszczone (decyzja usera), wersja 1 sekretu `DATABASE_URL` z Neonem wyłączona. Zostaje kosmetyka: usunąć `DATABASE_URL_NEON` z lokalnego `.env`.

- [x] ~~**Verify quick_picks-fix → Poisson live**~~ ✅ **13-14.08** — `poisson-dc` gra w OBU ścieżkach (job + draft na API). Escape-hatch bez zmian: `QUICK_PICKS_USE_POISSON_CACHE=0`, ale **uwaga** — ta flaga wyłącza adapter schematu i Poisson odpada po cichu, to nie jest czysty przełącznik modelu.

## 2026-07-19

- [x] ~~**DECYZJA (nie bug):** Bzzoiro etykietuje towarzyskie kadr jako "World Cup 2026" → whitelist MŚ (D1a).~~ **Wygasło 07-20** — MŚ zakończone 19.07; wraca ewentualnie przy Euro/kadrach.

## 2026-07-05

- [x] **Kontuzje v2 — baza graczy + goal_share** (07-05): `core/player_db.py` (SQLite) + `scrapers/player_stats.py`. Wpięte w `_apply_injury_corrections` → kara napastnika ∝ udziałowi w golach. Populacja przez **`scripts/refresh_players.py`** (`--season`, `--only`, `--understat`).
  - **2 źródła:** (1) API-Football `/players/topscorers` (topscorer denominator, mniejsze ligi) — 11 lig; (2) **Understat pełne składy TOP5** (per-gracz gole/asysty/xG) → **prawdziwy denominator** (Salah 34% nie 60%). Stan 07-05: **sezon 2025 (2025-26) PRIMARY = 2775 graczy** (Understat TOP5, najświeższy pełny sezon — pipeline `_current_season`=2026 → walk-back → 2025) + sezon 2024 fallback 2885. **MŚ 2026: 119 graczy** (sezon 2026, liga WC) — Sofascore top-players API (gole/asysty/**rating 1-10**/xG, angielskie kadry) via headless browser; Flashscore strzelcy jako cross-check. goal_share kadr działa (France Mbappé 54%, Brazil Vini 57%, England Kane 71%). `rating`/`xg` = nowe kolumny player_db (`get_team_players`).
  - **Siła kadr (team_stats):** 48 kadr MŚ (Sofascore standings + top-teams) → `team_attack_defense(team,2026)` = (gole/mecz, tracone/mecz) = **Poisson λ dla reprezentacji** (model nie miał historii kadr!). France λ_atk 3.33/def 0.67, Spain 1.67/0.00, Norway 2.67/2.33. + avg_rating 1-10, possession, clean_sheets, big_chances. Tabela `team_stats`.
  - [x] **λ kadr WPIĘTE** (07-05): `core/national_lambda.py` + `_apply_national_lambda` (daily_agent przed roznica_modeli). Mecze reprezentacji (obie w team_stats) → Poisson λ z turnieju BLEND 0.5 z Bzzoiro-ML. Gated: kluby bez zmian (backtest offline niezmieniony). Demo: Portugal-Spain 34/32/34 (Spain 0 straconych), Brazil-Norway 56%+O2.5 74%.
  - **Do wpięcia:** rating 1-10 — brak live data-path (lineup'y WC niedostępne w API-Football, kluby bez ratingu Sofascore); zapisane+wystawione (`get_team_players`), wpięcie gdy pojawi się źródło ratingów składów. Denominator goal_share kadr = top-50 strzelców (kraje z 1 strzelcem → 100%, bounded cap).
  - **Understat wymaga JS-renderu** (od ~2026 nie embeduje `playersData` w HTML → plain-HTTP zwraca []); kolekcja przez headless browser (odczyt `window.playersData`). `parse_understat_players`/bridge działają na wyrenderowanym HTML.
  - **Do dokończenia:** (a) doładować 5 lig API-Football po resecie 429 (MLS/Saudi/LigaMX/Belgia/Szkocja); (b) repeatable Understat fetch przez projektowy Playwright (teraz manual/MCP); (c) normalizacja: `normalize_team_name` zbija "Manchester City"=="United"→"manchester" i "Bayern Munich"≠"München" — kolizje/miss dla części drużyn (bounded cap ±20%); (d) match nazw injury(SofaScore) ↔ goal_share(Understat) — różne pisownie.

- [x] **Faza 2 — siła składu XI** (07-05): `core/lineup_strength.py` — brak topowego strzelca w startXI → λ ataku ↓ (`lineup_lambda_factor`) + kara decision_score (`lineup_confidence_penalty_v2`, zastępuje crude len<11). Wpięte w `_enrichuj_finalna_faza`.

## 2026-08-15

### BTTS dwustronne — model typował NIE, a potok kasował to po cichu
- **`b51ea5519`** `koryguj_tip_ou_btts` od dawna przerzuca typ na `"BTTS NO"`, gdy model
  daje stronie TAK mniej niż próg. Reszta potoku o tym nie wiedziała, w czterech miejscach:
  `prob_modelu` nie znało typu (pewność **50 zamiast 100−bt** — dla typów, których model
  był najpewniejszy), `_TYP_DO_ODDS_KEY` nie znało (noga kasowana), powód odrzucenia
  mówił „halucynacja Groqa" (Groq nie miał z tym nic wspólnego), a parsery API-Football
  i SofaScore brały ze zwracanego rynku **tylko stronę „yes"** — więc nie było czym wycenić.
  `match_tips.py` już czytał `odds.get("btts_no")` i dostawał wyłącznie kurs teoretyczny.
- **Zmierzone (walk-forward n=15 460, 39 lig, próba dzielona po dacie):** sygnał `p_btts`
  jest REALNY i replikuje się — krzywa monotoniczna w obu połowach (0-40% → BTTS pada
  w 48.7%/51.2%; 65%+ → **60.7%/64.1%**). Gra dwustronna bije stałą odpowiedź: TAK
  +7.0/+8.4pp, NIE +6.3/+6.6pp.
- **Ale rynek dalej lepszy:** Brier 0.2524/0.2508 vs **0.2503/0.2460**; przy niezgodzie
  rynek 52.2%/53.0% vs model 47.8%/47.0%. Strona NIE trafia 50.8%, więc do zera wymaga
  kursu **2.10**, a rynek daje ~1.6. Stąd `BTTS_TWO_WAY` **default OFF** — typ jest
  liczony, wyceniany i logowany, ale nie gra.
- Powód odrzucenia nogi rozróżnia teraz „źródło nie wycenia tego rynku" od „typ zmyślony".

### Migracja 13 wdrożona
- Kolumna `odds_verified` weszła przez CD (API rew. 00402 woła `run_migrations`).
  Joby przebudowane osobno, digest **z tagiem** `89ae6a28` — dwa nowsze digesty
  w rejestrze były BEZ TAGU (manifesty atestacji BuildKita), ta sama pułapka co 30.07.

## 2026-08-14

### `predictions` opisywało propozycje Groqa, nie zagrane typy
- **`6b25c95c9`** zapis predykcji dzieje się w KROKU 3 `daily_agent` (wewnątrz analizy Groqa),
  a anty-halucynacyjna podmiana kursu dopiero w KROKU 4. Weryfikacja działa na słowniku
  w pamięci i **nigdy nie wracała do bazy**. Komentarz „FAZA 17.3: top3 też weryfikowane
  (wcześniej halucynacje wchodziły do predictions)" opisywał naprawę, która nie mogła zadziałać —
  zapis jest wcześniej w potoku.
- Zmierzone na prodzie: ten sam kurs **52.58 na trzech różnych meczach** jednego dnia,
  Over 2.5 po 52.58, Under 2.5 po 1.05. **48 ze 133 rozliczonych (36%)** miało kurs poza
  filtrem longshotów 1.2–4.0 i trafiało **20.8%**. Bez nich trafność całości to 45.9%
  zamiast 36.8%, a 1X2 **45.5% zamiast 33.7%**.
- Konsumenci tych kursów to `backtest` (ROI, pasma kursów), `clv_tracker` i dashboard —
  czyli raporty, na których opieramy decyzje o modelu.
- Fix: migracja 13 + `odds_verified`, `oznacz_zweryfikowane`, KROK 4a w `daily_agent`
  (mniej trafień niż nóg → WARNING, nie cisza), CLV liczy tylko zweryfikowane i głośno mówi
  ile odrzucił, `stan_uczenia.py` pokazuje udział zweryfikowanych.

### Podzbiory BTTS i O/U — hipoteza „model działa na specyficznych meczach" obalona
- Test na **n=15 460 z 39 lig**, próba dzielona po dacie: podzbiory szukane na starszej
  połowie, liczone na nowszej. **52 podzbiory** wzdłuż 6 wymiarów (liga, pasmo pewności,
  suma λ, λ słabszej strony, rozjazd z rynkiem, zgoda z rynkiem).
- **BTTS: 5 kandydatów na DISCOVERY, 0 przeżyło.** **O/U: 2 z dodatnim ROI, 0 przeżyło.**
- **Wczorajsze +9,2% na ligach czołowych nie replikuje się:** −11,4% (55 zakładów) vs
  +12,1% (61) — obie w granicy błędu, znak się odwraca. Lig dodatnich w obu połowach: 0.

### Rozliczenia gubiły predykcje bezpowrotnie — 95 sierot na produkcji
- **`3d678f557`** okno rozliczeń było domknięte z OBU stron (`cutoff <= data < dziś`) i przesuwało się
  z datą, więc predykcja bez wyniku w swoje 3 dni wypadała z zasięgu **na zawsze**. Każda chwilowa
  usterka (padnięty job, brak meczu w źródle, zawieszone API-Football) zamieniała się w trwałą stratę.
  Zmierzone: 95 predykcji bez wyniku, mecze od 7 maja; 13 dało się jeszcze odzyskać, **82 przepadły**.
  Fix: `_wybierz_do_rozliczenia` (świeże okno w całości + zaległości paczkami po 15, limit 5 prób),
  migracja 12 z `settle_attempts`. Zweryfikowane na prodzie: licznik prób 0 → 19.
- **Druga ścieżka też ich nie łapała:** `cron_settle` rozlicza KUPONY, a wszystkie predykcje System
  mają `coupon_id IS NULL`. Dwa mechanizmy rozliczeń i żaden nie pokrywał tego przypadku.
- **`run_migrations()` odpalało wyłącznie `api/main.py`** → poprawność zależała od niepisanej kolejności
  wdrożenia, a brak kolumny wywalał CAŁY dzienny przebieg (KROK 0). Joby migrują teraz same.
- Test `test_mecz_starszy_niz_days_back_pomijany` **kodował ten błąd** — wymagał pomijania zaległości.
  Przepisany na nową intencję wraz z historią, dlaczego stare uzasadnienie było błędne.

### Pętla uczenia — obie strony medalu
- **`2b50d73ec`** `stan_uczenia.py` pytał tylko `predictions` (tabelę PO filtrach), więc w dni z zerem
  kuponów pokazywał martwą pętlę. `model_log` zbierał w tym czasie 202 oceny, 105 rozliczonych.
  Licznik do werdyktu: „brakuje 20" → „brakuje 7".
- **`a661afefa`** lekcje także z trafień — `_pobierz_porazki` miał `tip_correct = 0` zaszyte w zapytaniu.
  Osobny prompt pyta „proces czy szczęście" i każe być surowym; trafienie z błędnego powodu to nadal
  błędna decyzja. Domyślnie WYŁĄCZONE (pisze do prod `ai_feedback` + tokeny Groqa).
- **`f2e570faa`** regresja z powyższego: lekcje z wygranych szły do Groqa pod nagłówkiem
  „WNIOSKI Z OSTATNICH PORAŻEK — ucz się błędów", czyli model uczył się omijać to, co zadziałało.
  Każdy wniosek niesie teraz `(TRAFIONY)`/`(CHYBIONY)`.
- **`791f51063`** blacklista lig wycinała kandydatów całkiem po cichu — gałąź bez licznika i bez nazwy.
  Wykryte wymuszonym przebiegiem produkcyjnym; ta gałąź nie miała ANI JEDNEGO testu.

### Bezpieczeństwo
- **Rotacja `CRON_SECRET`** (Secret Manager v2 + serwis + 5 zadań Schedulera) po tym, jak wartość
  trafiła do wyjścia terminala przy filtrowaniu env. Zweryfikowane: nowy sekret 200, stary **401**.
- **`CRON_SECRET` → `secretKeyRef`** (rew. `00395-nss`) + dopisany do re-asercji w `cd.yml`.
  Wartość nie jest już widoczna w `gcloud run services describe`. Wcześniejszy konflikt typów,
  który wypchnął go do plain env (`aa307944f`), zniknął po pełnym przejściu na sekrety.
- **Ekspozycja Neona zamknięta:** wersja **1** sekretu `DATABASE_URL` zawierała połączenie do Neona
  i była `enabled` → wyłączona (dziś `FAILED_PRECONDITION`). Przeskanowane 60 rewizji Cloud Run —
  **żadna** jej nie wystawiała. Backfill okazał się już wykonany (`predykcje do wstawienia: 0`,
  sędziowie 186 w obu bazach). Kupony/bankroll/users z Neona **odpuszczone** (decyzja usera).

### Rozjazd wag ensemble zlikwidowany
- Ten sam mecz dawał **inną predykcję zależnie od ścieżki**: API miało `ENSEMBLE_MARKET_WEIGHT=0.70`,
  joby nie miały nic (default 1.0 = czysty model). Joby dostały 0.70. Decyzja poparta przeliczonym
  A/B na nowym modelu (n=3578, 3 niezależne grupy lig) — pełna tabela w `.env.example`.
- **NIE zeszliśmy do 0/100** mimo że mierzy się najlepiej: grupa kontrolna ma szczyt trafności przy
  30/70, a wypisanie modelu z 1X2 to decyzja produktowa, nie parametr.

### Werdykt per rynek — trzy różne odpowiedzi (walk-forward, n≈3586)
- **1X2 przegrany.** Przy niezgodzie z rynkiem (510 meczów) rynek trafia **42.9%**, model **29.8%** —
  spójnie we wszystkich trzech grupach. ROI ujemne przy KAŻDEJ wadze. To niezależnie potwierdza
  pivot z 07-06: static value-betting na publicznych danych nie bije rynku.
- **BTTS gorszy od stałej.** Model 53.2% / Brier 0.2496 vs częstość bazowa 54.4% / 0.2480.
  Typowanie „zawsze BTTS tak" bije model. Prod potwierdza: 18.2% (2/11). Kursów BTTS w datasecie
  NIE MA — to porównanie z częstością bazową, nie z rynkiem.
- **O/U 2.5 jedyna nadzieja.** ROI przy 30/70: ligi czołowe **+9.2%** (106 zakładów), razem −0.2%
  (na zero po 12% podatku). Przy niezgodzie na czołowych model **wygrywa 52.1% do 47.9%**.
- Ograniczenie: `model_log` śledzi wyłącznie argmax 1X2 → rynków golowych nie zweryfikujemy live
  bez rozszerzenia dziennika.

### Model
- **`QUICK_PICKS_USE_POISSON_CACHE` 0 → 1 na API.** Przy `=0` draft (kupony System) z definicji chodził
  na `bzzoiro-ml` — stąd 218 predykcji `bzzoiro-ml` vs 10 `poisson-dc`. Flaga wyłączała adapter schematu,
  a walidator odrzucał ramkę, więc Poisson odpadał po cichu. Zmierzone przed flipem (`model_log`):
  poisson-dc 65.2% (15/23), bzzoiro-ml 50.0% (41/82).
- **Kalibracja λ replikuje się** — niezależne przeliczenie na n=2983 dało 1.0193/0.9967 wobec
  1.0158/0.9795 z 09.08. NIE wdrożone (różnica w granicach szumu). Uwaga: n=388 daje mylące 0.921 —
  szum małej próby, nie zmiana reżimu.

## 2026-07-27

### Incydent logowania — redeploy zgubił env Cloud Run
- **Objaw:** login zwracał 500, a GUI pokazywało „nieprawidłowe dane" → wyglądało na złe hasło, było brakiem
  `JWT_SECRET` i reszty env po redeployu. Naprawione rev **00313-mf5**.
- **`335df65bb`** login odporny na malformed `password_hash` — 401 zamiast 500 (bcrypt na śmieciu rzucał).
- **`0cded9b4d`** `/mcp` montowany **tylko poza produkcją** (niepotrzebna powierzchnia ataku na prod).
- **`b5c49484a`** CD jawnie re-asertuje krytyczne sekrety przy deployu (self-heal — env nie zniknie po redeployu).
- **`aa307944f`** `CRON_SECRET` wyjęty z `secrets` (plain env var → konflikt typów blokował deploy).
- **`cc4574d16`** `LoginView` rozróżnia błąd serwera / rate-limit / brak sieci od faktycznie złych danych.
- **`17a2ecea4`** `scripts/backfill_users_from_neon.py` — przeniesienie kont Neon→Supabase 1:1 (login+hasło).
- **Audyt auth:** 6 znalezisk, rdzeń szczelny (SQL parametryzowane, JWT fail-closed, rate-limity działają).

### Sprzątanie repo
- **`0832d8bc2`** `pdf/` (12 raportów luty-maj) → `docs/archive/pdf/`, `logs/*` (25 plików) → `docs/archive/logs/`,
  10 screenshotów QA z rootu → `docs/screenshots/`. Usunięte regenerowalne: `.playwright-mcp`, `.mypy_cache`,
  `.pytest_cache`, `.ruff_cache`, 42 stare hook-backupy, `validation_errors.csv`, `brain_graph.html` (~17 MB).
- Docs zsynchronizowane ze stanem faktycznym: `STATUS.md` (był 07-03), `TODO.md` (plan P0-P3), oba README
  (Neon→Supabase, Task Scheduler→Cloud Run Jobs, 1656 testów), `PROJECT_STRUCTURE.md`.

## 2026-07-21/22

### Dziennik kuponów J1-J6 + match-linking
- **J1** `core/user_stats.py` — agregat read-only (ROI/win-rate/profit/streak/best-worst), 25 testów.
- **J2** `GET /api/stats/me` + `StatsView.jsx` — etykiety PLN + disclaimer „papierowy bankroll".
- **J3** `get_progress_series` + `GET /api/stats/progress` + `ProgressChart.jsx` (recharts).
- **J4** kolumna `bookmaker` + `POST /api/coupon/manual` + `PATCH /api/coupon/{id}/result`
  (owner-check, CAS, guard `kupon_type=='manual'`) + `ManualCouponForm.jsx`. Manual **wykluczony z auto-settle**.
- **J5** `GET /leaderboard` — sort (win_rate/roi/profit) + filtr `days`, ranking **shared-only** (opt-in).
- **J6** `POST /api/coupon/preview-signal` — podgląd „Nasz typ @conf%" w formularzu ręcznym.
- **Match-linking** `core/match_linker.py` (STRICT `_norm_ascii`, exact-only, 11 testów) +
  `settle_manual_coupons` (all-legs-or-nothing, CAS-guard, zero zewn. API, 13 testów) +
  `POST /cron/settle-manual` — **nie wpięty w scheduler**, czeka na decyzję.

## 2026-07-20

### Incydent po wyjeździe — potrójna awaria pipeline (14-20.07) + migracja DB
- **Neon quota-block (od 18.07):** pool (`minconn=1` + keepalives 30 s) trzymał endpoint obudzonym
  ~24/7 → free tier spalony w 17 dni, twardy blok connect do 1.08. **Prod DB → Supabase free**
  (session pooler eu-west-1): schemat + migracje + seed + RLS na 11 tabelach; secret `DATABASE_URL` v2;
  API rev 00305 (wcześniej URL Neona hardkodem w env serwisu). **Backfill z Neona po 1.08.**
- **`74c13d638`** image `footstats-jobs` bez pakietu `footstats.data` → `final` padał 14-20.07.
  Root cause: `gcloud builds submit` bez `.gcloudignore` generuje ignore z `.gitignore`, a
  niezakotwiczone `data/` wycinało `src/footstats/data/` z tarballa. Fix: `.gcloudignore` + `/data/`.
- **`9e74c59c2`** `kupon=None`/`zdarzenia=None` od Groq → crash `_dodaj_kelly` (daily_phases:491).
  None-guardy `(x or {})` w całej ścieżce final + 2 testy TDD. Po fixie: **pierwszy zielony
  `footstats-final` od 13.07** (3 predykcje 21-23.07 w Supabase).
- **`3c6bac670`** db-resilience: `psycopg2.Error` w catch `admin_user` (fallback zamiast crashu
  daily_agent) + init DB w `api/main.py` (import przeżywa martwą DB — kolekcja pytest, start kontenera).
- **`0e81aee9a`** merge BP-01 T1+T2 (routine z wyjazdu): walidacja Pydantic `POST /analyses/llm`
  (audyt M1) + auth JWT na endpointach analiz + GUI `apiFetch` (audyt H1 zamknięty).

## 2026-07-03

### Kalibracja + model — obrona i Kontuzje v2
- **`1ef84381c`** `probability_calibrator` runtime **health-gate**: płaska krzywa (rozpiętość y<0.10) →
  identity nawet przy `CALIBRATION_ENABLED=1`. Obrona przed footgunem — PROD Neon ma 104 settled →
  isotonic daje span 0.049 (płaska). +1 test. **Źródło prawdy = Neon (`_db.connect()`), NIE legacy sqlite.**
- **`880640223`** **Kontuzje v2 (rdzeń)**: `injury_lambda_factors(injuries, goal_shares=)` — kara napastnika
  = `goal_share*0.5` (utrata topowego strzelca boli mocniej niż rezerwowy). Wstecznie zgodne (None→v1). +6 testów.
  Scraper multi-source goal_shares (decyzja usera: kilka źródeł + cross-check) = osobny slice na sierpień.

### Auth — reset hasła
- **`b935a25ab`** `/api/auth/forgot-password` (zawsze 200, anty-enumeracja, graceful) + `/api/auth/reset-password`
  (JWT `purpose=reset` ≤1h) + LoginView tryby forgot/reset. Rate-limit 5/min. Reuse `send_password_reset_email`. +5 testów.
- **`ccd52f3c5`** review-fix: szersze łapanie wyjątków (psycopg2/HTTP) — gwarancja 200.
- **`5d8ca1712`** reset-password osiągalny mimo tokenu w localStorage (App.jsx wymusza LoginView na `/reset-password`).
  **Złapane wizualną weryfikacją Playwright.** Wymaga env `FRONTEND_URL`.

### Admin — panel Model vs Live
- **`2bdbc514e`** `/api/admin/model-vs-live` (require_admin) + sekcja w AdminPanelView: reliability
  (pewność→realna trafność), ROI kuponów, selekcja tip==argmax vs override. Diagnostyka sesji → stały monitoring. +2 testy.

### UI
- **`2efc10b43`** badge pewności modelu (`leg.prob`) na nodze kuponu (warunkowy).

### Cloud migration — pełny pipeline PC-off (Cloud Run Jobs)
- **`c2ba63a12`** config deploy-ready: `Dockerfile.jobs` (Playwright), `scripts/run_job.sh` (dispatch `JOB_PHASE`),
  `docs/cloud_migration.md` (runbook gcloud). **Decyzja: cloud, nie Raspberry Pi.**
- **`b8e042208`** fix CRLF: `run_job.sh` z Windows CRLF psuł Job (`env: bash\r` → exit 127) — sed strip w Dockerfile + `.gitattributes`.
- **fix deps**: `beautifulsoup4` niezadeklarowane w pyproject (bs4 crashował Job) + obraz instaluje `.[api,ai,scraper]` (groq też brakował).
- **Deploy UKOŃCZONY (footstats-495009):** obraz w Artifact Registry, Cloud Run Jobs `footstats-final`+`footstats-evening`
  (sekrety Secret Manager, SA compute, 2Gi/Playwright), test-run zielony. Cloud Scheduler `footstats-final-trigger` 11:00
  + `footstats-evening-trigger` 23:00 CEST (ENABLED). **Lokalne taski Disabled** → PC-off OK. Sekrety `APISPORTS_KEY`+`FOOTBALL_API_KEY` dodane.
- **fix CI**: `test_missing_results_stays_partial` bił realną sieć (consensus/football-data niezmockowane) — lokalnie ukryte
  (`.env`→DATABASE_URL→guard OFF), na CI RuntimeError. Domockowane. + audyt broad-except (auth/model-stats do BASELINE).

### Kupony
- 10 kuponów Admin_JG (#391-400, 5 zł, model best-picks śr prob 84%/EV 1.15). Na 2026-07-03: **3/3 rozliczone = WON** (+6.2 zł).

### Testy
- Suite: **1448 passed / 8 skip** (pełny regres, zero regresji).

## 2026-06-26

### Observability — cloud-draft data-freshness guard + flip-advisor
- **`748364933`** `core/draft_health.py::ocena_swiezosci` — dni od ostatniego kuponu System
  (`created_at`). cloud_draft dokleja `{stale_days, stale}` do `/cron/draft` + `log.warning` gdy STALE
  (≥3 dni). **Rozróżnia BENIGN-0 (PC pokrył, dedup) od STARVATION-0 (zbieranie zamarło)** — wcześniej
  HTTP 200 = ślepota. Surface w Cloud Logging (log-based alert). Graceful. +15 testów.
- **`b862ef85f`** `core/flip_advisor.py` — pure werdykty flipu lewarów M1: `werdykt_selekcja` (high-conf
  band vs ogół → `SELECTION_MIN_CONF`) + `werdykt_gating` (ligi <50% n≥8 → `LEAGUE_GATING`/`LIGI_SLABE`).
  Wpięte w `calibration_monitor` (raport per-liga + sekcja flip). +7 testów.
- **`74160501e`** testy `system_paper.build_single_leg_coupons` (writer danych System, pętla DB) — +5.

### M1 lewary — selekcja + gating (zbudowane, flag-gated default OFF, flip po walidacji)
- **`bb877e85a`** selekcja high-conf (lever #1): flaga `SELECTION_MIN_CONF` w `system_paper.najlepszy_typ`
  — domyślnie MIN_PROB (40, zero zmiany), podnosi próg do pasma high-conf (offline 65%+=68% acc).
  Czytane przy każdym wywołaniu (flip bez redeploy), fallback do 40 poza [0,100]. +5 testów.
- **`074a27e98`** gating słabych lig (lever #2): `LIGI_SLABE` (POL/ESP/FRA <50% offline) + flaga
  `LEAGUE_GATING` (default OFF) w `_pre_filtruj_ligi`. Gdy ON: odrzuca słabe ligi, faworyzuje
  NED/SCO/ITA/ENG. Porównanie znormalizowane (prefiks/akcenty/case). +6 testów.
- Oba wpływają na System paper-trading + cloud-draft (wspólna ścieżka filtrów). Flip po ~88 świeżych settled.

### Schedule-adjusted ratings (lever #5) — zbadane → ślepa uliczka (marginal)
- **`b70dfb3c4`** opponent-adjusted ratingi w `_oblicz_sile_wazona` (flaga `SCHEDULE_ADJUSTED_RATINGS`,
  default OFF): jedna iteracja korekty siły o trudność terminarza (atak=ważona gole/obrona_rywala).
  **Offline A/B (walk-forward DC W=0.5, n=2976): 50.97% → 51.18% = +0.20pp (szum, se~0.92pp)**,
  poniżej hipotezy +0.5-1pp, +57% wolniej. **Flag zostaje OFF** (jak ImportanceIndex/LightGBM).
  Kod + 7 testów zostają jako infra/zmierzony wynik.

### Coverage — ratchet floor 55→57
- **`617414137`** testy `ai/scoring.py` (kurs_do_prob/value_bet, było 30%) + `core/confidence.py`
  `komentarz_analityka` (string builder, było 74%) — pure-logic, +17 testów. CI `--cov-fail-under`
  55→57 (zmierzone 57.66%). Suite ~1375 pass / 6 skip.

### Parquet na cloud (cloud-draft Poisson) — DECYZJA: odłożone do sierpnia
- Cloud-draft `model_source=bzzoiro-ml` bo parquet nieobecny w obrazie (`.dockerignore` wyłącza
  `data/hist_cache/`, `data/` gitignored). Off-season WC=kadry → Poisson nie ruszy (dataset klubowy)
  → bzzoiro-ml OK teraz. Wrócić na restart lig klubowych (image COPY / GCS-pull). TODO #3 pending.

### 🔴 BUGFIX — quick_picks nie używał Poissona live (schema mismatch → Bzzoiro-ML)
- **`cc6242590`+`92dc276aa`+(flip default)**: `quick_picks` ładował `load_cached()` (schemat angielski
  home/away/hg/ag/date), ale `waliduj_df_wyniki` wymaga polskiego (gospodarz/goscie/gole_g/gole_a/data)
  → `df_mecze=None` → **Poisson CICHO pomijany → fallback Bzzoiro-ML**. Live (47.8%) używał Bzzoiro-ML,
  NIE naszego Poisson-DC (51.8% offline) — prawdopodobnie duży element luki Cel B (live≪offline).
  Fix: adapter `adapt_to_prod_schema` w quick_picks, **default ON** (escape-hatch `QUICK_PICKS_USE_POISSON_CACHE=0`).
  De-risk: na reprezentacjach (WC) typy identyczne (brak historii kadr w dataset klubowym) → zero zmiany
  teraz; realna poprawa na restart lig klubowych. +regression test, suite 1340 pass. cloud_draft `model_source` raportuje stan.

### Cloud-draft — System paper-trading PC-niezależny (odblokowanie danych walidacyjnych)
- **`e4da7adff`**: `/cron/draft` endpoint + `core/cloud_draft.py::generuj_system_draft`. Lite draft
  System (model-only) samą ścieżką requests (Bzzoiro API → quick_picks → predict_match) — BEZ
  Playwright/Groq/Telegram. **`dry_run=True` DEFAULT = zero zapisów Neon** (deploy bezpieczny/inert);
  live = `dry_run=false` po weryfikacji. Pole `model_source` wykrywa Poisson-DC (parquet) vs fallback
  Bzzoiro-ml. +5 testów (mock, graceful — nigdy 500). Odkrycie: `BzzoiroClient` jest requests-based
  (NIE Playwright) → rdzeń draftu cloud-feasible; Playwright dotyczy tylko forma/Superbet (enrichment).
- **`fbbe3793c`**: `/api/cron/draft` w `_LONG_RUNNING_PATHS` (120s zamiast 10s timeout).
- **WŁĄCZONY LIVE (06-26):** Cloud Scheduler `footstats-draft-morning` (07:30 CEST, `dry_run=false`,
  header `X-Cron-Secret` z Cloud Run env). Pierwszy run created:0 = **idempotencja** (12 kandydatów WC
  już miało kupony System — dedup per mecz/data; System user istnieje, leaderboard total:15). `model_source=bzzoiro-ml`
  na cloud (parquet nieobecny — Poisson po dostarczeniu `full_dataset.parquet`).

### Ensemble — reweight ku rynkowi WDROŻONY LIVE
- **`589e1aa6a`** (flaga) + **flip env**: `ENSEMBLE_MARKET_WEIGHT=0.70` (=30/70 model/rynek) na Cloud Run
  **rev 00274 LIVE**. WF A/B: 70/30→51.8% vs 30/70→52.8% (z kursami 52.5→53.8). Model przy praktycznym
  suficie, rynek (kursy) ~53% nieprzekraczalny. Zostawia 30% głosu modelu na value. Escape-hatch: usuń env.

### Infra ML + coverage
- **`6bfdf27dc`** `core/standings.py` (rekonstrukcja tabeli ligowej no-lookahead) + **`e9f1949e6`**
  `core/ml_features.py` (pi-ratings/elo/form/standings/odds). ImportanceIndex/LightGBM zbadane → ślepa
  uliczka (< rynek), moduły zostają jako infra cech. +18 testów.
- **`bc793c0e3`** test pokrycia prod `/cron/evict-cache` (było 0%, +5 testów). Suite ~1346 pass / 6 skip.

## 2026-06-24 / 06-25

### Settlement — consensus multi-source
- **`349fd919a`**: `coupon_settlement._find_leg_result` — Źródło 5: `aggregator.consensus_result`
  jako additive fallback po źródłach 1-4 (dokłada football-data.co.uk CSV + cross-walidowany
  FlashScore gdy AF/football-data.org/cache/DB nie pokryły meczu). +3 testy regresji.

### CI — lint/type gate + sprzątanie martwego kodu
- **`e7ea3ea50`**: job `lint` w `ci.yml` — `ruff check` (E9 składnia + F pyflakes, blokujący) +
  `mypy` na `scrapers/sources` (ratchet). Config w `pyproject.toml` (select/per-file-ignores).
  `ruff --fix` usunął ~200 martwych importów/zmiennych (51 src + 46 test, 99 plików). Przywrócone
  2 re-eksporty potrzebne testom (`quick_picks.calibrate_confidence`, `bzzoiro.ENV_BZZOIRO`).

### Bezpieczeństwo — hardening OWASP API Top 10 (wdrożony LIVE 06-25)
- **`cd2667579`**: `/health` okrojony (zero bankroll/accuracy/userów/timestamp — był publiczny leak);
  `/leaderboard/{u}/coupons` bez `user_id`; rate-limit `/auth/login` 10/min + `/auth/register` 5/min
  (`api/limiter.py` wydzielony); `/docs`+`/redoc`+`/openapi.json` off w prod (`ENV`); `/metrics` za
  `METRICS_TOKEN`; middleware nagłówków (nosniff/DENY/HSTS/no-referrer). +4 testy.
- **`6afa46f6a`**: DevSecOps — `bandit` (SAST, 1 realny fix MD5 `usedforsecurity=False` + 5 false-pos
  `# nosec`) + `pip-audit` (nasze deps: 0 CVE). Job `security` w CI + Dependabot (pip/npm/actions).
- **`9a09e6beb`**: `gitleaks` (job `secrets` + `.gitleaks.toml` allowlist) + `.pre-commit-config.yaml`
  (ruff/bandit/gitleaks/detect-private-key). Historia git: 0 realnych kluczy API.
- **Wdrożenie prod (06-25):** push → CD → Cloud Run revision 00259; METRICS_TOKEN zamontowany jako
  secret-ref env. Zweryfikowane live: `/health` minimal, `/metrics` 401, `/docs`+`/openapi` 404,
  4 nagłówki bezpieczeństwa obecne. Audyt non-API czysty (sekrety/git, Telegram authz, DB fail-closed).

### Refactor — dekompozycja superbet.py (ostatni god-moduł)
- **`3ad91a844`**: `superbet.py` 1128→867 linii — 6 czystych parserów (dict/str/list → dict)
  wydzielonych do `superbet_parsing.py` (AST-precyzyjnie, behavior-preserving). +22 testy
  (logika wcześniej 0% pokryta). Scrapery Playwright (`zaloguj`/`pobierz_*`) zostają.

### CI/CD — coverage gate + Dependabot fix
- **`4a85f91ab`**: job `test` liczy `--cov` i wymusza `--cov-fail-under=55` (floor anty-regresyjny,
  zmierzone ~57%; ratchet do 80%). Domyka gap "brak progu coverage".
- **`67af2d168`**: `secrets` job (gitleaks) `if: github.actor != dependabot[bot]` — Dependabot PR-y
  dostają read-only token bez secrets → gitleaks failował na 10 PR-ach. Skip bezpieczny (bumpy wersji
  nie dodają sekretów do źródła).

### Refactor — dekompozycja god-modułów
- **`c48ab449f`**: `daily_agent.py` 1078→818 — `daily_agent_output.py` (console/rich/zapis txt/toast) +
  `daily_agent_decision.py` (decision score). Behavior-preserving, re-export z `# noqa` (patch-targety).
- **`9bad59ac4`**: `utils/logging.py` 723→539 — `exceptions.py` (Blad*) + `safe_http.py`
  (BezpiecznyHTTP/BezpiecznePobieranie). Re-export, identity klas wyjątków zachowana.

### Scrapery — TheSportsDB 4. źródło
- **`3b16a64f5`**: `thesportsdb_source.py` — darmowe JSON API (bez anti-bot), FT. Pokrycie
  reprezentacji/towarzyskich/turniejów (settlement orphan predykcji MŚ/friendly, D1a). Graceful +
  cache 6h + 14 testów. Rejestr aggregatora = 4 źródła.

### Bezpieczeństwo — rotacja + CORS cleanup + cloud audyt + backup (06-25)
- CRON_SECRET **rotowany** (Cloud Run rev 00262 + headery obu scheduler jobów). `ALLOWED_ORIGINS`
  **wyczyszczony** (secret v3, rev 00263) — usunięto `localhost:5173/3000`, został Vercel+run.app.
- Cloud Scheduler zweryfikowany AKTYWNY: `footstats-settle-morning` (06:00 UTC=08:00 CEST) +
  `-evening` (21:30 UTC) → POST `/api/cron/settle` z `X-Cron-Secret`. Morning 06-25 potwierdzony
  200 OK (settled 0 — brak ACTIVE, bo draft lokalny nie odpalił, PC off). DRAFT = nadal tylko lokalny.
- **`59e0f7565`**: Daily DB Backup naprawiony — realny `pg_dump` Neona → GCS (off-site, conn z
  Secret Manager przez WIF, gated graceful). Zastąpił obsolete SQLite-backup co padał codziennie.

### R&D — walidacja modelu + ślepe uliczki (offline, zero prod, 06-25)
- **Walk-forward A/B + sweep `W_BAYESIAN`** (n=7934, out-of-sample): dixoncoles **51.8%** > baseline
  50.3% > poisson_only 48.8%. `W_BAYESIAN=0.5` potwierdzone optymalne (0.3→51.4/0.7→51.7/1.0→50.4).
  Kalibracja: pasmo 65%+ = **68%** trafność. Wniosek M1: model OK (DC on, W optymalne), droga =
  **SELEKCJA** (65%+ subset) + gating słabych lig (POL/ESP/FRA). Zero zmian λ w prod (dyscyplina walidacji).
- **`6bfdf27dc`**: `core/standings.py` (rekonstrukcja tabeli z wyników, no-lookahead, +13 testów).
  Backtest ImportanceIndex A/B → **ŚLEPA ULICZKA**: 14205 meczów OFF 47.3 vs ON 47.2 (−0.1pp),
  high-stakes (n=4100) OFF 51.2 vs ON 50.6 (−0.59pp). Crude ±20% nie pomaga, na high-stakes szkodzi.
  NIE wpinać. Standings infra zostaje (pozycja/punkty = cechy do przyszłego modelu ML — pomysł B).

### R&D — własny model ML (pomysł B) + reweight ensemble ku rynkowi (06-25, offline)
- **`e9f1949e6`**: `core/ml_features.py` (pi-ratings Constantinou + Elo + rolling form/strzały +
  pozycja/punkty + devig kursów, no-lookahead single-pass, +5 testów leakage-safety). Eksperyment
  LightGBM 1X2 (train 24400→test 8000, OOS): **51.6%** (z kursami) / 50.9% (bez) — **NIE bije rynku
  53.1% ani baseline 51.8%**. Potwierdza literaturę (rynek sharp; RPS nie do pobicia — SOTA CatBoost+pi
  55.8%). ml_features zostaje jako infra; LightGBM NIE wpinany do prod.
- **Reweight ensemble model↔rynek — REALNY WIN.** WF A/B (n=7934, OOS): obecne **70/30 = 51.8%**, ale
  30/70 = 52.8 / 15/85 = 53.1 / 0/100 = 53.2 (z kursami 52.5→54.3) — monotonicznie, **model ważony 70%
  dusił sygnał rynku (+1.4pp na stole)**. Flaga **`ENSEMBLE_MARKET_WEIGHT`** (env 0..1; **default OFF =
  obecne 70/30, zero zmiany prod**) + 4 testy. Rekomendacja: `=0.70` (30/70 — zostawia głos modelu na
  value/EV). **Flip PO walidacji** (~88 fresh; zmiana warstwy predykcji). Calibration check przy flipie.

## 2026-06-23

### Scrapery multi-source + cross-walidacja
- **`5c0a9adc2`**: framework `scrapers/sources/` — typ ujednolicony `MatchData` (wynik/HT/kursy/
  timestamp/source), protokół `ResultsSource` (interfejs każdego adaptera), `aggregator`
  (porównanie wielu źródeł → consensus/flag rozjazdu). Adapter API-Football jako 1. źródło
  (`af_source.py`). +202 linii testów (`test_scrapers_sources.py`).
- **`6ad9899d4`**: scraper football-data.co.uk jako `ResultsSource` (CSV wyniki+HT, bez anti-bot,
  `footballdata_source.py`). +164 linie testów.
- **`d35a074b4`**: rejestr aggregatora — football-data.co.uk jako 2. źródło (cross-walidacja);
  live smoke OK (AF 79 meczów+HT).
- **`0383a11ff`**: FlashScore (mobi, finished-only) jako `ResultsSource` — redundancja FT
  (`flashscore_source.py`). +161 linii testów.
- **`a0c22d2c6`**: rejestr aggregatora — FlashScore jako 3. źródło; live cross-walidacja OK —
  AF 79 + FlashScore 98 meczów, **27 potwierdzonych przez ≥2 źródła, 0 rozjazdów**.

### Fix — FlashScore live-leak
- **`fb98b9188`**: `_parse_mobi_html` matchował każdy `<a>` ze score, ignorując `class="fin"`
  (zakończony) → mecz w trakcie (Norway-Senegal 0-0 @15min) zwracany jako końcowy →
  settlement: BTTS=nie → kupony **#240/241/242 LOST błędnie** (mecz trwał). Fix: tylko mecze
  z `class="fin"`. Kupony zrewertowane do ACTIVE, FlashScore cache (live leaki) wyczyszczony.
  +4 testy regresji.

### Brain graph
- **`53499bbfc`**: `scripts/visualize_brain.py` przepisany na warstwową architekturę aktualną
  — 41 węzłów (było 15, przestarzałe: SQLite/db_main, brak scraperów/sources/phases/markets/D3).
  Warstwy kolorami, pełny data-flow (pipeline→Groq→kupony→settlement, multi-source
  cross-walidacja, RAG memory loop, FastAPI+GUI+Neon). `brain_graph.html` regenerowany (gitignored).

### Suite
- **1254 passed / 6 skip** (zweryfikowane lokalnym uruchomieniem `pytest tests/ -q`).

## 2026-06-22

### Bugi / fixy
- **Trainer crash na float korekcie** (`c99d41fe9`): `get_kalibracja_inject` formatował korektę
  z `f"{kor:+d}"` (int-only) → `ValueError` gdy `korekta_pewnosci` float → KROK 3 (Groq) crashował
  całkowicie, 0 predykcji zapisanych (baza kalibracji zagłodzona). Fix: `:+.0f` (float i int). +3
  testy. Złapane przez obserwowalność (sched log) z 06-21 — wcześniej niewidoczne.
- **Telegram HTML escape + cli NameError** (`6ad1dfd9a`): (1) nazwy drużyn z `</&` łamały
  `parse_mode=HTML` → HTTP 400 "can't parse entities", cicha porażka wysyłki — naprawione
  `html.escape` w `send_draft_kupon`/`send_kupon`/`_format_zdarzenia` + logowanie realnej
  przyczyny. (2) `cli_commands._analiza_kuponu` wołał `_bzz_parse_prob` bez importu → `NameError`
  przy trafieniu w ev_ml — dodany import z `bzzoiro`. +test regresji.
- **Flaky test deterministyczny** (`fa61cd63b`): `test_zapisz_kupon_final_promotes` był
  order-zależny (`resolve_admin_user_id()` ≠ user_id=1 draftu w izolacji) — zmockowany
  `resolve_admin_user_id→1`.

### D3 — Cel B bug 2 (Groq selekcja), część 1+2
- **`4823ac9c0`**: prob modelu (pw/pr/pp) zapisywane w `predictions` (kolumny prob_home/draw/away,
  migracja 8, DDL + `save_prediction`) — prerekwizyt: wcześniej brak prob modelu → retrospektywna
  analiza Groq-tip vs argmax niemożliwa. Migracja zaaplikowana w prod. Plus guard konserwatywny
  `koryguj_tip_wg_modelu` (w `analyzer_helpers.py`): Groq tip 1X2 z prob modelu <15% → override na
  argmax modelu. Wpięty w `_auto_zapisz_backtest` (top3+kupony). Tylko skrajne przypadki, brak
  prob → nie rusza. +6 testów. Pełna decyzja a/b/c po ~20 świeżych settled — w `TODO.md`.

### Email transakcyjny — Resend
- **`8dcb76a27`**: `utils/mailer.py` — `send_email` via Resend HTTP API (no-dep), `load_dotenv`,
  czyta `RESEND_API_KEY`/`resend_api_key`. `send_welcome_email` wpięte w `/auth/register`
  (graceful, nie blokuje rejestracji). `send_password_reset_email` gotowe na flow reset-tokenów.
  Live test: email dostarczony. FROM=`onboarding@resend.dev` (test-sender, podmień przed prod).
  +6 testów.
- **`a7f815381`**: dokumentacja limitu Resend Free (100/dzień, 3000/mc, 1 domena) w mailer + TODO;
  reset hasła / faktura / domena = follow-up.

### Rynki — Mecz & gol w każdej połowie (GG2H) + HT capture
- **`67f5f418b`**: nowy rynek "Mecz & gol w każdej połowie" — Poisson half-model (rozbicie λ na
  1./2. połowę) + settlement z wyniku HT (`oblicz_tip_correct`) + capture HT z API-Football w
  `results_updater.py` (zapis `ht_home`/`ht_away`). Reorder grupy "Liczba goli" w `markets.py`
  (Over na górze, Under na dole, czytelniejszy UX). +4 pliki testów (`test_betting_utils.py`,
  `test_evening_agent.py`, `test_markets.py`, `test_results_updater_ht.py` nowy).

### Suite
- **1209 passed / 4 skip** (2 fail + 2 error niezwiązane z sesją — `test_checkpoint.py` order
  dependency, `test_file_integrity.py` length check `daily_agent.py` — do zbadania, nie ruszane
  w tej sesji dokumentacyjnej).

## 2026-06-20/21

### Bugi / model (root-cause Cel B + kreator)
- **Kalibracja per-wynik 1X2 — root cause Cel B** (`11cc57232`, 06-20): `calibrate_confidence`
  zaprojektowane dla jednej liczby (confidence vs tip_correct), a stosowane per-wynik na
  pw/pr/pp i bt/o25 w `quick_picks.py`. Na zdegenerowanej krzywej (n_train=41, stare odwrócone
  predykcje) spłaszczało wszystkie wyniki do tej samej wartości → po renorm = uniform. Fix: nie
  kalibruj per-wynik.
- **Gate `CALIBRATION_ENABLED` OFF domyślnie** (`9faa72067`, 06-20): zdegenerowana
  `calibration.json` psuła Kelly + value-bet (zaniżanie). Domyślnie identity, mechanizm krzywej
  zachowany jako `_calibrate_raw` do re-fit (patrz D2 poniżej).
- **Double-chance (1X/X2) devig** (`30ac7c66b`, 06-20): `dc_odds` liczyło `1/(1/a+1/b)` na
  kursach z marżą → double-count overround → kurs <1.0 dla faworyta (kreator pokazał 1X 0.93).
  Fix: zdejmij marżę z trójki 1X2 (devig) przed joint prob → kurs double-chance zawsze >1.0. +2 testy.
- **Rynki: dokładny wynik + multigoal** (`549caa782`, 06-20): grupy "Dokładny wynik" (top-10 z
  macierzy Poissona) + "Multigoal" (0-1..4-6) w `markets.py`; settlement w `oblicz_tip_correct`
  ("Wynik h:a", "Multigoal lo-hi"). GUI renderuje generycznie. +9 testów.
- **Sugerowany typ = argmax 1X2** (`5aa0b6f97`, 06-20): kreator nie zawsze pokazywał "1" jako
  sugestię — teraz argmax modelu.

### Dług techniczny #1-#5 (audyt całościowy 06-20)
- **#1 Refactor `App.jsx`** (`2e112dc2c`, 06-20): 2144→267 linii. Wydzielone components/
  (LoginView, DashboardHome, History, Leaderboard, Settings, AdminPanel, ui, Wizard/*) + lib/
  (api, leagues, tips). Behavior-preserving, build PASS, Playwright OK.
- **#2 Odporność scraperów — health-check** (`f3366933e`, 06-20): `check_and_alert_source_down`
  — alert Telegram + log WARNING gdy źródło (Bzzoiro) zwróci 0/`_valid=False`; graceful, 1 alert/run.
  Wpięte w `_pobierz_kandydatow`.
- **#3 Rozbicie `daily_agent.py`** (`391e7b1b9`, 06-20): 1553→1046 linii; 9 spójnych faz
  wyodrębnionych do `core/daily_phases.py` (injury/forma/betbuilder/kelly/groq-walidacja/
  ensemble/final-enrich). Behavior-preserving, smoke parytet OK.
- **#4 Podwójny backtest — izolacja + usunięcie** (`366b495d2`, `a7e845470`, 06-20/21):
  `backtest_engine.py` najpierw izolowany od prod (guard test-DB, rzuca gdy prod Neon bez
  opt-in), potem USUNIĘTY (moduł + `run_backtest.py` + 2 testy + baseline broad-except) —
  walk-forward zastępuje. `core/backtest.py` (save_prediction) nietknięty.

### Decyzje D1-D8 (06-20 zatwierdzone przez usera, zrealizowane w sesji)
- **D1a — Whitelist +MŚ** (`e9ad8bf1f`, 06-20): "World Cup 2026"/"World Cup"/"Mundial" w
  `LIGI_WHITELIST`; kwalifikacje MŚ nadal odrzucane (blacklist). +2 testy.
- **D1b/D6 — Kursy z 2. źródła = ROZWIĄZANE.** Fallback chain: Bzzoiro → API-Football `/odds`
  → Sofascore. Wpięte w `_wzbogac_o_kursy_fallback` (daily_phases).
  - **AF `/odds`** (`131abc1bf`, 06-21) — PODSTAWOWY fallback, reuse `APISPORTS_KEY` + budżet,
    zero anti-bot. Live smoke potwierdził (Ecuador-Curaçao: home 1.17/draw 7.4/away 13.0/
    over25 1.6/btts 2.55). Koszt ~1 req/mecz/dzień.
  - **Sofascore** (`6b3b2bfd1`, 06-20) — 2. fallback, `sofascore_odds.py`. Obecnie 403
    anti-bot (dotyczy też form_scraper) — działa tylko gdy AF nie ma meczu I 403 ustąpi.
  - +42 testy (AF parsing/fixture-match + Sofascore + fallback order).
- **D2 — Auto-refit kalibracji co +30 settled** (`dd81d829b`, 06-21): `maybe_refit_calibration()`
  w evening_agent po `update_pending`; gdy settled - n_train ≥ 30 → `fit_calibrator()` +
  ostrzeżenie gdy krzywa płaska. Gate `CALIBRATION_ENABLED` zostaje u usera. Stan 06-20:
  58 settled, n_train=41 (delta 17 < 30 → następny refit ~88 settled). +5 testów.
- **D4 — backtest_engine USUNIĘTY** (`a7e845470`, 06-21) — patrz dług techniczny #4 wyżej.
- **D5 — Scal taski 08:00** (06-21, Task Scheduler, NIE w git): `--faza draft` zapisuje
  predykcje (`_auto_zapisz_backtest` bezwarunkowo) + kupony + system_paper + propozycje →
  no-faza `FootStats-DailyAgent` redundantny (robił ściśle mniej, bez enrichu). WYŁĄCZONY
  (Disabled w Task Scheduler). 08:00 = tylko Draft, 11:00 Final, 23:00 Evening.
- **D7 — 15.7 weryfikacja czatu Telegram (nonce)** (`4cbd01d58`, 06-21): `POST /telegram/link/start`
  generuje nonce (TTL 15min), webhook `/start <nonce>` wiąże zweryfikowany chat_id (przed
  gate'em admina), jednorazowy. Migracja kolumn + 9 testów. `set_telegram_chat_id` deprecated
  (fallback).
- D3 (Cel B bug 2 — Groq selekcja) i D8 (JDG/prawnik) NIE zrealizowane — patrz `TODO.md`.

### TECHNICZNE / SECURITY (06-21)
- **Sofascore stealth** (`a5af86ecf`, security fix `d085b5815`): no-dep ukrycie
  `navigator.webdriver`/AutomationControlled vs 403. `--no-sandbox` usunięty po review MEDIUM
  (sandbox Chromium przy obcym JS) — stealth działa bez niego. NIE gwarantuje obejścia 403
  (AF /odds podstawą kursów); pomaga też form_scraper.
- **God-moduły rozbite (behavior-preserving):** `cli.py` 1112→773 (`210d9ec46`, spójne komendy/
  helpery → `cli_commands.py`); `analyzer.py` 930→793 (`6fa110177`, 4 czyste funkcje
  `_analizuj_forme`/`_wyciagnij_json`/`_deduplikuj_kupony`/`_wymusz_40pct` → `analyzer_helpers.py`).
- **daily_io — testy** (`3be80d1b9`): +10 testów `_zapisz_kupon_do_db` (mock DB, zero prod).
- Pre-existing bug udokumentowany (NIE naprawiony, poza scope): `cli.py::_analiza_kuponu` woła
  nieistniejące `_bzz_parse_prob` → `NameError` przy trafieniu w ev_ml.

### Weryfikacja unblocku (06-21, dry-run)
- Pipeline z AF fallback kursów → **System BY utworzył 15 kuponów** (przed fixami: 0) na realnych
  danych (USL/MŚ; kursy AF uzupełniły 7/18 brakujących; sygnał przywrócony bo kalibracja OFF).
  Cache AF pre-warmowany na run 08:00. Budżet AF 11/100.

### Suite
- **1177 passed / 4 skipped** (było 1076 na starcie serii commitów tej sesji).

## 2026-06-19

### Cel A — walk-forward offline, walidacja 10 lig
- Harness `scripts/run_walkforward_prod.py` (classic + Dixon-Coles + ensemble, devig kursów, no-lookahead, zapis `data/walkforward.db` — NIE Neon).
- Cache rozszerzony 5→**10 lig** (32 400 meczów): +ITA Serie A, +FRA Ligue 1, +AUT, +BEL, +SCO.
- **Werdykt 10 lig (out-of-sample, n=25 738):** dixoncoles **51.3%** > baseline 49.6% > poisson_only 48.1%. DC +1.7pp — generalizuje (NED było +1.9pp).
- Kalibracja **MONOTONICZNA** na wszystkich 10 ligach: 37.5→43.2→46.4→58.8% (pasmo 65%+ = strefa zakładów). Per liga (DC): NED 54.9, SCO 54.8, ENG 53.4, ITA 53.1, GER 51.5, ESP 51.2, BEL 50.4, FRA 49.8, AUT 47.8, POL 44.6.
- Fix kodów lig BEL/SCO: format sezonowy B1/SC0 zamiast `/new/` (404) — `c43e0bc3d`.

### Cel B — root cause live ≪ offline (częściowy)
- **bug 1 NAPRAWIONY** (`072ee9035`): `quick_picks` nie budował klucza `pred` → confidence leciało na Groq fallback (overconfident) zamiast prob modelu → inwersja kalibracji live. Fix: `wyniki` dostaje `pred` dict (p_wygrana/p_remis/p_przegrana/btts/over25/under25).
- bug 2 (otwarty, w TODO): `ai_tip` = selekcja Groq (44% remisy, 12.5% wyjazdy hit) zamiast argmax modelu.

### Cel C — Dixon-Coles w produkcji
- Wpięty za flagą `USE_DIXON_COLES` (default ON, env-toggle), `W_BAYESIAN=0.5`. 8 zadań TDD: `b42fd8043`, `ff0da87b5`, `b0e307e94`, `a15b616f5`, `f14255824`, `4e96110d5` (merge `b0a83d8fd`).
- `blend_dixon_coles` (poisson_bayesian): remap pa→pp, blend nad pw/pr/pp, bt/o25 nietknięte, graceful (DC None → classic). Wspólna funkcja z `wf_harness` (parytet prod↔harness).
- Smoke A/B NED: DC 55.2% > baseline 54.0%. Weryfikacja 10 lig po merge = identyczna z przed-merge (lewar nietknięty przez refactor).
- E2e test regresji wiringu (`4cd677820`, merge `e1b8f8809`) — łapie usunięcie wpięcia (dowiedzione RED).
- Code review: `footstats-reviewer` APPROVE z uwagami (0× P1/P2), `footstats-data-guard` SAFE. P3 #1 (luka testu wiringu) naprawiona e2e testem.
- Suita: **1078 pass** / 4 skip.

### Sprzątanie audytu + wpięcia (sesja 06-19 wieczór)
- **Bug 3 (mock leak) — potwierdzony naprawiony:** `coupons.py:_fallback_predictions` (24-31) — mock tylko `DEMO_MODE==1`, inaczej pusta lista; wszystkie 3 ścieżki fetch (brak klucza / pusty wynik / wyjątek) przez fallback. Realny user nie widzi już FAKE meczów (Legia/Lech/Ajax).
- **`waliduj_df_wyniki` — potwierdzony wpięty:** data-quality check przed predykcją (`quick_picks.py:73-74`).
- **`bezpieczny_budget_use` — WPIĘTY** (`25f6bc92a`): swap z `af_budget_use` w `api_football.py:_get`. Typed `BladBudzetu` zamiast `RuntimeError` + pełne logowanie budżetu. Ten sam plik/schema/progi (`cache/api_football/af_budget.json`, 100/5/20) → zero rozjechania liczników. Fallback do wygasłych danych cache zachowany. TDD + suita 1079 pass / 4 skip.
- Uwaga: `af_budget_use` (cache.py) jest teraz martwy w prod (callery tylko w testach) — kandydat do usunięcia osobnym taskiem.

### Zespół subagentów
- Dodany `footstats-scribe` (kronikarz: sesja → TODO/CHANGELOG/STATUS + commit, archiwizuje zamiast kasować).
