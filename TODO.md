# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-04  
**Wersja:** v3.4-stable  
**Accuracy baseline:** 42.4% (14/33 settled kuponów)  
**Cel na koniec lipca:** M1 = 55% win rate

---

## Archiwum ukończonych faz

Phase 1–9: ✅ DONE  
Phase 10 (Code Quality): ✅ DONE (10.0–10.4)  
Phase 11 (Accuracy Features): ✅ DONE (11.1–11.10)  

Wszystkie feature'y accuracy już shipped (Poisson+xG, Kelly, RAG semantic, referee, H2H/Fortress, CLV, kalibracja, LLM filter, BetExplorer arbitraż). Problem: accuracy nadal 42% — feature'y wdrożone, ale **nie zmierzone na żywych danych** bo agent nie działa od 25.05.

---

## 🔴 FAZA 12: RATOWANIE PIPELINE'U (P0 — tydzień 1)

Pipeline stoi od 25.05. Bez działającego agenta nie zbieramy danych do kalibracji i nie dostarczamy predykcji użytkownikom. To blokuje wszystko inne.

### 12.1: Git commit niezapisanych zmian
- [ ] `git add -A && git commit -m "sync: 45 uncommitted changes from May/June"`
- **Dlaczego:** 45 niezcommitowanych plików (~13k linii zmian). Jeden crash dysku = utrata miesiąca pracy.
- **Effort:** 5 min

### 12.2: Rozliczenie zaległych kuponów ✅
- [x] Sprawdzono DB: 25 ACTIVE kuponów (nie 101 — dane z TODO były przeszacowane)
- [x] 19 dummy kuponów (match_date_first=2099) → VOID (test data, brak realnych meczów)
- [x] 6 starych kuponów (2026-05-30, 2026-06-01) → VOID (API-Football free plan: tylko ±2 dni)
- [x] Accuracy po rozliczeniu: **26.7%** (4/15 predictions z tip_correct), 0/2 na poziomie kuponów
- **Uwaga:** Stara wartość 42.4% z TODO była z innego datasetu (dane lokalne SQLite przed migracją do Neon.tech)

### 12.3: Diagnoza i restart daily agenta ✅
- [x] Przyczyna crash: `bankroll.py` używał SQLite `DATETIME('now','-7 days')` → PostgreSQL crash
- [x] Fix: zmieniono na `NOW() - INTERVAL '7 days'` (bankroll.py:141)
- [x] Fix: `checkpoint.py` — datetime nieserializable → `json.dumps(..., default=str)`
- [x] Fix: Playwright Chromium nie był zainstalowany → `playwright install chromium`
- [x] Groq AI ✅, Bzzoiro ✅ (50 lig), SofaScore ✅, Understat 404 dla nie-top5 lig (normalnie)
- [x] Daily agent działa end-to-end — kupon zapisany: `logs/kupon_2026-06-04.txt`
- [ ] TODO: przywrócić automatyczny scheduling (run_daily.bat / Cloud Scheduler) — osobne zadanie

### 12.4: Reset bankrollu ✅
- [x] user_id=1 (system): 58 PLN → 500 PLN
- [x] user_id=2 (admin): 150 PLN → 500 PLN
- [x] bankroll_history zachowana (archiwum historyczne)

### 12.5: Cloud Run env vars (BUG-2) — RĘCZNA AKCJA
- [ ] W Cloud Console → Cloud Run → footstats-api → Edit → Variables:
  - `FOOTSTATS_USER=<username>`
  - `FOOTSTATS_PASSWORD_HASH=<bcrypt_hash>`
- [ ] Zweryfikować: `curl https://<service-url>/health`
- **Uwaga:** gcloud niedostępny lokalnie — wymaga Cloud Console lub ! gcloud run services update
- **Effort:** 30 min

---

## 🟡 FAZA 13: KALIBRACJA I POMIAR (P1 — tydzień 2–3)

Agent znów działa (po fazie 12). Teraz zbieramy dane i kalibrujemy model.

