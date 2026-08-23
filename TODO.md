# FootStats TODO — Lipiec 2026

> **🎯 PIVOT 2026-07-06:** zero monetyzacji/użytkowników → **czysta predykcja do doskonałości**. Strategia + 16 pomysłów → **`docs/PREDICTION_ROADMAP.md`**. Empiria: static value-betting na publicznych danych OBALONE (nie bije rynku O/U ani 1X2). Kierunek: **ścieżka A kalibracja** (best predyktor, metryka log-loss/Brier) lub **ścieżka B edge informacyjny** (player-availability delta/live/CLV). P3 monetyzacja → ARCHIWUM.
>
> **🔧 NAPRAWIONE 07-06 (największy lever):** audyt 104 settled — Groq nadpisywał model i psuł (1X2 model argmax 60% vs Groq 48%, +12pp). Fix: `GROQ_TIP_OVERRIDE` flip ON + threshold 33 (1X2) + 45 (O/U/BTTS `koryguj_tip_ou_btts`). **LLM (llama-3.1-8b) odsunięty od WSZYSTKICH picków → tylko analiza/podsumowania.** Model wybiera. TODO: zakładka GUI "analiza LLM"; rozważyć GROQ_MODEL=70b (reasoning). Inne dławiki: 65% predykcji bez modelu (off-season egzotyka/WC → LEAGUE_GATING celuje w złe ligi), confidence odwrócony (80%+→19%, nie włączać selekcji).

> **🎯 KIERUNEK 2026-07-21:** produkt = **dziennik kuponów + śledzenie postępu ludzi** (nie tylko surowa predykcja). NIE bukmacher, **zero obsługi pieniędzy** (jednostki, nie PLN przez nas). Predykcja = sygnał zaufania w dzienniku, nie sprzedawany edge. Plan → sekcja `📓 DZIENNIK KUPONÓW` niżej. Omija KILL rady ROAST (dziennik ≠ konkurent devigu rynku).

> **🎯 KIERUNEK 2026-07-27:** produkt zostaje na **użytek prywatny + beta-testerzy (znajomi)**. Priorytet = **żeby bot się uczył** (pętla predykcja→settle→kalibracja→RAG). Zero monetyzacji, zero publicznego launchu. Plan wykonawczy → sekcja `🎯 PLAN P0-P3` niżej.

