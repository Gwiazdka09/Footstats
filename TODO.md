# FootStats TODO — Lipiec 2026

> **🎯 PIVOT 2026-07-06:** zero monetyzacji/użytkowników → **czysta predykcja do doskonałości**. Strategia + 16 pomysłów → **`docs/PREDICTION_ROADMAP.md`**. Empiria: static value-betting na publicznych danych OBALONE (nie bije rynku O/U ani 1X2). Kierunek: **ścieżka A kalibracja** (best predyktor, metryka log-loss/Brier) lub **ścieżka B edge informacyjny** (player-availability delta/live/CLV). P3 monetyzacja → ARCHIWUM.
>
> **🔧 NAPRAWIONE 07-06 (największy lever):** audyt 104 settled — Groq nadpisywał model i psuł (1X2 model argmax 60% vs Groq 48%, +12pp). Fix: `GROQ_TIP_OVERRIDE` flip ON + threshold 33 (1X2) + 45 (O/U/BTTS `koryguj_tip_ou_btts`). **LLM (llama-3.1-8b) odsunięty od WSZYSTKICH picków → tylko analiza/podsumowania.** Model wybiera. TODO: zakładka GUI "analiza LLM"; rozważyć GROQ_MODEL=70b (reasoning). Inne dławiki: 65% predykcji bez modelu (off-season egzotyka/WC → LEAGUE_GATING celuje w złe ligi), confidence odwrócony (80%+→19%, nie włączać selekcji).

> **🎯 KIERUNEK 2026-07-21:** produkt = **dziennik kuponów + śledzenie postępu ludzi** (nie tylko surowa predykcja). NIE bukmacher, **zero obsługi pieniędzy** (jednostki, nie PLN przez nas). Predykcja = sygnał zaufania w dzienniku, nie sprzedawany edge. Plan → sekcja `📓 DZIENNIK KUPONÓW` niżej. Omija KILL rady ROAST (dziennik ≠ konkurent devigu rynku).

