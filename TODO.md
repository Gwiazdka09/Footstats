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
- [x] **J1 — Agregat statystyk usera** ✅ `core/user_stats.py` read-only (ROI/win-rate/profit-PLN/streak/best-worst). 25 testów. `get_user_stats`+`get_progress_series`. (per-liga POMINIĘTE — legi niespójne między źródłami.)
- [x] **J2 — GUI Profil/Statystyki** ✅ `GET /api/stats/me` + `StatsView.jsx` (win-rate/ROI/profit/streak/best-worst). Etykiety PLN + disclaimer "papierowy bankroll, nie prawdziwe pieniądze". Playwright PASS.
- [x] **J3 — Krzywa postępu** ✅ `get_progress_series` + `GET /api/stats/progress` + `ProgressChart.jsx` (recharts, profit indigo / win-rate pink). Data = `created_at` (schemat bez `settled_at`). Playwright PASS.
- [x] **J4 — Ręczny wpis kuponu** ✅ kolumna `bookmaker` (migracja 9→Supabase deploy) + `POST /api/coupon/manual` (free-form, ACTIVE, bankroll-neutral) + `PATCH /api/coupon/{id}/result` (owner-check, CAS, guard `kupon_type=='manual'`) + `ManualCouponForm.jsx` + WON/LOST/VOID w `HistoryCouponRow`. **Manual WYKLUCZONY z auto-settle** (hybryda: co mamy=my, reszta=user ręcznie). Playwright PASS.
- [x] **J5 — Leaderboard v2** ✅ `GET /leaderboard` + ROI/profit/win-rate + `sort` (win_rate/roi/profit, nieznany→400) + filtr czasu `days` (cache vary_by) + `LeaderboardView` v2 (selektory, design-system inline-token, disclaimer PLN). Liga/sezon POMINIĘTE (legi niespójne). **Ranking = shared-only (opt-in); statystyki osobiste = WSZYSTKIE kupony (decyzja 2026-07-21).** Playwright PASS.
- [x] **J6 — Predykcja jako sygnał w dzienniku** ✅ `POST /api/coupon/preview-signal` + podgląd "Nasz typ @conf%" w `ManualCouponForm` (indigo zgoda / pink rozjazd / muted brak typu). Kalibracja OFF → pewność=model (przepływa przez `calibrate_confidence` gdy włączą). Playwright PASS.

### 🔗 Match-linking (fundament J6+J4c, kierunek 2026-07-21) — DONE
> Free-form mecz → nasze dane. Odblokowało oba: podgląd sygnału (J6) + auto-settle (J4c).
- [x] **A — `core/match_linker.py`** ✅ `link_leg(home,away,date)` STRICT `_norm_ascii` (NIE `normalize_team_name` — ono koliduje City==United!). Konserwatywny: exact-only, swap/ambiguous/pusta-norma → brak matchu. 11 testów. Ograniczenie: `ł` daje false-negative (bezpieczne).
- [x] **C — J4c `settle_manual_coupons`** ✅ auto-settle nóg manual TYLKO gdy match+nasz `actual_result`; all-legs-or-nothing; ZERO zewn. API; CAS-guard; bankroll-neutralny; guard pustych nóg. `POST /cron/settle-manual` (X-Cron-Secret, **NIE wpięty w scheduler**). reviewer APPROVED + data-guard GREEN. 13 testów.
  - ⏳ **Decyzja usera:** enablement `/cron/settle-manual` — dodać do Cloud Scheduler (dry-run first) czy manualny trigger?
  - Follow-up (opcj.): aliasy PSG/Man City (kontrolowana lista), per-leg result w legs_json dla UI.

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