### 13.1: Zebranie minimum 50 nowych predykcji z live'u
- [ ] Przez ~2 tygodnie daily agent generuje i rozlicza kupony automatycznie
- [ ] Monitorować logi codziennie (5 min/dzień)
- [ ] Cel: minimum 50 settled kuponów z nowymi feature'ami (Poisson+xG, referee, H2H)
- **Dlaczego:** Kalibrator potrzebuje danych. Dotychczasowe 33 settled to za mało, a dane sprzed wdrożenia feature'ów nie są miarodajne.
- **Effort:** ~2 tygodnie pasywnego zbierania

### 13.2: Uruchomienie kalibratora
- [ ] `python -m footstats.core.probability_calibrator`
- [ ] Wygenerować nową krzywą isotonic regression z danych po feature'ach 11.x
- [ ] Sprawdzić czy Bzzoiro raw 70% → kalibrowane prob jest bliższe realności
- [ ] Zapisać `data/model_calibration.json` z nową krzywą
- **Dlaczego:** Kalibrator to kluczowy element. Bzzoiro mówi 70% pewności, a realnie trafia w 42%. Kalibracja powinna to skorygować i dać lepsze decyzje Kelly.
- **Effort:** 1h (po zebraniu danych)

### 13.3: Pomiar accuracy per feature
- [ ] Porównać accuracy meczów z top-5 lig Poissona vs reszta
- [ ] Porównać accuracy meczów z danymi sędziowskimi vs bez
- [ ] Porównać accuracy meczów z H2H/Fortress vs bez
- [ ] Wyciągnąć wnioski: które feature'y realnie pomagają
- **Dlaczego:** Mamy 8 feature'ów accuracy, ale nie wiemy który działa. Może Poisson pomaga a referee nie — trzeba wiedzieć co dalej optymalizować.
- **Effort:** 2–3h (query + analiza)

### 13.4: A/B test — ensemble wagi
- [ ] Przetestować różne wagi ensemble: 50/50 Poisson/Bzzoiro → 60/40 → 70/30
- [ ] Backtest na zebranych danych (walkforward validation)
- [ ] Ustawić optymalne wagi w config
- **Dlaczego:** Domyślne 50/50 mogło nie być optymalne. Z danymi z live'u możemy to zmierzyć.
- **Effort:** 3–4h

---

## 🟡 FAZA 14: STABILIZACJA PRODUKCJI (P2 — tydzień 3–4)

### 14.1: Monitoring i alerting ✅
- [x] `/health` rozbudowane: last_prediction_date, agent_ok (>26h), bankroll_pln, rolling_accuracy_pct
- [x] `telegram_notify.send_alert()` — ogólny alert
- [x] `check_and_alert_agent_down()` — wywołane w evening_agent po settlement
- [x] `check_and_alert_accuracy(35%, window=20)` — wywołane w daily_agent na starcie

### 14.2: Auto-settlement cron
- [ ] evening_agent jako scheduled job (Cloud Scheduler lub cron)
- [ ] Rozliczenie kuponów automatycznie co wieczór o 23:00
- [ ] Retry logic jeśli API wyników nie odpowiada
- **Dlaczego:** 101 nierozliczonych kuponów = brak feedbacku → brak kalibracji → accuracy nie rośnie.
- **Effort:** 2h

