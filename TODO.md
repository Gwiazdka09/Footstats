# FootStats TODO — Updated 2026-05-31

## Completed Phases (Archive)

### Phase 1–9: ALL COMPLETE ✅
### Phase 10.0–10.3, 10.6–10.8: COMPLETE ✅

---

## KRYTYCZNE BUGI (P0) — natychmiastowe

### BUG-1: Ten sam kupon na Telegramie od kilku dni ✅
- [x] Deduplication kuponów — hash SHA256

### BUG-3: 7x truncated files (P0) ✅
- [x] quick_picks.py, response_cache.py, bankroll.py, coupons.py, auth.py, main.py, migrations.py
- [x] Przywrócone z git HEAD — 2026-05-31

### BUG-2: Brak logowania do /preview (Cloud Run) ✅
- [x] Kod: warning log + /health rozszerzony
- [x] Migration v4: kolumna `is_admin` w tabeli `users`
- [x] JWT zawiera flagę `adm` (is_admin)
- [x] `require_admin` dependency — 403 dla non-admin
- [x] Admin API: `GET/POST /api/admin/users`, `DELETE /api/admin/users/{id}`
- [x] Walidacja hasła min. 8 znaków przy tworzeniu usera
- [x] Audit log każdej operacji na userach
- [x] 15 nowych testów — 78/78 zielone
- [ ] Deployment: ustawić FOOTSTATS_USER + FOOTSTATS_PASSWORD_HASH w Cloud Run (jednorazowo dla seed admina)

---

## Phase 10: CODE QUALITY & ACCURACY (aktywna)

### 10.2: Broad Except Cleanup (P2) — PARTIAL
- [x] 48 cichych `except Exception` naprawionych
- [ ] Pozostało ~172 — priorytet: superbet, base_playwright, sts, analyzer

### 10.4: Large File Refactoring (P3)
- [x] daily_agent.py — _build_parser() wydzielony
- [ ] analyzer.py (1396 LOC) — wydzielić: prompts, scoring, output formatting
- [ ] superbet.py (1128 LOC) — wydzielić: auth, scraping, parsing
- [ ] cli.py (1112 LOC) — wydzielić komendy do submodułów

### 10.5: Cache Auto-Eviction (P3) — NEW
- [ ] Dodać auto-czyszczenie cache >30 dni (817 plików, 283MB)
- [ ] Skrypt/cron do okresowego czyszczenia

### 10.9: Commit & Push (P1) ⚠️
- [ ] **50 uncommitted changes** — KRYTYCZNE, wzrost z 38→50, ryzyko utraty pracy

### 10.10: Cleanup zbędnych plików (P4) — NEW
- [ ] Usunąć scripts/add_logging.py, scripts/fix_logging_fstrings.py (jednorazowe)
- [ ] Oczyścić stare logi w logs/ (>14 dni)
- [ ] Rozważyć archiwizację docs/DAILY_ANALYSIS_*.md (9 plików)

---

## Phase 11: ACCURACY IMPROVEMENT (planowana)

### 11.1: Kalibracja modelu (P2)
- [ ] Analiza rozbieżności Poisson vs rzeczywiste wyniki
- [ ] Tuning parametrów kalibracji w model_calibration.json
- [ ] A/B test: Bayesian Poisson vs klasyczny

### 11.2: Value Bet Filter (P2)
- [ ] Zaostrzenie filtra value_bet — wyższy margin
- [ ] Dodanie confidence threshold przed wysyłką