- [x] ~~**Backfill Neon → Supabase + rotacja hasła**~~ ✅ **14.08 zamknięte** — backfill był już wykonany, kupony/bankroll/users odpuszczone (decyzja usera), wersja 1 sekretu `DATABASE_URL` z Neonem wyłączona. Zostaje kosmetyka: usunąć `DATABASE_URL_NEON` z lokalnego `.env`.
- [ ] **Co kilka dni:** `python scripts/stan_uczenia.py` (read-only) — licznik do werdyktu, teraz z `model_log`. Uzupełniająco `scripts/calibration_monitor.py` + flip-advisor (`core/flip_advisor.py`): rekomenduje flip `SELECTION_MIN_CONF` i ligi do `LEAGUE_GATING` (<50%, n≥8).
- [ ] **D3 — pełna decyzja a/b/c** (próg guardu, czy argmax na stałe) — po ~20 ŚWIEŻYCH settled z zapisanym prob. Zwaliduj że guard pomaga, dostrój próg. (D3 cz.1+2 prob+guard ZROBIONE 06-22.)
- [ ] **Po ~88 settled → D2 auto-refit sam** (delta +30 od n_train); gdy krzywa zdrowa → włącz `CALIBRATION_ENABLED=1`.
- [x] ~~**DECYZJA (nie bug):** Bzzoiro etykietuje towarzyskie kadr jako "World Cup 2026" → whitelist MŚ (D1a).~~ **Wygasło 07-20** — MŚ zakończone 19.07; wraca ewentualnie przy Euro/kadrach.
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

