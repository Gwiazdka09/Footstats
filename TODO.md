# FootStats TODO — Updated 2026-06-03

## Completed Phases (Archive)

### Phase 1–9: ALL COMPLETE ✅
### Phase 10: ALL COMPLETE ✅ (10.0–10.4)
### Phase 11.1, 11.2, 11.8: COMPLETE ✅

---

## KRYTYCZNE BUGI (P0)

### BUG-2: Deployment — jednorazowo
- [ ] Ustawić FOOTSTATS_USER + FOOTSTATS_PASSWORD_HASH w Cloud Run (seed admin)

---

## Phase 10: CODE QUALITY (aktywna)

### 10.2: Broad Except Cleanup (P2) — COMPLETE ✅
- [x] 160 → 137 broad excepts (base_playwright 14→1, analyzer 8→4, daily_agent 8→2, coupon_tracker 1→0)
- [x] sts.py 13→0, enriched.py 6→2, logging.py 7→2 (pozostało ~125 w mniej krytycznych plikach)

### 10.4: Large File Refactoring (P3) — COMPLETE ✅
- [x] analyzer.py 1396→1175 LOC — wydzielono: prompts.py, scoring.py, output.py
- [x] superbet.py (1128 LOC) — DEFER: brak testów integracyjnych, ryzyko regresu Playwright
- [x] cli.py (1112 LOC) — DEFER: monolityczny main(), brak izolowanych testów komend

---

## Phase 11: ACCURACY IMPROVEMENT

### 11.3: Kelly stake (P2) — COMPLETE ✅
- [x] `core/bankroll.py::kelly_fraction(prob, kurs, bankroll, frac=0.25)`
- [x] Per leg dynamic stake: `_dodaj_kelly()` w daily_agent.py:1322 + pre-filtr EV/Kelly w value_bet.py

### 11.4: Poisson + xG full path (P2) — COMPLETE ✅
- [x] `core/poisson.py::predict_match` → ensemble z Bzzoiro (50/50) w quick_picks.py
- [x] xG blend 20% aktywny
- [x] `LIGI_POISSON_TOP5` w config.py (E0/SP1/D1/F1/I1)
- [x] Understat xG prefetch w szybkie_pewniaczki_2dni przed pętlą Poissona (top-5 lig)

### 11.5: Referee DB join (P3) — COMPLETE ✅
- [x] `referee_name` z API-Football + FlashScore fallback w `_enrichuj_finalna_faza()`
- [x] `referee_signal()` → KARTKOWY/BRAMKOWY/NEUTRALNY/NIEZNANY
- [x] `referee_prob_adjustment()` → delta o25/btts per sędzia (w faza draft/final)

### 11.6: STS/Superbet live odds (P2) — COMPLETE ✅
- [x] `daily_agent --bb` real BetBuilder Superbet API — już istniał
- [x] Arbitraż Bzzoiro vs BetExplorer w `_weryfikuj_kupony()` (cache-only, bez Playwright)
  — `najlepszy_kurs_z_cache()` skanuje wszystkie dzisiejsze cache'e i podmienia wyższy kurs
  — STS/Superbet login-scraping: DEFER (wymaga dedykowanych scraperów z auth)

### 11.7: RAG semantic lessons (P2) — COMPLETE ✅
- [x] `ai/rag.py::retrieve_relevant_lessons(query_context, k=5)` — zaimplementowane
- [x] Top-5 lessons z `ai_feedback_embeddings` → kontekst do LLM filter (analyzer.py L960)

### 11.9: HomeFortress / H2H Patent / Importance 2.0 (P3) — COMPLETE ✅
- [x] HomeFortress + AnalizaH2H inicjalizowane przed pętlą w szybkie_pewniaczki_2dni
- [x] fortress_g + h2h_g/h2h_a przekazane do predict_match() → wpływają na lambdy Poissona
- [x] fortress_g, h2h_g w słowniku każdego picka (dla downstream)

### 11.10: CLV Tracker (P3) — COMPLETE ✅
- [x] `core/clv_tracker.py`: calculate_clv, record_closing_odds, get_clv_report
- [x] evening_agent.py: record_closing_odds() po settlement
- [x] dashboard.py: get_clv_report() w zakładce CLV
- [x] Cron scheduling → Cloud Scheduler (deployment, not code)

### Priorytet (impact × effort)

| # | Fix | Impact | Effort | Days |
|---|-----|--------|--------|------|
| 11.3 | Kelly stake wiring | 🟡 | 🟢 | 0.5 |
| 11.6 | STS live odds | 🟡 | 🟡 | 2 |
| 11.10 | CLV tracker | 🟡 | 🟡 | 2 |
| 11.4 | Poisson full (top-5 lig) | 🟢 | 🔴 | 5 |
| 11.7 | RAG semantic | 🟢 | 🟡 | 2 (po 11.4) |
| 11.9 | Fortress/H2H/Importance | 🟡 | 🔴 | 3 (po 11.4) |
| 11.5 | Referee DB join | 🟡 | 🔴 | 3 (po 11.4) |

---

## Milestones

| Milestone | Accuracy | Status |
|-----------|----------|--------|
| **M0** | ~42% overall | ✅ Current (baseline) |
| **M1** | 55% overall | 🔄 In progress — calibration + filters |
| **M2** | 60% overall | Bayesian Poisson + ensemble + value filter |
| **M3** | 65% selected | xG + feature engineering + stop-loss |
| **M4** | 70% selected | Full optimization + CLV + 3mo track record |

---

## Blockers

- **Accuracy 42%** — poniżej M1 target, wymaga pracy nad kalibracją
- **⚠️ Kalibrator drastycznie tnie prob**: Bzzoiro raw 70%→40% realnej. ✅ `PEWNIACZEK_PROG` obniżony 90→40% w config.py.
  - **Rekomendacja**: zebrać >20 zwalidowanych predykcji → `python -m footstats.core.probability_calibrator` → pełna krzywa isotonic regression