### 11.3: Ensemble Weights (P3)
- [ ] Optymalizacja wag ensemble (Poisson + xG + form + H2H)
- [ ] Walk-forward validation na danych historycznych

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
- **38 uncommitted changes** — ryzyko utraty pracy
- **⚠️ Kalibrator drastycznie tnie prob** (po Phase 11.2) — Bzzoiro raw 70%→40% realnej, prog domyślny 75% w `_typy_pewne` staje się nieosiągalny. Konsekwencje:
  - Stare wywołania `szybkie_pewniaczki_2dni(b)` z domyślnym `prog=PEWNIACZEK_PROG` (75%) zwracają **0 wyników**
  - Trzeba albo:
    1. Wywoływać z `prog=35-40%` (workaround — patrz `_tmp_save_send.py` / kupony #14-16)
    2. Zmienić `PEWNIACZEK_PROG` w `config.py` na 40% (breaking change dla innych modułów)
    3. Rozbudować `_FALLBACK_TABLE` w `probability_calibrator.py` o większą próbkę (>20 predictions in DB) → `fit_calibrator()` zbuduje pełną krzywą isotonic regression
  - **Rekomendacja**: opcja #3 — uruchomić `python -m footstats.core.probability_calibrator` po zebraniu >20 zwalidowanych predykcji

---

## Phase 11: PIPELINE COMPLETENESS — audyt 2026-05-30

**Kontekst**: kupon generation (5 PLN × 3 cele 30/100/300 PLN, coupons #14/15/16) używał TYLKO Bzzoiro ML + EV filter + dedup. Pominięto większość modułów accuracy-boost. Lista co dopiąć.

### Użyte ✅
- Bzzoiro ML (`scrapers/bzzoiro.py`) — prob 1/X/2/BTTS/Over
- Bzzoiro odds snapshot — kursy referencyjne
- `szybkie_pewniaczki_2dni` (`core/quick_picks.py`) — scan 72h prog≥55%
- `_scout_bot_ocen` — EV = P×kurs−1
- `save_coupon` (`core/coupon_tracker.py`) — DRAFT do `coupons`
- `send_kupon` + dedup SHA256 (`utils/telegram_notify.py`)

### NIE użyte ❌ — fixy

#### 11.1: Ollama lokalny (P1) — COMPLETE ✅
- [x] Sprawdzone `curl localhost:11434/api/tags` — qwen2.5:7b, gemma2:9b, deepseek-r1:7b dostępne (brak llama3.1:8b)
- [x] `ai/client.py`: env overrides `OLLAMA_MODEL` (default `qwen2.5:7b`), `OLLAMA_URL`, `AI_PREFER_LOCAL`
- [x] `_ollama_available()`: probe `/api/tags`, weryfikacja modelu
- [x] `zapytaj_ai()`: branching prefer_local → Ollama→Groq fallback; default → Groq→Ollama fallback
- [x] Test: `_ollama_available()=True`, model `qwen2.5:7b` wykryty

#### 11.2: Probability Calibrator wpięty (P1) — COMPLETE ✅
- [x] `core/probability_calibrator.py::calibrate_confidence` wpięte w `quick_picks.py` po `_bzz_parse_prob`
- [x] Kalibracja `pw/pr/pp/bt/o25` przed `_typy_pewne` i `_scout_bot_ocen`
- [x] Surowe wartości zachowane jako `pw_raw/pr_raw/pp_raw/bt_raw/o25_raw` w dict wyniku
- [x] **Effekt empiryczny**: Bzzoiro raw 55%→17%, 65%→40%, 70%→40%, 80%→33% (fallback table 2026-05-26)
- [x] **UWAGA**: prog domyślny 75% staje się nieosiągalny — wymaga rekalibracji na większej próbce lub obniżenia prog do ~40%
- [x] Test: 809/809 passed, sample Cerezo Osaka pw_raw=52.2%→pw_cal=17.1%

#### 11.3: Kelly stake (P2) 🟡 mid / 🟢 low
- [ ] `core/bankroll.py::kelly_fraction(prob, kurs, bankroll, frac=0.25)`
- [ ] Per leg dynamic stake zamiast flat 5 PLN
- [ ] **Why**: long-term ROI wzrost, mniej risk na low-EV

#### 11.4: Poisson + xG full path (P2) 🟢 high / 🔴 high
- [ ] Auto-loop top-5 lig (Brasileirão A, Champions, Bundesliga, La Liga, Premier)
- [ ] `data/historical_loader.py` → df_mecze per liga
- [ ] `core/poisson.py::predict_match` → ensemble z Bzzoiro prob (waga 50/50)
- [ ] xG blend już w `poisson.py:199-213` (20%), pre-fetch Understat dla top-5
- [ ] **Why**: M2 target 60% accuracy

#### 11.5: Referee DB join (P3) 🟡 mid / 🔴 high
- [ ] Brak `referee_name` w Bzzoiro feed → join niemożliwy
- [ ] FlashScore scraper (`scrapers/flashscore_results.py`) ma URL meczu → wyciąg sędziego
- [ ] Tabela `referees` (PostgreSQL, already migrated) → bias kart/karnych
- [ ] Korekta BTTS/Over per sędzia (strict ref → mniej goli)
- [ ] **Why**: +3-5% accuracy BTTS/Over markets

#### 11.6: STS/Superbet live odds (P2) 🟡 mid / 🟡 mid
- [ ] `daily_agent --bb` real BetBuilder Superbet API (~3min Playwright)
- [ ] Arbitraż: max kurs spośród (Bzzoiro / STS / Superbet)
- [ ] **Why**: +3-8% wypłata per kupon, weryfikacja stale Bzzoiro odds

#### 11.7: RAG semantic lessons (P2) 🟢 high / 🟡 mid
- [ ] `ai/rag.py::retrieve_relevant_lessons(query_context, k=5)` wymaga `pred` dict z `predict_match` (factors: PATENT/TWIERDZA/ROTACJA)
- [ ] Dependency: 11.4 (Poisson path)
- [ ] Top-5 lessons z `ai_feedback_embeddings` → kontekst do LLM filter
- [ ] **Why**: model uczy się z przeszłych pudeł

#### 11.8: LLM Scout filter (P2) 🟢 high / 🟢 low
- [ ] Po wyborze top-N picks → `ai/analyzer.py::oceń_kupon(legs, kontekst)` → reasoning + decision_score 0-100
- [ ] Veto na kuponach score < 50
- [ ] **Why**: LLM łapie sytuacje których Poisson/Bzzoiro nie widzi (kontuzje, derby, motywacja)

#### 11.9: HomeFortress / H2H Patent / Importance 2.0 (P3) 🟡 mid / 🔴 high
- [ ] Per pick: detect liga → `_oblicz_sile_wazona` historical → mnożniki fortress/patent/importance
- [ ] Dependency: 11.4 (df_mecze per liga)
- [ ] **Why**: dom-twierdze (+10% obrona), H2H patenty (+10% atak), final/relegation boost

#### 11.10: CLV Tracker (P3) 🟡 mid / 🟡 mid
- [ ] Cron 5min przed startem meczu → snapshot closing odds
- [ ] CLV = (kurs_otwarcia − kurs_zamkniecia) / kurs_zamkniecia
- [ ] **Why**: CLV+ predicts long-term ROI lepiej niż short-term win rate

### Priorytet (impact × effort)

| # | Fix | Impact | Effort | Days |
|---|-----|--------|--------|------|
| 11.1 | Ollama lokalny | 🟢 | 🟢 | 0.5 |
| 11.3 | Kelly stake | 🟡 | 🟢 | 0.5 |
| 11.8 | LLM Scout filter | 🟢 | 🟢 | 1 |
| 11.2 | Probability calibrator | 🟢 | 🟡 | 1 |
| 11.6 | STS live odds | 🟡 | 🟡 | 2 |
| 11.10 | CLV tracker | 🟡 | 🟡 | 2 |
| 11.4 | Poisson + xG full | 🟢 | 🔴 | 5 |
| 11.7 | RAG semantic | 🟢 | 🟡 | 2 (po 11.4) |
| 11.9 | Fortress/H2H/Importance | 🟡 | 🔴 | 3 (po 11.4) |
| 11.5 | Referee DB join | 🟡 | 🔴 | 3 (po 11.4) |

**Sequence**: 11.1 → 11.3 → 11.8 → 11.2 → 11.4 → reszta