### 14.3: Broad except cleanup — runda 2
- [ ] Zredukować z ~125 do <50 broad excepts
- [ ] Priorytet: daily_agent, analyzer, scraperzy (te co mogą cicho połknąć błędy pipeline'u)
- **Dlaczego:** Broad except może tłumić prawdziwe błędy. Agent mógł umrzeć właśnie przez to — błąd został złapany ale nie obsłużony.
- **Effort:** 4–6h

### 14.4: Testy integracyjne pipeline'u
- [ ] Test end-to-end: daily_agent → scrape → predict → kupon → DB (z mockami API)
- [ ] Test: evening_agent → fetch results → settle → feedback → RAG update
- [ ] Dodać do CI (GitHub Actions)
- **Dlaczego:** 431 unit testów przechodzi, ale nie testujemy czy cały pipeline od A do Z działa razem.
- **Effort:** 1 dzień

---

## ⚪ FAZA 15: NOWE FEATURE'Y (P3 — lipiec, po osiągnięciu M1)

Te zadania mają sens dopiero gdy accuracy >= 55% i pipeline jest stabilny.

### 15.1: Stop-loss mechanizm
- [ ] Automatyczne zatrzymanie agenta gdy strata > X% bankrollu w ciągu dnia/tygodnia
- [ ] Konfigurowalny próg w config.py (np. -20% dziennie, -40% tygodniowo)
- [ ] Powiadomienie Telegram + log
- **Dlaczego:** Brak stop-loss = agent może spalić cały bankroll w jeden zły dzień.
- **Effort:** 3–4h

### 15.2: STS/Superbet scraper z auth
- [ ] Dedykowany scraper z logowaniem na STS
- [ ] Dedykowany scraper z logowaniem na Superbet
- [ ] Porównanie kursów STS vs Superbet vs BetExplorer → najlepszy kurs do kuponu
- **Dlaczego:** Aktualnie używamy BetExplorer cache-only. Prawdziwe kursy bukmacherów mogą dać lepsze arbitraże.
- **Effort:** 3–5 dni (każdy bukmacher to osobny Playwright scraper z auth)

### 15.3: Dashboard UX
- [ ] Filtrowanie po lidze, dacie, typie zakładu
- [ ] Wykres accuracy over time (rolling 20-kupon window)
- [ ] Wykres bankroll over time
- [ ] Export kuponów do PDF/CSV
- **Dlaczego:** Dashboard istnieje ale jest podstawowy. Użytkownik nie widzi trendów.
- **Effort:** 1–2 dni

### 15.4: Multi-user support
- [ ] Różne profile ryzyka (conservative / balanced / aggressive)
- [ ] Per-user bankroll tracking
- [ ] Per-user Telegram notifications
- **Dlaczego:** Obecnie system jest single-user. Dla skalowalności trzeba to rozdzielić.
- **Effort:** 3–5 dni

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M0** | 42% baseline | ✅ Done | Zmierzony na 33 kuponach |
| **M1** | 55% win rate | 🔴 Blocked | Pipeline nie działa, brak nowych danych. **Faza 12 → 13 odblokuje** |
| **M2** | 60% win rate | ⏸️ | Po M1 — tuning wag ensemble + kalibracja |
| **M3** | 65% (selected) | ⏸️ | Po M2 — stop-loss + filtrowanie na pewne ligi |
| **M4** | 70% (selected) | ⏸️ | 3 miesiące track record + CLV pozytywne |

---

## Blockers (stan na 2026-06-04)

| # | Blocker | Blokuje | Rozwiązanie |
|---|---------|---------|-------------|
| 1 | ~~Agent nie działa od 25.05~~ | ~~Wszystko~~ | ✅ Faza 12.3 — naprawiono 3 bugi (bankroll/checkpoint/playwright) |
| 2 | ~~101 nierozliczonych kuponów~~ | ~~Pomiar accuracy~~ | ✅ Faza 12.2 — zvoided, acc=26.7% |
| 3 | **45 niezcommitowanych zmian** | Bezpieczeństwo kodu | Faza 12.1 |
| 4 | ~~Bankroll 0 PLN~~ | ~~Kelly~~ | ✅ Faza 12.4 — reset do 500 PLN |
| 5 | **Cloud Run brak admin seeda** | API niedostępne publicznie | Faza 12.5 |
| 6 | **Accuracy 42%** | Zaufanie użytkowników | Faza 13 (kalibracja po danych) |

---

## Porządki (nice-to-have, robimy przy okazji)

- [ ] Usunąć duplikat `validation_errors.csv` z root (zostawić w `data/`)
- [ ] Usunąć `tests/scratch` (debug plik)
- [ ] Usunąć `data/.fuse_hidden*` (3 orphan pliki)
- [ ] Zarchiwizować 12 plików DAILY_ANALYSIS z `docs/`
- [ ] Naprawić 11x `conn.close()` bez context manager (bankroll.py, json_export.py, coupon_tracker.py)
