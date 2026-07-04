# FootStats TODO — Lipiec 2026

**Aktualizacja:** 2026-07-04 · v3.4-stable
**Accuracy:** offline **51.8%** (WF A/B, DC W=0.5) | live świeże ≥06-19 **47.8%** (23 settled, fixy Cel B) vs stare 31%
**Cel M1:** 55% win rate · **Suite:** ~1436 pass (coverage 57)
**LIVE:** pipeline **PC-off w chmurze** — Cloud Run Jobs (final 11:00 + evening 23:00) + Scheduler (draft 07:30, settle 06:00/21:30). Szczegóły → `docs/cloud_migration.md`.
**Zbudowane flag-OFF (flip po walidacji):** `SELECTION_MIN_CONF` (#1) · `LEAGUE_GATING` (#2). Już LIVE: `ENSEMBLE_MARKET_WEIGHT=0.70` (reweight ku rynkowi).

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

- [ ] **Co kilka dni:** `python scripts/calibration_monitor.py` (Neon, read-only) — System vs Pipeline, czy accuracy ruszyła, licznik settled. Ma per-liga + **flip-advisor** (`core/flip_advisor.py`): rekomenduje czy flipnąć `SELECTION_MIN_CONF` i które ligi do `LEAGUE_GATING` (<50%, n≥8).
- [ ] **D3 — pełna decyzja a/b/c** (próg guardu, czy argmax na stałe) — po ~20 ŚWIEŻYCH settled z zapisanym prob. Zwaliduj że guard pomaga, dostrój próg. (D3 cz.1+2 prob+guard ZROBIONE 06-22.)
- [ ] **Po ~88 settled → D2 auto-refit sam** (delta +30 od n_train); gdy krzywa zdrowa → włącz `CALIBRATION_ENABLED=1`.
- [ ] **DECYZJA (nie bug):** Bzzoiro etykietuje towarzyskie kadr jako "World Cup 2026" → whitelist MŚ (D1a). Opcje: (a) zostaw MŚ [domyślnie], (b) wyklucz kadry z kuponów Groq, (c) zawęź whitelist do realnych fixture'ów WC.

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
- [ ] **Kontuzje v2 — scrape per-gracz** goal_share (waga udziałem w golach: utrata strzelca > rezerwowy). Rdzeń `injury_lambda_factors` ZBUDOWANY (07-03) — czeka na multi-source scraper udziałów.

---

## 🔵 P3 — MONETYZACJA / LAUNCH (wymaga Ciebie, WSTRZYMANE do walidacji)

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