**Aktualizacja:** 2026-08-14 · v3.4-stable
**Accuracy (live, `model_log` 13.08):** **poisson-dc 65.2%** (15/23) · bzzoiro-ml 50.0% (41/82) — próba mała, ale poisson-dc realnie gra i prowadzi
**Accuracy (offline):** Brier 0.6064 po fiksie rozdzielczości (było 0.6454); rynek 0.5912 — **wciąż nad nami**
**Cel M1:** 55% win rate (mierzony na 1X2 — **do rewizji**, patrz werdykt per rynek) · **Suite:** 4375 testów
**LIVE:** pipeline **PC-off w chmurze** — Cloud Run Jobs (final 11:00 + evening 23:00) + Scheduler (draft 07:30, settle 06:00/21:30). Szczegóły → `docs/cloud_migration.md`.
**⚠️ INCYDENT 27.07 (naprawiony):** redeploy zgubił env Cloud Run (`JWT_SECRET` itd.) → login zwracał 500 udający „złe hasło". Fix: rev 00313-mf5 + malformed-hash guard (401 nie 500) + `/mcp` off w prod + CD re-asertuje krytyczne sekrety + LoginView rozróżnia błąd serwera/limit/sieć od złych danych. Audyt auth: 6 znalezisk, rdzeń szczelny.
**⚠️ INCYDENT 14-20.07 (naprawiony 07-20):** potrójna awaria — Neon quota-block → **DB = Supabase free** (session pooler); image jobów bez `footstats.data` (`.gcloudignore` fix); kupon=None crash. **Luka w danych 14-20.07** (zero predykcji/settled). Dane 1-17.07 uwięzione w Neonie do **1.08**. Szczegóły → `CHANGELOG.md` 07-20.
**Zbudowane flag-OFF (flip po walidacji):** `SELECTION_MIN_CONF` (#1) · `LEAGUE_GATING` (#2). Już LIVE: `ENSEMBLE_MARKET_WEIGHT=0.70` (reweight ku rynkowi).

> **📦 Ukończone → `CHANGELOG.md`.** 23.08 przeniesiono stamtąd 40 zamkniętych pozycji
> (729 → 403 linie). Ten plik trzyma **wyłącznie to, co otwarte** — jeśli szukasz, jak coś
> zostało naprawione, szukaj w CHANGELOG-u albo w `git log`.

---

## 🎯 PLAN P0-P3 — PĘTLA UCZENIA (2026-07-27, DO WYKONANIA)

> **Cel nadrzędny:** bot ma się **uczyć**, a nie tylko generować. Dziś pętla jest przerwana w trzech miejscach naraz: gra nie ten model, nie ma danych, RAG dostaje puste faktory.
> **Kolejność usera: A → C → B.** Wszystko model-critical → walk-forward + zgoda usera przed każdym flipem.

| # | Zadanie | Kod | Blokada | Status |
|---|---------|-----|---------|--------|
| **P0** | **Model musi realnie grać live** — parquet w obrazach jobów i API → Poisson-DC zamiast `bzzoiro-ml` | **A** | — | ✅ **13.08** — `poisson-dc` 65.2% (15/23) w `model_log` |
| **P1** | **Pętla settle→kalibracja** — `calibration_monitor.py` + `flip_advisor` co 2-3 dni → progi flipów | — | brakuje **7** rozliczonych poisson-dc do progu 30 | ⏳ **JEDYNA ŻYWA BLOKADA** |
| **P2** | **Więcej danych → lepsze λ** — backfill Neon→Supabase | **B** | — | ✅ **14.08** — backfill był już zrobiony, reszta danych odpuszczona |
| **P3** | **RAG feedback domyka sygnał** — puste `factors` | **C** | — | ✅ **13.08 NIE bug** — wąskie gardło = liczba predykcji |

> Szczegóły zamkniętych P0/P2/P3 → `CHANGELOG.md` (13-14.08).
> Zostaje z P3 do zapamiętania: TWIERDZA wymaga serii ≥5 (`FORTRESS_MECZE`), a na losowej próbce
> 300 meczów tagi zapalają się w 31.7% — mechanizm żyje, po prostu potrzebuje wolumenu.

---

## 📓 DZIENNIK KUPONÓW + POSTĘP LUDZI (kierunek 2026-07-21)

> **Cel:** produkt = miejsce gdzie ludzie zapisują swoje kupony (obstawione GDZIE INDZIEJ), a system podsumowuje zysk/stratę i śledzi postęp w czasie. Predykcja modelu = sygnał obok wyboru usera. **Zero obsługi pieniędzy, nie bukmacher.**
> **Dlaczego to żyje (a "best predyktor" nie):** dziennik NIE ściga się z devigiem rynku — wartość = rekord, dyscyplina, accountability, ranking grupy. Rada ROAST zabiła "predyktor jako produkt", nie "dziennik z predykcją jako feature".

### Fundament (JUŻ istnieje — nie budować od zera)
- `core/coupon_tracker.py` — CRUD kuponów per `user_id` (`save_coupon`/`update_coupon_status`/`get_active_coupons`/`get_coupon_legs`/`promote_to_active`).
- `core/coupon_settlement.py` — auto-rozliczanie po wyniku meczu · `core/bankroll.py` — saldo jednostek · `core/system_coupons.py` · `core/clv_tracker.py`.
- GUI: `HistoryView`+`HistoryCouponRow` (historia), `LeaderboardView` (ranking ludzi), `DashboardHome`, `LoginView`/multi-user, `AdminPanelView`, `SettingsView`.
- Dowód działania: 10 kuponów Admin_JG rozliczone (CHANGELOG 07-03/04).

### Luki do domknięcia (bite-size, TDD + design-system, w tej kolejności)

### 🔗 Match-linking (fundament J6+J4c, kierunek 2026-07-21) — DONE
> Free-form mecz → nasze dane. Odblokowało oba: podgląd sygnału (J6) + auto-settle (J4c).

### Silnik sygnału (dotychczasowa praca = wartość dziennika)
Kalibracja/selekcja (P0/P1 niżej) NIE jest już celem samym w sobie — to **feature zaufania w dzienniku**: uczciwa pewność, której blind-tipster nie da. P0 walidacja dalej ważna, ale jako **jakość sygnału**, nie jako "bicie rynku".

### Non-goals (twarde — blok scope-creep)
- ❌ Płatności / wypłaty / realny PLN przez nas — tylko **jednostki**. ❌ Przyjmowanie zakładów (nie bukmacher). ❌ Sprzedawanie edge / ściganie rynku jako produkt.

### 🐞 Znalezione przy J1-J4 (osobne taski, NIE blokują dziennika)
- **CSS cascade-layer bug (app-wide):** `gui/src/index.css` `button {color:inherit;background:transparent}` jest POZA `@layer` → w Tailwind v4 bije utility-klasy, więc `text-*`/`bg-*` na KAŻDYM `<button>` się nie stosują (przyciski bezbarwne). Obejście w dzienniku: inline `style var()`. Fix globalny = owinąć reset w `@layer base` + pełna regresja wizualna przycisków.
- ~~**Auto-settle hybryda „co mamy — my":**~~ ✅ ZROBIONE (match-linking A+C wyżej). Zostaje decyzja enablement `/cron/settle-manual`.
- **Testy widzą prod przez `.env`:** `config.py` robi `load_dotenv` → `DATABASE_URL` z `.env` (dziś Supabase, nie martwy Neon). Guard w `tests/conftest.py` **przerywa całą suitę**, gdy URL wskazuje prod — to zadziałało i zadziałać ma. Zostaje uciążliwość: na Windowsie `$env:DATABASE_URL=""` kasuje zmienną zamiast ustawić pustą, więc guard i tak czyta `.env`. Docelowo marker `@pytest.mark.integration` + test-DB; doraźnie patrz „Dług testowy" w Następnych krokach.

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M1** | 55% win rate | 🔴 W toku | ~88 świeżych settled → selekcja 65%+ conf (offline=68%) + gating lig |
| **M2** | 60% win rate | ⏸️ | Po M1 — tuning |
| **M3** | 65% selected | ⏸️ | Po M2 |
| **BETA** | Testerzy | ⏸️ | Po M1 |

---

## 🔬 WALIDACJA — szczegóły P1/P2 (blokuje M1, PASYWNE — NIE dokładaj zmian λ)

> Root-cause'y Cel B usunięte. Kalibracja OFF (`CALIBRATION_ENABLED`), auto-refit czeka na dane (D2).
> STOP na nowe λ aż zbierzemy świeże settled — zmiana teraz zaciemnia czy fixy działają.
> **Zbieranie leci PC-niezależnie** (cloud draft 07:30 + settle) — brak wąskiego gardła danych.

- [ ] **Co kilka dni:** `python scripts/stan_uczenia.py` (read-only) — licznik do werdyktu, teraz z `model_log`. Uzupełniająco `scripts/calibration_monitor.py` + flip-advisor (`core/flip_advisor.py`): rekomenduje flip `SELECTION_MIN_CONF` i ligi do `LEAGUE_GATING` (<50%, n≥8).
- [ ] **D3 — pełna decyzja a/b/c** (próg guardu, czy argmax na stałe) — po ~20 ŚWIEŻYCH settled z zapisanym prob. Zwaliduj że guard pomaga, dostrój próg. (D3 cz.1+2 prob+guard ZROBIONE 06-22.)
- [ ] **Po ~88 settled → D2 auto-refit sam** (delta +30 od n_train); gdy krzywa zdrowa → włącz `CALIBRATION_ENABLED=1`.
- [ ] **🆕 Dług testowy:** `config.py` robi `load_dotenv(override=True)` → testy integracyjne biją w `DATABASE_URL` z `.env`.
  - ✅ **Zrobione 07-29:** `DATABASE_URL` wskazuje już Supabase (prod), stary Neon zachowany jako `DATABASE_URL_NEON` (źródło backfillu). Naprawia narzędzia/skrypty diagnostyczne, które dotąd trafiały w martwego Neona.
  - ⚠️ **KOREKTA:** to NIE jest fix długu testowego. Część tych testów **pisze** (`test_auth` zakłada userów, `test_settle_*` zmienia statusy kuponów) — uruchomienie ich teraz celowałoby w PRODUKCJĘ. Suitę dalej odpalamy z `DATABASE_URL=""` (guard sieciowy w `conftest`).
  - Fix docelowy bez zmian: marker `@pytest.mark.integration` + oddzielny test-DB.

---

## 🟠 M1 LEVERS — szczegóły P1 (zbudowane flag-OFF → flip po ~88 fresh settled)

> Kalibracja: **65%+ conf = 68%** (robustnie). Per-liga: NED 56/SCO 55/ITA 54/ENG 54 ≥M1; POL 44/ESP 49/FRA 49 w dół.
> Wniosek M1 (zgodny z Cel B): model OK, droga = **SELEKCJA** (65%+ subset) + **gating lig**.

- [ ] **Flip `SELECTION_MIN_CONF=65`** po walidacji — podnosi próg `najlepszy_typ` do pasma high-conf. Zwaliduj że live trzyma kalibrację. (Wpływa na System paper + cloud-draft.)
- [ ] **Flip `LEAGUE_GATING=1`** po walidacji — odrzuca `LIGI_SLABE` (POL/ESP/FRA <50%), faworyzuje NED/SCO/ITA/ENG.
- [ ] **Monitoruj reweight 30/70** (`ENSEMBLE_MARKET_WEIGHT=0.70`, rev 00274 LIVE) — calibration check (log-loss) na świeżych settled. Escape-hatch: zmień/usuń env.
- [ ] (opcj.) re-optymalizacja per-league wag ku rynkowi (`ensemble_optimizer`).

---

## 🟡 SIERPIEŃ (restart lig klubowych) — okno wykonania P0/A

> Teraz off-season = mecze kadr (WC) → Poisson nie ma historii reprezentacji (dataset = ligi klubowe). Realny zysk dopiero na restart lig.

---

## 🗄️ MONETYZACJA / LAUNCH (ARCHIWUM — pivot 2026-07-06, zero monetyzacji)

> Odłożone bezterminowo. Focus = predykcja (`docs/PREDICTION_ROADMAP.md`). Zostawione jako referencja gdyby wróciło.

- [ ] **D8 — prawnik (ToS bukmacherów) + JDG (CEIDG)** — wstrzymane (koszt/ryzyko). Wrócić po walidacji.
- [ ] **Resend** FROM `onboarding@resend.dev` (test) → zweryfikowana domena przed prod. (Reset hasła + Resend wpięte ✅.) Wymaga env `FRONTEND_URL`.
- [ ] **Płatności** (Lemon Squeezy/Paddle, po JDG): cennik+auto-renewal, webhooks, email potwierdzenie/faktura, upgrade/proration.
- [ ] **Faktura** (po płatnościach). Custom domain (opcjonalne).

---

## ⚪ OPCJONALNE

- [ ] **Scrapery — ocena per-stabilność/anti-bot:** Soccer24 (klon FlashScore, skip), Meczyki/LiveScore (anti-bot), Transfermarkt (squad/value nie wyniki). 4 źródła już wpięte (AF/football-data.co.uk/FlashScore/TheSportsDB).

---

## 🚫 Zbadane → odrzucone (NIE wracać)

- **ImportanceIndex** (crude ±20%): A/B −0.1pp, high-stakes −0.59pp → ślepa uliczka. `core/standings.py` zostaje jako CECHY do ML.
- **LightGBM / własny model ML:** 51.6% (z kursami) < rynek 53.1% < baseline. Rynek nieprzekraczalny (jak literatura). `core/ml_features.py` zostaje jako infra. Jedyny owoc = reweight ensemble ku rynkowi.
- **Schedule-adjusted ratings** (M1 lever #5): offline A/B +0.20pp (szum, se~0.92pp), +57% wolniej. Flag `SCHEDULE_ADJUSTED_RATINGS` zostaje OFF; kod+7 testów jako infra.
- **FBref jako źródło xG** (sprawdzone 2026-07-29): HTTP **403 z normalnym User-Agentem**, a przez headless chromium wraca **strona challenge Cloudflare**. Przepuszczenie wymagałoby stealth/anti-detekcji — wysoki koszt utrzymania, kruche. NIE wracać bez nowego powodu.
- **StatsBomb open-data jako źródło xG** (sprawdzone 2026-07-29): API działa bez anti-bota, ale **nie nadaje się do tego projektu**. Twarde liczby: `matches.json` **nie zawiera xG** (tylko wyniki) — xG jest wyłącznie w `events/{match_id}.json` po **~2.6 MB na mecz**. Pokrycie to wyłącznie historia (najnowsze: Bundesliga 2023/24 = **34 mecze**, La Liga 2020/21, MŚ 2022), **zero sezonu bieżącego** → nie nakarmi live λ. Do walidacji offline próbka o 3 rzędy wielkości za mała (walk-forward chodzi na 25k+ meczów). Koszt ~90 MB za jedną niepełną konkurencję.

---

## 🚨 AWARIA 16-22.08 — Groq wycofał model (naprawione 22.08)

**Potok stał 6 dni przy `exit=0`.** `llama-3.1-8b-instant` zniknął z API Groqa →
404 NotFoundError → brak odpowiedzi → zero predykcji. Dostawca nie ostrzegł.

### ⚠️ ZNALEZIONE PRZY OKAZJI — Groq zmyśla pewność
Zmierzone (3 próby na zestaw, `gpt-oss-120b`):

| dane wejściowe | wynik |
|---|---|
| żaden rynek nie sięga 60% | `top3=0` · `top3=3 [68,62,65]` · `top3=3 [71,68,66]` |
| rynki powyżej 60% | `top3=3` za każdym razem |

Gdy dane nie dają żadnego typu powyżej progu, model **albo poprawnie zwraca pustkę,
albo wymyśla pewności** (68%, 71%) nieistniejące w danych. Losowo, ~1 na 3.

**To NIE jest groźne dla typów** — potok i tak nadpisuje `pewnosc_pct`
prawdopodobieństwem modelu (`_nadpisz_pewnosc_modelem`), podmienia kurs na realny
(KROK 4) i nadpisuje tip argmaxem (`GROQ_TIP_OVERRIDE`). Groq jest tylko warstwą
opisu, nie decyduje.

**Groźne jest co innego:** gdy Groq zwróci pustkę, przebieg zapisuje ZERO predykcji —
mimo że Poisson policzył je niezależnie. Potok jest uzależniony od LLM-a w tym,
żeby *wypisał listę*, choć typy powstają bez niego.

### 🔎 ZNALEZIONE NA PIERWSZYM PRZEBIEGU PO A1 (23.08, `footstats-final-pptp4`)

Przebieg planowy 11:00: 32 kandydatów → 14 po filtrach → Groq odpowiedział poprawnie
→ **5 predykcji w bazie**. A1 słusznie się nie uruchomił. Wyszły trzy inne rzeczy.

- [ ] **A4 — 1 martwy wiersz z 23.08 został w bazie** (`2 (wygrana gościa)`, nie rozliczy
  się nigdy) plus 3 wiersze z `odds_verified=0`. Nowe już nie powstaną, ale te
  istnieją. Do decyzji: zostawić jako ślad, czy posprzątać (operacja na prod DB).

### Sprawdzone i odrzucone
- **Podział promptu na warstwy** (reguły w wiadomości systemowej, potem kontekst →
  mecze → polecenie): A/B po 3 próby. Tokeny wejścia 1285 vs 1289, ta sama
  częstość pustego `top3`. **Bez mierzalnej korzyści** — nie wdrażać.
- `qwen/qwen3.6-27b` — wypluwa `<think>` do treści, parser nie ma szans.
- `groq/compound-mini` — działa (top3=3), ale zjada 3423 tokeny zamiast 1550.
  Rezerwa: 70K tok/min i brak dziennego limitu tokenów (za to 250 req/dzień).

## 🔍 AUDYT 2026-08-17 — 23 znaleziska (0 krytycznych)

> Pełny raport z dowodami: artefakt „Audyt FootStats". Poniżej lista do odhaczania.
> Zakres: 172 pliki .py (37 636 linii), 3381 linii JSX, 4463 testy / **80% pokrycia**, prod DB + GCP.

### 🔴 Wysokie
- ~~**F7 — opis pierwotny**~~ (zostawiony dla kontekstu):
  1. **Baner twierdzi**: „używamy NIEZBĘDNYCH plików cookie / local storage (np. token sesji)".
  2. **Realnie**: `main.jsx:13-14` montuje `<Analytics />` i `<SpeedInsights />` (Vercel) **bezwarunkowo**. Dowód: przy `fs_cookie_consent = null` i widocznym banerze oba skrypty są już w DOM (`/_vercel/insights/script.js`, `/_vercel/speed-insights/script.js`).
  3. **Polityka prywatności** nie wspomina o analityce ani słowem (jest tylko „cookies").
  - Flaga `fs_cookie_consent` jest **czytana wyłącznie przez sam baner** — przycisk „Rozumiem" nie włącza ani nie wyłącza niczego.
  - Pod RODO/ePrivacy: cookies *ściśle niezbędne* zgody NIE wymagają, ale analityka **wymaga** i nie może odpalać przed zgodą. Obecny stan jest gorszy niż brak banera — to komunikat, który nie opisuje tego, co aplikacja robi.
  - **Do decyzji:** (A) usunąć Vercel Analytics — najprościej i zgodne z kierunkiem „prywatny użytek + znajomi", wtedy treść banera staje się prawdziwa i wystarczy jednolinijkowa notka zamiast paska; (B) bramkować analitykę zgodą i dopisać ją do polityki; (C) zostawić i tylko poprawić treść — najsłabsze, bo dalej brak bramki.
- [ ] **F8 — link do polityki prywatności zaszyty na sztywno** jako surowy adres Cloud Run (`CookieConsent.jsx:21`), zamiast ścieżki względnej lub zmiennej środowiskowej. Po zmianie hostingu link umrze po cichu.
- [ ] **F10 — sześć klikalnych `<div>` do konwersji.** `HistoryCouponRow` (rozwijanie wiersza), `LeaderboardView` (wiersz rankingu), `ui.jsx`, `CouponWizard` (3×). Niedostępne z klawiatury i bez roli dla czytnika. Każdy wymaga `role="button"` + `tabIndex` + obsługi Enter/Spacji albo przepisania na `<button>`. Próg w strażniku obniżyć po każdej konwersji.
- [ ] **F11 — reszta widoków bez audytu dostępności.** Zrobione: `LoginView`, `ManualCouponForm` (zamykanie), `App` (menu). Zostają: `SettingsView`, `AdminPanelView`, `CouponWizard`, `StatsView`, `LeaderboardView`, `TerminarzView`, `MatchAnalysisView` — głównie powiązanie etykiet z polami.
- [ ] **F9 — inline'owe kolory na przyciskach to już tylko pozostałość.** Były obejściem buga CSS naprawionego w F1. Trzy miejsca: `HistoryCouponRow.jsx`, `StatsView.jsx`, `ProgressChart.jsx` — można uprościć do zwykłych klas Tailwinda. Wymaga przejścia po wszystkich trzech naraz z regresją wizualną. Komentarz w `HistoryCouponRow` już nie kłamie (zaktualizowany).
- [ ] **M5 — jedyna zmiana wsparta danymi: wyłączyć BTTS z puli selekcji.** Symulacja BEZ BTTS dała −10,7%, a produkcja z BTTS −13,5% ogółem przy **−28,2% na samym BTTS**. Zastrzeżenie: to inne okresy i próby, więc nie jest to porównanie 1:1 — przed flipem policzyć na wspólnym oknie.

### 🟡 Średnie
- [ ] **D2 — `/cron/settle-manual` NIE jest w Schedulerze.** ⚠️ **Sprawdzone na sucho na produkcji 17.08: wpięcie go dziś NIC BY NIE DAŁO.**
  - Dry-run zwrócił `{"settled": 0, "skipped": 1, "errors": 0}` — endpoint działa, znalazł jedyny kupon manualny (#149) i **pominął** go.
  - **Powód:** `settle_manual_coupons` rozlicza wyłącznie z NASZYCH `predictions`, a dla meczu Yunnan Yukun – Dalian Yingbo (15.08) predykcji **w ogóle nie ma** — przebieg o 11:00 tego dnia padł na parsowaniu JSON-a od Groqa. W bazie jest tylko Yunnan Yukun – Chengdu Rongcheng z 08.08, czyli inny mecz.
  - **Wniosek:** samo zadanie w Schedulerze jest bezpieczne (0 błędów) i tanie, ale rozlicza tylko mecze, które sami typowaliśmy. Reszta zostaje na ręczne oznaczenie w GUI — i tak działa zaprojektowana hybryda („co mamy = my, reszta = user ręcznie").
  - ⏳ **Decyzja usera:** wpiąć do Schedulera (dry-run pokazuje, że bezpieczne) czy zostawić trigger ręczny, skoro dziś i tak nie ma czego rozliczać.

### 🔴 ZNALEZIONE PRZY OKAZJI — rozliczanie stało 8 dni

Historia z logów (`cron_settle`), pełna sekwencja:

| data | wynik |
|---|---|
| 15.08 21:30 | `settled 20, partial 24` — działało |
| 16.08 06:00 → 23.08 | `settled 0` **za każdym razem** |

Liczba PARTIAL spada wyłącznie przez VOID po 10 dniach, nie przez rozliczenia.
**Dwie przyczyny po kolei:**
1. **16.08:** `API-Football: Your account is suspended` — konto zawieszone.
2. **23.08:** konto **znów działa** (`Free plans do not have access to this date`),
   ale kupony zestarzały się w międzyczasie poza horyzont obu źródeł.

- [ ] **D7 — 21 kuponów z 14-15.08 jest nie do odzyskania** z darmowych źródeł
  (duńska, japońska, chińska liga + angielskie niższe — poza pokryciem football-data,
  poza oknem AF, poza 7 dniami FlashScore). Zejdą przez VOID 24-25.08. Do decyzji:
  pogodzić się ze stratą 20 punktów paper-tradingu czy szukać źródła z historią.

- [ ] **D5 — kupony na mecze BEZ naszej predykcji nie rozliczą się nigdy.** Wyszło przy D2. `settle_manual_coupons` czyta tylko `predictions`, a `coupon_settlement` dla kuponów AI ma osobną ścieżkę z czterema źródłami wyników (`_find_leg_result`). Dziennik użytkownika nie korzysta z żadnego z nich. Do rozważenia: dopuścić `_find_leg_result` również dla kuponów `manual` (kosztuje zapytania do API-Football, więc pod flagą).
- [ ] **D3 — 231 predykcji z `odds_verified=0`** (kurs od Groqa) → ROI/CLV z historii nic nie znaczą. Decyzja: backfill kursów czy trwałe wykluczenie z raportów.
- [ ] **I2 — licznik tokenów myli się 2×.** Heurystyka 1,4 znaku/token vs realne 2,86 (1338 vs **655** tokenów na szkielecie) → prompt bywa przycinany bez potrzeby. Fix: `tiktoken` — **wymaga `pip install`, czyli zgody**.
- [ ] **J1 — połowa `except` milczy.** 271 z 546 bez logu i bez `raise`. Strażnik w testach pilnuje SZEROKOŚCI (`except Exception`), nie milczenia. Fix: drugie kryterium w tym samym strażniku.
- [ ] **J2 — mypy sprawdza 1 katalog** (`scrapers/sources/`) ze 172 plików.
- [ ] **J3 — schematy testowe dublują produkcyjny** (`test_backtest_db`, `test_evening_agent`) — bolało przy migracji 12 i 13. Fix: jedna fikstura z `init_db()`.
- [ ] **M2 — trzy flagi czekają na walidację:** `SELECTION_MIN_CONF=65`, `LEAGUE_GATING=1`, `BTTS_TWO_WAY`. Wszystkie blokuje ten sam brak danych.
- [ ] **M3 — cel M1 mierzy rynek, który przegrywa.** „55% win rate" liczone na 1X2, gdzie przy niezgodzie rynek 42,9% vs model 29,8%. Rozważyć ROI zamiast trafności.

### ⚪ Niskie
- [x] ✅ **B6 — ZROBIONE 23.08. Walidacja identyfikatorów przed sklejeniem SQL.**
  `player_db.py` `ALTER TABLE ... ADD COLUMN {col} {typ}` musi iść f-stringiem —
  SQLite **nie pozwala parametryzować identyfikatorów** (`?` działa dla wartości,
  nie dla nazw kolumn), więc parametryzacja jest tu fizycznie niemożliwa i jedyną
  obroną jest walidacja. `_sprawdz_identyfikator` przepuszcza wyłącznie nazwę
  pasującą do `^[a-z_][a-z0-9_]*$` i typ z zamkniętej listy `{REAL, INTEGER, TEXT}`.
  Sprawdzane są **oba** pola — walidacja samej nazwy zostawiałaby drugą połowę
  zapytania otwartą. +21 testów, bandit czysty.
  **Uczciwie: to nie była podatność.** `_OPTIONAL_COLS` to stała w module, nie dane
  z zewnątrz — nic nie dało się wstrzyknąć. Zmiana zamienia „bezpieczne, bo nikt
  tego nie zmienił" na „bezpieczne, bo sprawdzane", co zaczyna mieć znaczenie
  dopiero w dniu, w którym ktoś weźmie listę kolumn z konfiguracji albo ze źródła.
  Jeden z testów sprawdza SKUTEK, nie sam wyjątek: po próbie wstrzyknięcia tabela
  `player_stats` ma dalej istnieć.
- [ ] **D4 — `model_log` śledzi tylko argmax 1X2** → rynków golowych nie zweryfikujemy live. Dopisać `p_over25`/`p_btts` + wynik.
- [ ] **F4 — PWA nie działa, ale NIE dlatego, że jej nie ma.** Backend serwuje OBA:
  `/manifest.json` (`main.py:455`) i `/sw.js` z pełnym cyklem install/activate/fetch.
  Problem jest węższy: **front ich nie podłącza**. W `gui/index.html` nie ma
  `<link rel="manifest">`, a w całym `gui/src` nie pada ani razu `serviceWorker`.
  Kod jest napisany i osierocony, więc fix to dwie linijki (link + rejestracja),
  nie `vite-plugin-pwa` od zera.
  ⚠️ **Uwaga o duplikacie (23.08):** „odkryłem" to ponownie i dopisałem drugi wpis,
  choć audyt 17.08 zapisał to samo. Wpisy scalone tutaj; stary miał nieaktualny
  numer linii (`main.py:411`). Ostrzeżenie na przyszłość: przed dopisaniem
  „korekty" sprawdź, czy korekta już nie istnieje.
- [ ] **F5 — `CouponWizard.jsx` 437 linii**, `SettingsView.jsx` 377 (limit 400).
- [ ] **I3 — brak Sentry na froncie** (backend ma).
- [ ] **I4 — `DATABASE_URL_NEON` wciąż w lokalnym `.env`** mimo porzucenia Neona.
- [ ] **I5 — rejestr obrazów puchnie: 79 GB (znalezione 23.08 przy I1).** `footstats-api`
  424 obrazy / 68,8 GB, `footstats-jobs` 45 / 25,9 GB. Darmowy limit Artifact Registry
  to 0,5 GB → ~0,10 USD/GB/mies. **Zrobione 23.08** (zmierzone przed/po):
  `footstats-jobs` 109 → **30** wpisów, atestacje 65 → **0**, bez taga 15 → **0**,
  25,9 → **20,1 GB**; `footstats-api` 430 → **419**, atestacje 6 → **0**, bez taga
  7 → **2**, 68,8 → **68,6 GB**. Razem skasowane 71 atestacji + 20 obrazów bez taga,
  **zwolnione 6,0 GB**. Polityka czyszczenia ustawiona w trybie **NA SUCHO**
  (`trzymaj 30 najnowszych` + `kasuj nieotagowane starsze niż 30 dni`).
  Uwaga operacyjna: `gcloud artifacts docker images delete` pisze „Delete request
  issued… done." na **stderr** i podnosi kod wyjścia — skrypt liczył 3 udane
  kasowania jako błędy. Sprawdzaj stan faktyczny (`describe`), nie kod wyjścia.
  **DLACZEGO NA SUCHO, a nie od razu na ostro:** Artifact Registry **nie widzi
  referencji Cloud Run**. Zmierzone: dwa obrazy API są nieotagowane, a mimo to
  wskazywane przez żywe rewizje (`:latest` przewędrował dalej, digest został) —
  reguła „kasuj nieotagowane" skasowałaby działający obraz. **W tym projekcie
  nieotagowany ≠ nieużywany.**
  **Zostaje do decyzji:** 68,8 GB obrazów API jest przypiętych przez **435 rewizji
  Cloud Run**. Zwolnienie ich wymaga skasowania najpierw starych rewizji, czyli
  świadomej rezygnacji z rollbacku do nich. Przed włączeniem polityki na ostro:
  przejrzeć log trybu suchego i skonfrontować listę z `gcloud run revisions list`.
- [ ] **I6 — każdy push na `main` przebudowuje obraz jobów (~570 MB), też przy zmianie
  wyłącznie dokumentacji.** Skutek uboczny I1: dziś commit czysto CI-owy (B9) odpalił
  pełny build z chromium. Do rozważenia `paths-ignore` na `*.md` — ale ostrożnie:
  filtr, który pominie zmianę w `src/`, przywraca dokładnie ten dryf między `main`
  a obrazem, który I1 likwidował.
- [ ] **J4 — bramka pokrycia 8 pkt pod stanem faktycznym.** Zmierzone **80%**, `--cov-fail-under=72` → można skasować 8 pkt i build przejdzie. Najsłabsze: `football_data.py` 21%, `flashscore_results.py` 42%, `utils/cache.py` 56%, **`utils/db.py` 69%** (warstwa dostępu do bazy).
- [ ] **J5 — 4 pliki > 800 linii:** `daily_agent.py` 1022, `superbet.py` 867, `coupons.py` 832, `analyzer.py` 814.

### 🛡️ Odporność na ataki — ZMIERZONA 17.08 (`tests/test_odpornosc_ataki.py`, 25 testów)

| atak | werdykt | dowód |
|---|---|---|
| **Wstrzyknięcie SQL** (`' OR 1=1 --`, `UNION SELECT`, `DROP TABLE`) | ✅ **odporni** | 14 ładunków × 2 pola → wszystkie 401. Ładunek trafia do bazy jako **parametr**, nigdy do tekstu zapytania |
| **Brute-force z jednego IP** | ✅ **blokowany** | 15 prób zgadywania → limiter ucina po 10. Ta sama odpowiedź dla złego hasła i nieistniejącego konta (brak enumeracji) |
| **Brute-force z wielu IP** | ✅ **naprawione (B7, 23.08)** | licznik `failed_attempts` + `locked_until`: po 5 błędach konto zamyka się na rosnące okno (1 → 15 min). Zablokowane konto **nie sprawdza hasła**, więc nie działa jak wyrocznia. Limit per-adres realnie działa od naprawy B2 |
| **Podrobiony token** | ✅ **odrzucany** | obcy sekret → 401; wygasły → 401; bez `uid` → 401 |
| **Skradziony token** | ⚠️ **luka B10** | działa z **dowolnego IP i przeglądarki** do wygaśnięcia; brak `jti`/powiązania z urządzeniem, więc kopii nie da się wykryć. **To NIE jest B1** — naprawa `token_version` unieważnia tokeny przy zmianie hasła, ale nie wykrywa kopii przy niezmienionym haśle |
| **Zmiana hasła po przejęciu konta** | ✅ **naprawione (B1, 17.08)** | `_uniewaznij_sesje` podbija `token_version` przy zmianie hasła ([auth.py:339](src/footstats/api/auth.py#L339)) i przy resecie ([auth.py:435](src/footstats/api/auth.py#L435)) — wszystkie wydane tokeny padają natychmiast |

- [ ] **B10 — token nie jest z niczym związany** (wydzielone z B1, 23.08). `token_version`
  unieważnia tokeny przy zmianie hasła, ale skradzionej KOPII przy niezmienionym haśle
  nie da się wykryć ani odciąć: brak `jti`, brak powiązania z urządzeniem/adresem.
  Do rozważenia: `jti` + lista unieważnionych, albo skrócenie życia tokenu + refresh.
- Trzy testy są celowo zielone WOBEC LUK (`test_BRAK_blokady_konta…`, `test_token_dziala_z_DOWOLNEGO…`, `test_zmiana_hasla_NIE_uniewaznia…`). Po naprawie **padną** — to ich zadanie: wymuszają aktualizację audytu zamiast cichego rozjazdu dokumentacji.

### ✅ Sprawdzone i w porządku
SQL parametryzowany (1 wyjątek wyżej) · JWT fail-closed · bcrypt+gensalt, min. 8 znaków w walidatorach ·
limity 10/5/60 na minutę · nagłówki bezpieczeństwa · CORS z jawnej listy (nie `*`) · `/mcp` off na prodzie ·
CI blokujące (ruff+bandit+pip-audit+coverage) · backup DB codziennie 07:00 · zero sekretów w kodzie ·
klikalne elementy to `<button>`, nie `<div>`.

---

## 📋 Następne kroki (zweryfikowane na produkcji 2026-08-14)

1. **Obserwować budżet API-Football.** 14.08 zjechał do **17/100** — nadrabianie zaległości kosztuje ~8 requestów na przebieg. Przy dwóch przebiegach dziennie może nie starczyć. Regulacja bez redeploya: `LIMIT_NADRABIANIA` (domyślnie 15).
2. **Dobić 7 rozliczonych poisson-dc** → próg 30 → `scripts/porownaj_modele.py` wydaje werdykt. Licznik: `python scripts/stan_uczenia.py`.
3. ✅ **Podzbiory BTTS i O/U rozbite 14.08** — żaden nie przeżył sprawdzenia poza próbą. Szczegóły niżej.
4. ✅ **Migracja 13 (`odds_verified`) WDROŻONA 15.08** — kolumna weszła przez CD (API rew. 00402), joby przebudowane osobno (digest z tagiem `89ae6a28`; dwa nowsze były bez tagu = atestacja BuildKita). **Do sprawdzenia po przebiegu 11:00:** czy pojawiają się wiersze `odds_verified = 1` i czy w logach nie ma WARNINGA „Uzgodniono kursy dla X z Y" (= rozjazd nazw między zapisem a weryfikacją).
5. **Kosmetyka:** usunąć `DATABASE_URL_NEON` z lokalnego `.env` (Neon zbędny; rotacja wymagałaby ich konsoli, brak `NEON_API_KEY`).

> Zamknięte 14.08 (szczegóły → `CHANGELOG.md`): rozjazd wag ensemble · `CRON_SECRET` → `secretKeyRef`
> · backfill Neon + wyłączenie wersji 1 sekretu `DATABASE_URL` · okno rozliczeń · lekcje RAG z trafień
> · diagnostyka blacklisty lig.

### 🎯 Werdykt per rynek (14.08, n=3586, 3 niezależne grupy lig) — TRZY RÓŻNE ODPOWIEDZI
| rynek | werdykt | dowód |
|---|---|---|
| **1X2** | 🔴 przegrany | ROI ~−20% przy każdej wadze; przy niezgodzie rynek 42.9% vs model 29.8% |
| **BTTS** | 🔴 **szkodliwy** | model 53.2% / Brier 0.2496 vs częstość bazowa 54.4% / 0.2480. „Zawsze BTTS tak" **bije model**. Grupa C: 50.5% vs 54.2%. Prod potwierdza: BTTS 18.2% (2/11) |
| **Over/Under 2.5** | 🟡 **jedyna nadzieja** | ROI przy 30/70: A **+9.2%** (106 zakł.), B −3.8%, C −15.5%, **razem −0.2%** (na zero PO podatku). Przy niezgodzie na ligach czołowych model **wygrywa 52.1% do 47.9%** |

**Wnioski do decyzji:**
1. ✅ **Hipoteza „model działa na specyficznych meczach" SPRAWDZONA 14.08 — nie potwierdza się.** Patrz sekcja niżej.
2. ⚠️ **+9,2% na ligach czołowych NIE replikuje się** — patrz sekcja niżej. Tę liczbę trzeba uznać za szum.
3. **`model_log` śledzi wyłącznie argmax 1X2** — rynków golowych nie da się dziś zweryfikować live bez rozszerzenia dziennika.

### 🔬 Test podzbiorów BTTS i O/U (14.08, n=15 460, 39 lig) — NIC NIE PRZEŻYŁO
Metoda: próba podzielona **po dacie**. Podzbiory szukane wyłącznie na starszej części
(DISCOVERY, 9226 meczów do 03.01.2026), liczone na nowszej (HOLDOUT, 6234), której szukanie
nie widziało. Bez tego każde dostatecznie drobne cięcie znajduje „przewagę" — tak powstają
strategie działające wyłącznie wstecz.

Wymiary cięcia: liga · pasmo pewności BTTS · suma λ (profil golowy) · λ słabszej strony ·
rozjazd z rynkiem · zgoda/niezgoda z rynkiem. Razem **52 podzbiory**.

| rynek | kandydaci na DISCOVERY | przeżyli HOLDOUT |
|---|---|---|
| **BTTS** | 5 (RUS +5.2pp, BEL +3.2pp, ENG-PL +1.9pp, rozjazd 3-6pp, BRA) | **0** |
| **O/U** | 2 z dodatnim ROI (+8.5%, +7.4%) | **0** |

Oba dodatnie ROI mieściły się w granicy błędu (±11,7pp i ±11,2pp przy 73 i 80 zakładach).
Na HOLDOUT: −6,1% i −4,2%.

**Ligi czołowe (te same 4 co wczoraj), test wczorajszego +9,2%:**
DISCOVERY **−11,4%** (55 zakładów) · HOLDOUT **+12,1%** (61 zakładów) — obie w granicy błędu
(±13,5 i ±12,8), **znak się odwraca**. Wczorajsze +9,2% na 106 zakładach to jedno losowanie
z tego rozkładu, nie przewaga. Lig dodatnich w OBU połowach: **0**.

**Co z tego wynika:** hipoteza „model działa na specyficznych meczach/drużynach, a średnia
to zaciera" została sprawdzona na 4× większej próbie i się nie broni — wzdłuż żadnego
z sześciu wymiarów. To nie zamyka tematu na zawsze (można próbować innych cech, np. formy
czy H2H), ale zamyka drogę „potnijmy istniejące predykcje na kawałki i znajdźmy dobry".

### 🎯 BTTS dwustronne (pomysł usera 15.08) — sygnał REALNY, ale nie bije rynku
**Diagnoza usera trafna:** ścieżka selekcji (`system_paper._ODDS_KEY`) zna wyłącznie
„BTTS" = TAK. Skoro BTTS pada w ~54%, model był strukturalnie wepchnięty w klasę
większościową i nie mógł zagrać tam, gdzie jest pewny, że gole po obu stronach NIE padną.
Wczorajszy werdykt „gorszy od stałej" był więc częściowo artefaktem pomiaru.
(`markets.py:92` ma „BTTS NIE" w katalogu BetBuildera — selekcja go nie widzi.)

**Sygnał istnieje i REPLIKUJE SIĘ** — krzywa monotoniczna w obu połowach:
`p_btts` 0-40% → BTTS pada 48.7% / 51.2%; 65%+ → **60.7% / 64.1%**.
Gra dwustronna przy marginesie 15pp bije stałą odpowiedź w obu połowach:
TAK +7.0/+8.4pp, NIE +6.3/+6.6pp.

**Ale przeciw rynkowi przegrywa** (rynkowe BTTS wyliczone z dopasowania λ do cen O/U,
bo kursów BTTS w datasecie nie ma): Brier model 0.2524/0.2508 vs rynek **0.2503/0.2460**;
przy niezgodzie rynek 52.2%/53.0% vs model 47.8%/47.0%.
**Arytmetyka progu:** NIE trafia 50.8% → wymaga kursu **2.10**, a rynek na „BTTS nie"
w takim meczu daje ~1.6. Nie domyka się.

✅ **ZROBIONE 15.08 (`b51ea5519`)** — przy okazji wyszło, że dwustronność **już istniała**,
tylko potok ją kasował. `koryguj_tip_ou_btts` od dawna przerzuca typ na `"BTTS NO"`, ale:
1. `prob_modelu` nie znało tego typu → pewność zapisywana jako **50 zamiast 100−bt**,
   i to akurat dla typów, których model był NAJPEWNIEJSZY;
2. `_TYP_DO_ODDS_KEY` nie znało → noga kasowana...
3. ...i podpisywana jako **halucynacja Groqa**, choć Groq nie miał z nią nic wspólnego;
4. API-Football i SofaScore zwracają OBIE strony, a parsery brały tylko „yes" — więc nie
   było czym wycenić (`match_tips.py` czytał `btts_no` i dostawał wyłącznie kurs teoretyczny).

Granie strony NIE zostaje za flagą **`BTTS_TWO_WAY` (default OFF)** — typ jest liczony,
wyceniany i logowany, ale nie wchodzi do kuponu. Flip po zebraniu realnych kursów `btts_no`
i zmierzeniu ROI na nich. Pełna tabela dowodów w `.env.example`.

Zastrzeżenie metody: zbieracz nie zapisał kursów 1X2, więc λ rynku dopasowane tylko do O/U.

### 🔍 Ustalone 13-14.08 — nie zgubić
- **`model_log` to główne źródło danych o modelu**, nie `predictions`. Ta druga dostaje wiersz dopiero PO filtrach wartości. `scripts/stan_uczenia.py` czyta już obie.
- **Rozliczenia mają DWIE ścieżki i żadna nie pokrywała wszystkiego:** `cron_settle` rozlicza KUPONY, a wszystkie predykcje System mają `coupon_id IS NULL`. Predykcje luzem rozlicza wyłącznie `update_pending` z jobów.
- **Okno rozliczeń gubiło dane bezpowrotnie** (naprawione 14.08, commit `3d678f557`): filtr domknięty z obu stron zostawił 95 sierot, mecze od 7 maja. Odzyskiwalne było 13, reszta przepadła. Teraz zaległości wracają paczkami po 15 z limitem 5 prób.
- **Odzyskiwalne były NAJSTARSZE, nie najnowsze** — pierwsza paczka (15 najnowszych) odzyskała 0. Założenie „źródła pamiętają świeższe mecze" nie potwierdziło się na tych ligach.
- **`run_migrations()` odpalało wyłącznie API.** Joby dostały to samo 14.08 — wcześniej poprawność zależała od niepisanej kolejności wdrożenia, a brak kolumny wywalał CAŁY dzienny przebieg (KROK 0), nie same rozliczenia.
- **CLV zależy od rozliczeń.** Blok CLV siedzi wewnątrz pętli rozliczania — bez rozliczonej nogi w ogóle nie startuje. Zero wypełnionych przy zerze rozliczeń to stan oczekiwany, nie bug.
- **API-Football zawieszone** (konto suspended) → brak składów i sędziego → sufit DECISION SCORE 70/100. Dla starych meczów zwraca „Brak w API", ale część zapytań przechodzi.
- **Logi jobów idą w `jsonPayload`, nie `textPayload`** (JSON formatter). `severity` też się nie mapuje — pytaj `jsonPayload.level`.
- **Dług testowy:** `$env:DATABASE_URL=""` w PowerShellu KASUJE zmienną (guard widzi `.env` → prod i przerywa suitę). Działa: `python -c "import os,sys; os.environ['DATABASE_URL']=''; import pytest; sys.exit(pytest.main(['tests/','-q']))"`.
- **Schematy testowe dublują produkcyjny** (`test_backtest_db.py`, `test_evening_agent.py` mają własne `CREATE TABLE`) — każda migracja wymaga ręcznego dociągnięcia, inaczej test sprawdza tabelę, której nigdzie nie ma.

---

> **Ukończone → `CHANGELOG.md` + `git log`.** Ostatnie (07-03/04): reset hasła + panel Model vs Live + Kontuzje v2 (rdzeń) + kalibracja health-gate + **cloud migration** (pipeline PC-off) + 10 kuponów Admin_JG (3/3 WON) + Claude setup hardening (guard hook). Wcześniej (06-24/26): OWASP hardening + CI lint/security/coverage gate + cloud-draft live + reweight ku rynkowi + M1 lewary #1/#2 + 4 źródła danych + Daily DB Backup + walk-forward A/B (DC 51.8%). Jeszcze wcześniej: Cel A/B/C, D1-D7, multi-source, RODO, multi-user.