**Aktualizacja:** 2026-07-21 · v3.4-stable
**Accuracy:** offline **51.8%** (WF A/B, DC W=0.5) | live świeże ≥06-19 **47.8%** (23 settled, fixy Cel B) vs stare 31%
**Cel M1:** 55% win rate · **Suite:** ~1539 pass unit-mode (coverage 57)
**LIVE:** pipeline **PC-off w chmurze** — Cloud Run Jobs (final 11:00 + evening 23:00) + Scheduler (draft 07:30, settle 06:00/21:30). Szczegóły → `docs/cloud_migration.md`.
**⚠️ INCYDENT 14-20.07 (naprawiony 07-20):** potrójna awaria — Neon quota-block → **DB = Supabase free** (session pooler); image jobów bez `footstats.data` (`.gcloudignore` fix); kupon=None crash. **Luka w danych 14-20.07** (zero predykcji/settled). Dane 1-17.07 uwięzione w Neonie do **1.08**. Szczegóły → `CHANGELOG.md` 07-20.
**Zbudowane flag-OFF (flip po walidacji):** `SELECTION_MIN_CONF` (#1) · `LEAGUE_GATING` (#2). Już LIVE: `ENSEMBLE_MARKET_WEIGHT=0.70` (reweight ku rynkowi).

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
- [ ] **J6 — Predykcja jako sygnał w dzienniku**: przy dodawaniu/podglądzie kuponu pokaż predykcję modelu + **kalibrowaną pewność** (uczciwe 65%=65%) obok wyboru usera → user widzi zgodność swojego typu z modelem. Zależy od jakości sygnału (P0/P1).

### Silnik sygnału (dotychczasowa praca = wartość dziennika)
Kalibracja/selekcja (P0/P1 niżej) NIE jest już celem samym w sobie — to **feature zaufania w dzienniku**: uczciwa pewność, której blind-tipster nie da. P0 walidacja dalej ważna, ale jako **jakość sygnału**, nie jako "bicie rynku".

### Non-goals (twarde — blok scope-creep)
- ❌ Płatności / wypłaty / realny PLN przez nas — tylko **jednostki**. ❌ Przyjmowanie zakładów (nie bukmacher). ❌ Sprzedawanie edge / ściganie rynku jako produkt.

### 🐞 Znalezione przy J1-J4 (osobne taski, NIE blokują dziennika)
- **CSS cascade-layer bug (app-wide):** `gui/src/index.css` `button {color:inherit;background:transparent}` jest POZA `@layer` → w Tailwind v4 bije utility-klasy, więc `text-*`/`bg-*` na KAŻDYM `<button>` się nie stosują (przyciski bezbarwne). Obejście w dzienniku: inline `style var()`. Fix globalny = owinąć reset w `@layer base` + pełna regresja wizualna przycisków.
- **Auto-settle hybryda „co mamy — my":** manual kupony na razie TYLKO ręczne rozliczenie. Follow-up J4c: best-effort auto-match ręcznych nóg do naszych wyników (fuzzy nazwa+data) → link match_id → istniejący settle. Ostrożnie (settlement correctness, data-guard) — osobny task.
- **Testy dotykają prod Neon:** import `api/routes/coupons` przy zbiórce testów próbuje realnego połączenia do martwego Neona (`config.py` `load_dotenv override` → `DATABASE_URL` z `.env`). Pre-existing. Fix: marker `@pytest.mark.integration` + test-DB (patrz P0 dług testowy).

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M1** | 55% win rate | 🔴 W toku | ~88 świeżych settled → selekcja 65%+ conf (offline=68%) + gating lig |
| **M2** | 60% win rate | ⏸️ | Po M1 — tuning |
| **M3** | 65% selected | ⏸️ | Po M2 |
| **BETA** | Testerzy | ⏸️ | Po M1 |

---

## 🔴 P0 — WALIDACJA (blokuje M1, PASYWNE — NIE dokładaj zmian λ)

> Root-cause'y Cel B usunięte. Kalibracja OFF (`CALIBRATION_ENABLED`), auto-refit czeka na dane (D2).
> STOP na nowe λ aż zbierzemy świeże settled — zmiana teraz zaciemnia czy fixy działają.
> **Zbieranie leci PC-niezależnie** (cloud draft 07:30 + settle) — brak wąskiego gardła danych.

- [ ] **🆕 1.08 (twarda data — reset quota Neon):** backfill Neon → Supabase (`pg_dump`: predictions/coupons/bankroll/**users z hasłami**) + **rotacja hasła Neon** (wisiało plaintext w env Cloud Run) + decyzja czy Neon kasować. Bez backfillu licznik settled i konta userów = od zera.
- [ ] **Co kilka dni:** `python scripts/calibration_monitor.py` (DB read-only) — System vs Pipeline, czy accuracy ruszyła, licznik settled. Ma per-liga + **flip-advisor** (`core/flip_advisor.py`): rekomenduje czy flipnąć `SELECTION_MIN_CONF` i które ligi do `LEAGUE_GATING` (<50%, n≥8). *(Sensowne dopiero po backfillu 1.08 — świeży Supabase ma 0 settled.)*
- [ ] **D3 — pełna decyzja a/b/c** (próg guardu, czy argmax na stałe) — po ~20 ŚWIEŻYCH settled z zapisanym prob. Zwaliduj że guard pomaga, dostrój próg. (D3 cz.1+2 prob+guard ZROBIONE 06-22.)
- [ ] **Po ~88 settled → D2 auto-refit sam** (delta +30 od n_train); gdy krzywa zdrowa → włącz `CALIBRATION_ENABLED=1`.
- [x] ~~**DECYZJA (nie bug):** Bzzoiro etykietuje towarzyskie kadr jako "World Cup 2026" → whitelist MŚ (D1a).~~ **Wygasło 07-20** — MŚ zakończone 19.07; wraca ewentualnie przy Euro/kadrach.
- [ ] **🆕 Dług testowy:** lokalna pełna suita wymaga żywej DB — `config.py` robi `load_dotenv(override=True)` → 23 testy integracyjne biją w `DATABASE_URL` z `.env` (= martwy Neon). Fix krótki: podmienić `DATABASE_URL` w `.env` na Supabase (wymaga zgody usera). Fix docelowy: testy integracyjne za markerem `@pytest.mark.integration` + oddzielny test-DB.

---

## 🟠 P1 — M1 LEVERS (zbudowane flag-OFF → flip po ~88 fresh settled)

> Kalibracja: **65%+ conf = 68%** (robustnie). Per-liga: NED 56/SCO 55/ITA 54/ENG 54 ≥M1; POL 44/ESP 49/FRA 49 w dół.
> Wniosek M1 (zgodny z Cel B): model OK, droga = **SELEKCJA** (65%+ subset) + **gating lig**.

- [ ] **Flip `SELECTION_MIN_CONF=65`** po walidacji — podnosi próg `najlepszy_typ` do pasma high-conf. Zwaliduj że live trzyma kalibrację. (Wpływa na System paper + cloud-draft.)
- [ ] **Flip `LEAGUE_GATING=1`** po walidacji — odrzuca `LIGI_SLABE` (POL/ESP/FRA <50%), faworyzuje NED/SCO/ITA/ENG.
- [ ] **Monitoruj reweight 30/70** (`ENSEMBLE_MARKET_WEIGHT=0.70`, rev 00274 LIVE) — calibration check (log-loss) na świeżych settled. Escape-hatch: zmień/usuń env.
- [ ] (opcj.) re-optymalizacja per-league wag ku rynkowi (`ensemble_optimizer`).

---

## 🟡 P2 — SIERPIEŃ (restart lig klubowych)

> Teraz off-season = mecze kadr (WC) → Poisson nie ma historii reprezentacji (dataset = ligi klubowe). Realny zysk dopiero na restart lig.

- [ ] **Verify quick_picks-fix → Poisson live** (51.8%) zamiast Bzzoiro-ML gdy wrócą ligi klubowe. Monitor `calibration_monitor.py`. Gdyby Poisson gorszy → escape-hatch `QUICK_PICKS_USE_POISSON_CACHE=0`.
- [ ] **Parquet na cloud** → cloud-draft użyje Poisson-DC zamiast `bzzoiro-ml` (cloud nie ma `full_dataset.parquet` 562KB). Opcje: (a) GCS-pull przy starcie [najlepsze] lub (b) COPY do obrazu. **Odłożone do sierpnia** (off-season → Poisson i tak nie ruszy).
- [x] **Kontuzje v2 — baza graczy + goal_share** (07-05): `core/player_db.py` (SQLite) + `scrapers/player_stats.py`. Wpięte w `_apply_injury_corrections` → kara napastnika ∝ udziałowi w golach. Populacja przez **`scripts/refresh_players.py`** (`--season`, `--only`, `--understat`).
  - **2 źródła:** (1) API-Football `/players/topscorers` (topscorer denominator, mniejsze ligi) — 11 lig; (2) **Understat pełne składy TOP5** (per-gracz gole/asysty/xG) → **prawdziwy denominator** (Salah 34% nie 60%). Stan 07-05: **sezon 2025 (2025-26) PRIMARY = 2775 graczy** (Understat TOP5, najświeższy pełny sezon — pipeline `_current_season`=2026 → walk-back → 2025) + sezon 2024 fallback 2885. **MŚ 2026: 119 graczy** (sezon 2026, liga WC) — Sofascore top-players API (gole/asysty/**rating 1-10**/xG, angielskie kadry) via headless browser; Flashscore strzelcy jako cross-check. goal_share kadr działa (France Mbappé 54%, Brazil Vini 57%, England Kane 71%). `rating`/`xg` = nowe kolumny player_db (`get_team_players`).
  - **Siła kadr (team_stats):** 48 kadr MŚ (Sofascore standings + top-teams) → `team_attack_defense(team,2026)` = (gole/mecz, tracone/mecz) = **Poisson λ dla reprezentacji** (model nie miał historii kadr!). France λ_atk 3.33/def 0.67, Spain 1.67/0.00, Norway 2.67/2.33. + avg_rating 1-10, possession, clean_sheets, big_chances. Tabela `team_stats`.
  - [x] **λ kadr WPIĘTE** (07-05): `core/national_lambda.py` + `_apply_national_lambda` (daily_agent przed roznica_modeli). Mecze reprezentacji (obie w team_stats) → Poisson λ z turnieju BLEND 0.5 z Bzzoiro-ML. Gated: kluby bez zmian (backtest offline niezmieniony). Demo: Portugal-Spain 34/32/34 (Spain 0 straconych), Brazil-Norway 56%+O2.5 74%.
  - **Do wpięcia:** rating 1-10 — brak live data-path (lineup'y WC niedostępne w API-Football, kluby bez ratingu Sofascore); zapisane+wystawione (`get_team_players`), wpięcie gdy pojawi się źródło ratingów składów. Denominator goal_share kadr = top-50 strzelców (kraje z 1 strzelcem → 100%, bounded cap).
  - **Understat wymaga JS-renderu** (od ~2026 nie embeduje `playersData` w HTML → plain-HTTP zwraca []); kolekcja przez headless browser (odczyt `window.playersData`). `parse_understat_players`/bridge działają na wyrenderowanym HTML.
  - **Do dokończenia:** (a) doładować 5 lig API-Football po resecie 429 (MLS/Saudi/LigaMX/Belgia/Szkocja); (b) repeatable Understat fetch przez projektowy Playwright (teraz manual/MCP); (c) normalizacja: `normalize_team_name` zbija "Manchester City"=="United"→"manchester" i "Bayern Munich"≠"München" — kolizje/miss dla części drużyn (bounded cap ±20%); (d) match nazw injury(SofaScore) ↔ goal_share(Understat) — różne pisownie.
- [x] **Faza 2 — siła składu XI** (07-05): `core/lineup_strength.py` — brak topowego strzelca w startXI → λ ataku ↓ (`lineup_lambda_factor`) + kara decision_score (`lineup_confidence_penalty_v2`, zastępuje crude len<11). Wpięte w `_enrichuj_finalna_faza`.

---

## 🗄️ P3 — MONETYZACJA / LAUNCH (ARCHIWUM — pivot 2026-07-06, zero monetyzacji)

> Odłożone bezterminowo. Focus = predykcja (`docs/PREDICTION_ROADMAP.md`). Zostawione jako referencja gdyby wróciło.

- [ ] **D8 — prawnik (ToS bukmacherów) + JDG (CEIDG)** — wstrzymane (koszt/ryzyko). Wrócić po walidacji.
- [ ] **Resend** FROM `onboarding@resend.dev` (test) → zweryfikowana domena przed prod. (Reset hasła + Resend wpięte ✅.) Wymaga env `FRONTEND_URL`.
- [ ] **Płatności** (Lemon Squeezy/Paddle, po JDG): cennik+auto-renewal, webhooks, email potwierdzenie/faktura, upgrade/proration.
- [ ] **Faktura** (po płatnościach). Custom domain (opcjonalne).

---

## ⚪ P4 — OPCJONALNE

- [ ] **Scrapery — ocena per-stabilność/anti-bot:** Soccer24 (klon FlashScore, skip), Meczyki/LiveScore (anti-bot), Transfermarkt (squad/value nie wyniki). 4 źródła już wpięte (AF/football-data.co.uk/FlashScore/TheSportsDB).

---

## 🚫 Zbadane → odrzucone (NIE wracać)

- **ImportanceIndex** (crude ±20%): A/B −0.1pp, high-stakes −0.59pp → ślepa uliczka. `core/standings.py` zostaje jako CECHY do ML.
- **LightGBM / własny model ML:** 51.6% (z kursami) < rynek 53.1% < baseline. Rynek nieprzekraczalny (jak literatura). `core/ml_features.py` zostaje jako infra. Jedyny owoc = reweight ensemble ku rynkowi.
- **Schedule-adjusted ratings** (M1 lever #5): offline A/B +0.20pp (szum, se~0.92pp), +57% wolniej. Flag `SCHEDULE_ADJUSTED_RATINGS` zostaje OFF; kod+7 testów jako infra.

---

## 📋 Następne kroki

1. **Pasywne (PRIORYTET):** zbieraj świeże settled — pipeline leci PC-niezależnie. Co kilka dni `calibration_monitor.py`: czy reweight 30/70 + Poisson ruszyły accuracy. Budżet AF 100/dzień.
2. **Sierpień:** zweryfikuj że quick_picks-fix → Poisson live (51.8%) zamiast Bzzoiro-ML.
3. **Po ~88 settled:** D2 auto-refit → `CALIBRATION_ENABLED=1`; D3 decyzja; flip selekcja #1 + gating #2.
4. **Opcjonalne:** parquet na cloud (→ cloud-draft Poisson).
5. **Sam koniec (D8):** JDG/prawnik (wstrzymane). Email/płatności po walidacji.

---

> **Ukończone → `CHANGELOG.md` + `git log`.** Ostatnie (07-03/04): reset hasła + panel Model vs Live + Kontuzje v2 (rdzeń) + kalibracja health-gate + **cloud migration** (pipeline PC-off) + 10 kuponów Admin_JG (3/3 WON) + Claude setup hardening (guard hook). Wcześniej (06-24/26): OWASP hardening + CI lint/security/coverage gate + cloud-draft live + reweight ku rynkowi + M1 lewary #1/#2 + 4 źródła danych + Daily DB Backup + walk-forward A/B (DC 51.8%). Jeszcze wcześniej: Cel A/B/C, D1-D7, multi-source, RODO, multi-user.