- [x] ~~**Verify quick_picks-fix → Poisson live**~~ ✅ **13-14.08** — `poisson-dc` gra w OBU ścieżkach (job + draft na API). Escape-hatch bez zmian: `QUICK_PICKS_USE_POISSON_CACHE=0`, ale **uwaga** — ta flaga wyłącza adapter schematu i Poisson odpada po cichu, to nie jest czysty przełącznik modelu.
- [x] ~~**Parquet na cloud**~~ ✅ w obrazie (`Dockerfile.jobs` + `Dockerfile.api`).
- [x] **Kontuzje v2 — baza graczy + goal_share** (07-05): `core/player_db.py` (SQLite) + `scrapers/player_stats.py`. Wpięte w `_apply_injury_corrections` → kara napastnika ∝ udziałowi w golach. Populacja przez **`scripts/refresh_players.py`** (`--season`, `--only`, `--understat`).
  - **2 źródła:** (1) API-Football `/players/topscorers` (topscorer denominator, mniejsze ligi) — 11 lig; (2) **Understat pełne składy TOP5** (per-gracz gole/asysty/xG) → **prawdziwy denominator** (Salah 34% nie 60%). Stan 07-05: **sezon 2025 (2025-26) PRIMARY = 2775 graczy** (Understat TOP5, najświeższy pełny sezon — pipeline `_current_season`=2026 → walk-back → 2025) + sezon 2024 fallback 2885. **MŚ 2026: 119 graczy** (sezon 2026, liga WC) — Sofascore top-players API (gole/asysty/**rating 1-10**/xG, angielskie kadry) via headless browser; Flashscore strzelcy jako cross-check. goal_share kadr działa (France Mbappé 54%, Brazil Vini 57%, England Kane 71%). `rating`/`xg` = nowe kolumny player_db (`get_team_players`).
  - **Siła kadr (team_stats):** 48 kadr MŚ (Sofascore standings + top-teams) → `team_attack_defense(team,2026)` = (gole/mecz, tracone/mecz) = **Poisson λ dla reprezentacji** (model nie miał historii kadr!). France λ_atk 3.33/def 0.67, Spain 1.67/0.00, Norway 2.67/2.33. + avg_rating 1-10, possession, clean_sheets, big_chances. Tabela `team_stats`.
  - [x] **λ kadr WPIĘTE** (07-05): `core/national_lambda.py` + `_apply_national_lambda` (daily_agent przed roznica_modeli). Mecze reprezentacji (obie w team_stats) → Poisson λ z turnieju BLEND 0.5 z Bzzoiro-ML. Gated: kluby bez zmian (backtest offline niezmieniony). Demo: Portugal-Spain 34/32/34 (Spain 0 straconych), Brazil-Norway 56%+O2.5 74%.
  - **Do wpięcia:** rating 1-10 — brak live data-path (lineup'y WC niedostępne w API-Football, kluby bez ratingu Sofascore); zapisane+wystawione (`get_team_players`), wpięcie gdy pojawi się źródło ratingów składów. Denominator goal_share kadr = top-50 strzelców (kraje z 1 strzelcem → 100%, bounded cap).
  - **Understat wymaga JS-renderu** (od ~2026 nie embeduje `playersData` w HTML → plain-HTTP zwraca []); kolekcja przez headless browser (odczyt `window.playersData`). `parse_understat_players`/bridge działają na wyrenderowanym HTML.
  - **Do dokończenia:** (a) doładować 5 lig API-Football po resecie 429 (MLS/Saudi/LigaMX/Belgia/Szkocja); (b) repeatable Understat fetch przez projektowy Playwright (teraz manual/MCP); (c) normalizacja: `normalize_team_name` zbija "Manchester City"=="United"→"manchester" i "Bayern Munich"≠"München" — kolizje/miss dla części drużyn (bounded cap ±20%); (d) match nazw injury(SofaScore) ↔ goal_share(Understat) — różne pisownie.
- [x] **Faza 2 — siła składu XI** (07-05): `core/lineup_strength.py` — brak topowego strzelca w startXI → λ ataku ↓ (`lineup_lambda_factor`) + kara decision_score (`lineup_confidence_penalty_v2`, zastępuje crude len<11). Wpięte w `_enrichuj_finalna_faza`.

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

## 🔍 AUDYT 2026-08-17 — 23 znaleziska (0 krytycznych)

> Pełny raport z dowodami: artefakt „Audyt FootStats". Poniżej lista do odhaczania.
> Zakres: 172 pliki .py (37 636 linii), 3381 linii JSX, 4463 testy / **80% pokrycia**, prod DB + GCP.

### 🔴 Wysokie
- [x] ✅ **D1 — dogrywka/karne. ZROBIONE 17.08.** ⚠️ **KOREKTA pierwotnego znaleziska:** napisałem „kupon stoi ACTIVE NA ZAWSZE" — **nieprawda**. Jest siatka `VOID_AFTER_DAYS=10` ([coupon_settlement.py:346](src/footstats/core/coupon_settlement.py#L346)) i działa: **zero** kuponów ACTIVE starszych niż 10 dni na produkcji.
  - **Realna szkoda była subtelniejsza i częściowo GORSZA.** Zachowanie zależało od ZAPISU źródła: `2-1aet` → `None` (10 dni limbo → VOID bez wyjaśnienia), ale `2-1 (AET)` → **rozliczane jako wygrana gospodarza**. Ten sam mecz, dwa werdykty. Druga ścieżka to **ciche BŁĘDNE rozliczenie** — po 90 min mógł być remis.
  - **Dlaczego nie rozliczamy po dogrywce:** rynki 90-minutowe wymagają wyniku regulaminowego, a tego zapisu w danych nie ma. Wnioskowanie „była dogrywka → po 90 remis" jest zawodne (w dwumeczu dogrywkę wymusza remis w DWUMECZU, sam mecz mógł skończyć się 1-0).
  - **Fix:** `powod_nierozliczalny()` rozpoznaje dogrywkę/karne (dopasowanie po całych słowach — „Openda" nie myli); `oblicz_tip_correct` zwraca `None` **z WARNINGIEM** dla obu zapisów; kupon dostaje **VOID od razu z podanym powodem** zamiast 10 dni ciszy. Trzy stare testy kodowały obcinanie sufiksu — przepisane wraz z uzasadnieniem zmiany intencji. +30 testów.
- [x] ✅ **F1 — reset CSS zabijał kolory przycisków. ZROBIONE 17.08.** Bug **udowodniony w przeglądarce** (Playwright, styl wyliczony), nie tylko z lektury pliku:
  - przed: `<button class="text-rose-400">` → `rgb(248,250,252)`, `<button class="bg-emerald-500">` → `rgba(0,0,0,0)`; ten sam `text-rose-400` na `<span>` **działał**
  - po: przycisk i span dają identyczny kolor; przycisk bez klasy dalej dziedziczy i jest przezroczysty; `.btn-primary` dalej wygrywa gradientem (brak regresji)
  - **Zmieniło wygląd 6 przycisków** — wszystkie na lepsze. Najboleśniejsze były niewidoczne: przycisk **rejestracji** (`bg-indigo-500`) był PRZEZROCZYSTY, a **usunięcia konta** (`bg-rose-500`) nie miał czerwieni ostrzegawczej.
  - Zrzuty desktop 1440 + mobile 390 po fiksie: bez regresji. `tests/test_css_warstwy.py` pilnuje warstwy (i tego, że `.btn-primary` ma zostać POZA warstwami — to celowe).
- [ ] **F6 — baner cookie zasłania link „Masz już konto? Zaloguj się"** na mobile (390px) w widoku rejestracji. Znalezione przy weryfikacji F1, nie związane z tą zmianą.
- [x] ✅ **F7 — ZROBIONE 17.08 (wariant A: analityka usunięta).** `<Analytics />` i `<SpeedInsights />` wyjęte z `main.jsx`, zależności `@vercel/*` usunięte z `package.json` + lockfile. Zweryfikowane w przeglądarce po zmianie: **zero** skryptów analityki w DOM. Treść banera („wyłącznie niezbędne") jest teraz prawdziwa. Rewert = jeden commit.
- [x] ✅ **F8 — ZROBIONE 17.08.** Trzy zaszyte na sztywno adresy Cloud Run (baner + dwa linki w stopce) zastąpione helperem `legalUrl()` w `lib/api.js`. **Zweryfikowane, że nie psuje produkcji:** żywy bundle na Vercelu ma `VITE_API_BASE = https://footstats-api-…run.app/api`, a helper wylicza z niego dokładnie ten sam URL, który był zaszyty. Teraz linki dzielą los aplikacji — jeśli `API_BASE` jest zły, i tak nic nie działa.
- ~~**F7 — opis pierwotny**~~ (zostawiony dla kontekstu):
  1. **Baner twierdzi**: „używamy NIEZBĘDNYCH plików cookie / local storage (np. token sesji)".
  2. **Realnie**: `main.jsx:13-14` montuje `<Analytics />` i `<SpeedInsights />` (Vercel) **bezwarunkowo**. Dowód: przy `fs_cookie_consent = null` i widocznym banerze oba skrypty są już w DOM (`/_vercel/insights/script.js`, `/_vercel/speed-insights/script.js`).
  3. **Polityka prywatności** nie wspomina o analityce ani słowem (jest tylko „cookies").
  - Flaga `fs_cookie_consent` jest **czytana wyłącznie przez sam baner** — przycisk „Rozumiem" nie włącza ani nie wyłącza niczego.
  - Pod RODO/ePrivacy: cookies *ściśle niezbędne* zgody NIE wymagają, ale analityka **wymaga** i nie może odpalać przed zgodą. Obecny stan jest gorszy niż brak banera — to komunikat, który nie opisuje tego, co aplikacja robi.
  - **Do decyzji:** (A) usunąć Vercel Analytics — najprościej i zgodne z kierunkiem „prywatny użytek + znajomi", wtedy treść banera staje się prawdziwa i wystarczy jednolinijkowa notka zamiast paska; (B) bramkować analitykę zgodą i dopisać ją do polityki; (C) zostawić i tylko poprawić treść — najsłabsze, bo dalej brak bramki.
- [ ] **F8 — link do polityki prywatności zaszyty na sztywno** jako surowy adres Cloud Run (`CookieConsent.jsx:21`), zamiast ścieżki względnej lub zmiennej środowiskowej. Po zmianie hostingu link umrze po cichu.
- ⚠️ **KOREKTA F4 (PWA):** manifest i service worker **istnieją** — serwuje je API (`main.py:411` `/manifest.json`, `/sw.js`). Front ich jednak **nie podpina**: `index.html` nie linkuje manifestu, `main.jsx` nie rejestruje SW. Czyli nie „brak PWA", tylko **PWA niepodłączone** — kawałki leżą po stronie API i nikt ich nie używa.
- [ ] **F2 — zero dostępności.** 0× `aria-label`, 0× `alt`, 0× `role` w 3381 liniach JSX. (Plus: 0× `onClick` na `div`/`span` — klikalne są `<button>`, więc baza jest dobra.)
- [x] ✅ **F3 — ZROBIONE 17.08. Front ma pierwsze 29 testów i bramkę w CI.** Vitest + Testing Library + jsdom; `npm test` / `npm run test:watch`; osobny job `frontend` w `ci.yml` (`npm ci --legacy-peer-deps` — ten sam przełącznik co build na Vercelu — plus `npm test` i `npm run build`). Zweryfikowane czystym `npm ci`, tak jak zrobi to CI.
  - **Setup pilnuje izolacji jak `tests-no-prod.md` po stronie backendu:** domyślny `fetch` wybucha z czytelnym komunikatem, więc zapomniany mock widać od razu zamiast cichego strzału w API.
  - Pokryte: `lib/api.js` (`legalUrl`, `decodeJwtPayload` — śmieciowy token nie może wywalić apki białym ekranem), `HistoryCouponRow` (ręczne rozliczanie: widoczne TYLKO dla `manual`+ACTIVE, właściwy endpoint i payload, błąd trafia na ekran, podwójne kliknięcie nie wysyła dwóch rozliczeń, licznik nóg), `CookieConsent`, `main.jsx` (strażnik: analityka nie może wrócić po cichu).
  - Zostaje do pokrycia: `ManualCouponForm`, `CouponWizard`, `StatsView`, `LeaderboardView`.
- [ ] **F9 — inline'owe kolory na przyciskach to już tylko pozostałość.** Były obejściem buga CSS naprawionego w F1. Trzy miejsca: `HistoryCouponRow.jsx`, `StatsView.jsx`, `ProgressChart.jsx` — można uprościć do zwykłych klas Tailwinda. Wymaga przejścia po wszystkich trzech naraz z regresją wizualną. Komentarz w `HistoryCouponRow` już nie kłamie (zaktualizowany).
- [ ] **M1 — selekcja gra najwięcej tam, gdzie traci najwięcej.** 62% kuponów 15.08 to BTTS; papier: **47,6% traf, ROI −28,2%** na 42 kuponach. Hipoteza: filtr kursu 1,20–4,00 strukturalnie faworyzuje BTTS (kursy 1,5–1,8 zawsze przechodzą, faworyci 1X2 wypadają dołem). Sprawdzić rozkład typów PO filtrze per rynek → ewentualnie próg kursu per rynek.

### 🟡 Średnie
- [ ] **B1 — tokenów nie da się unieważnić.** Brak `jti`/blacklisty/`token_version`; **zmiana hasła NIE wylogowuje sesji**, token żyje 24h. Fix: `token_version` w users + w tokenie.
- [ ] **B2 — limity zapytań mogą liczyć zły adres.** `get_remote_address` = `request.client.host`, za Cloud Run to load balancer, nie klient. **Podejrzenie, nie fakt** — potwierdzić testem z dwóch sieci. Fix: `key_func` czytający `X-Forwarded-For`.
- [ ] **B3 — python-jose → PyJWT**, żeby zdjąć `--ignore-vuln PYSEC-2026-1325` (ecdsa) z pip-audit.
- [ ] **B4 — zależności bez wersji.** 50 pozycji, **0 przypiętych**, brak lockfile → build niereprodukowalny. Fix: `pip-compile` + lock z hashami.
- [ ] **D2 — `/cron/settle-manual` NIE jest w Schedulerze** (7 zadań, żadne go nie woła) → kupony `manual` z dziennika nie rozliczają się. Dotyczy m.in. #149.
- [ ] **D3 — 231 predykcji z `odds_verified=0`** (kurs od Groqa) → ROI/CLV z historii nic nie znaczą. Decyzja: backfill kursów czy trwałe wykluczenie z raportów.
- [ ] **I1 — wdrożenie jobów to ręczna pułapka.** Przy każdym buildzie 2 najnowsze digesty są BEZ TAGU (atestacja BuildKita); przypięcie takiego zatrzymało pipeline 30.07–02.08. API ma CD, joby nie. Fix: joby w `cd.yml`.
- [ ] **I2 — licznik tokenów myli się 2×.** Heurystyka 1,4 znaku/token vs realne 2,86 (1338 vs **655** tokenów na szkielecie) → prompt bywa przycinany bez potrzeby. Fix: `tiktoken` — **wymaga `pip install`, czyli zgody**.
- [ ] **J1 — połowa `except` milczy.** 271 z 546 bez logu i bez `raise`. Strażnik w testach pilnuje SZEROKOŚCI (`except Exception`), nie milczenia. Fix: drugie kryterium w tym samym strażniku.
- [ ] **J2 — mypy sprawdza 1 katalog** (`scrapers/sources/`) ze 172 plików.
- [ ] **J3 — schematy testowe dublują produkcyjny** (`test_backtest_db`, `test_evening_agent`) — bolało przy migracji 12 i 13. Fix: jedna fikstura z `init_db()`.
- [ ] **M2 — trzy flagi czekają na walidację:** `SELECTION_MIN_CONF=65`, `LEAGUE_GATING=1`, `BTTS_TWO_WAY`. Wszystkie blokuje ten sam brak danych.
- [ ] **M3 — cel M1 mierzy rynek, który przegrywa.** „55% win rate" liczone na 1X2, gdzie przy niezgodzie rynek 42,9% vs model 29,8%. Rozważyć ROI zamiast trafności.

### ⚪ Niskie
- [ ] **B5 — brak Content-Security-Policy** (reszta nagłówków jest: nosniff, DENY, HSTS, Referrer-Policy). Start w `report-only`.
- [ ] **B6 — jedyne dynamiczne SQL:** `player_db.py:73` `ALTER TABLE ... ADD COLUMN {col} {typ}` — wartości z kodu, nie z wejścia. Whitelist par (kolumna, typ).
- [ ] **D4 — `model_log` śledzi tylko argmax 1X2** → rynków golowych nie zweryfikujemy live. Dopisać `p_over25`/`p_btts` + wynik.
- [ ] **F4 — brak PWA** mimo planu „PWA first" (jest favicon/robots/sitemap, brak manifestu i SW). Albo `vite-plugin-pwa`, albo skreślić z planu.
- [ ] **F5 — `CouponWizard.jsx` 437 linii**, `SettingsView.jsx` 377 (limit 400).
- [ ] **I3 — brak Sentry na froncie** (backend ma).
- [ ] **I4 — `DATABASE_URL_NEON` wciąż w lokalnym `.env`** mimo porzucenia Neona.
- [ ] **J4 — bramka pokrycia 8 pkt pod stanem faktycznym.** Zmierzone **80%**, `--cov-fail-under=72` → można skasować 8 pkt i build przejdzie. Najsłabsze: `football_data.py` 21%, `flashscore_results.py` 42%, `utils/cache.py` 56%, **`utils/db.py` 69%** (warstwa dostępu do bazy).
- [ ] **J5 — 4 pliki > 800 linii:** `daily_agent.py` 1022, `superbet.py` 867, `coupons.py` 832, `analyzer.py` 814.

### 🛡️ Odporność na ataki — ZMIERZONA 17.08 (`tests/test_odpornosc_ataki.py`, 25 testów)

| atak | werdykt | dowód |
|---|---|---|
| **Wstrzyknięcie SQL** (`' OR 1=1 --`, `UNION SELECT`, `DROP TABLE`) | ✅ **odporni** | 14 ładunków × 2 pola → wszystkie 401. Ładunek trafia do bazy jako **parametr**, nigdy do tekstu zapytania |
| **Brute-force z jednego IP** | ✅ **blokowany** | 15 prób zgadywania → limiter ucina po 10. Ta sama odpowiedź dla złego hasła i nieistniejącego konta (brak enumeracji) |
| **Brute-force z wielu IP** | ⚠️ **luka B7** | brak licznika prób i blokady konta — botnet dostaje 10 prób/min **z każdego adresu**, konto nigdy się nie zamyka |
| **Podrobiony token** | ✅ **odrzucany** | obcy sekret → 401; wygasły → 401; bez `uid` → 401 |
| **Skradziony token** | ⚠️ **luka B1** | działa z **dowolnego IP i przeglądarki** do 24h; brak `jti`/powiązania z urządzeniem, więc kopii nie da się wykryć |
| **Zmiana hasła po przejęciu konta** | ⚠️ **luka B1** | **nie unieważnia** starego tokenu — napastnik zachowuje dostęp do doby |

- [ ] **B7 — brak blokady konta po serii błędnych haseł.** Jedyna obrona to limit per IP (B2 podaje w wątpliwość nawet to, bo za Cloud Run kluczem bywa adres load balancera). Fix: licznik `failed_attempts` + `locked_until` na `users`, wykładnicze opóźnienie albo CAPTCHA po N próbach.
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
