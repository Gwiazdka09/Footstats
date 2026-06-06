# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-06  
**Wersja:** v3.4-stable  
**Accuracy baseline:** 26.7% (15 live settled, Neon.tech)  
**Cel na koniec lipca:** M1 = 55% win rate

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M0** | 42% baseline | ✅ Done | 33 kupony SQLite lokalny |
| **M0b** | 26.7% live baseline | ✅ Done | 15 kuponów Neon.tech |
| **M1** | 55% win rate | 🔴 W toku | min. 50 settled + kalibracja |
| **M2** | 60% win rate | ⏸️ | Po M1 — tuning wag ensemble |
| **M3** | 65% selected | ⏸️ | Po M2 — stop-loss + filtrowanie lig |
| **BETA** | Testerzy | ⏸️ | Po M1 — stabilna accuracy |

---

## 🔴 FAZA 16: ACCURACY FIXES (przed betą — teraz)

### 16.1: Filtr ligowy — odrzucaj mecze bez danych Poisson
- [ ] W daily_agent (krok 1): sprawdź czy `predict_match()` != None przed dodaniem meczu
- [ ] Jeśli None → skip (towarzyskie Afryka/Azja/CONCACAF bez historii Poissona)
- [ ] Dodać `ALLOWED_LEAGUES` whitelist w `config.py`
- **Efekt:** mniej kuponów ale znacznie lepsze; koniec z decision_score=25
- **Effort:** 2–3h | Plik: `daily_agent.py` KROK 1 + `config.py`

### 16.2: Podnieść próg PROG_DRAFT → 50
- [ ] `core/decision_score.py`: `PROG_DRAFT = 50` (było 40)
- [ ] Fallback: jeśli < 3 kandydatów po filtrze → akceptuj 40 (nie generuj śmieciowego kuponu)
- **Effort:** 30 min

### 16.3: Void kupon #33 (Ajax vs PSV — sezon skończony)
- [ ] `UPDATE coupons SET status='VOID' WHERE id=33`
- **Effort:** 2 min

### 16.4: Kalibracja modelu (po 50 settled)
- [ ] `python -m footstats.core.probability_calibrator`
- [ ] A/B test wag: 50/50 → 60/40 → 70/30 Poisson/Bzzoiro
- [ ] Zapisać `data/model_calibration.json`
- **Effort:** 2–3h | Warunek: min. 50 settled live kuponów

### 16.5: Zbieranie danych (pasywne — 3 tygodnie)
- [ ] Daily agent działa automatycznie (Task Scheduler 08:00 + 11:00 + 23:00)
- [ ] Monitorować logi: `logs/kupon_YYYY-MM-DD.txt`
- [ ] Cel: 50 settled kuponów z filtrowanymi ligami

---

## 🔧 TECH DEBT

### TD3: Redukcja broad except (P2)
- [x] cli.py 6x, form_scraper.py 4x, bzzoiro.py 4x, superbet.py 1x, superbet_bb.py 4x, flashscore_match.py 4x
- [ ] Pozostałe ~25x: circuit_breaker, async_utils, api_football, enriched, flashscore_results, understat_xg, superoferta, kursy, migrations, runner, smoke_api
- **Effort:** ~2h

### TD4: Rozbicie dużych plików (P3)
- [ ] `daily_agent.py` (1474 LOC) → wydzielić kroki do osobnych modułów
- [ ] `analyzer.py` (1175 LOC) → wydzielić helpery
- **Effort:** 4–6h

### ~~TD1~~ ~~TD2~~ ~~TD5~~ ~~TD6~~ ~~TD7~~ ~~TD8~~ — ✅ DONE

---

## ⚪ FAZA 15: NOWE FEATURE'Y (po M1=55%)

### 15.1: Stop-loss mechanizm
- [ ] Auto-pause gdy strata > 20% bankrollu w ciągu 7 dni
- [ ] Telegram alert + status `PAUSED` + wznowienie przez dashboard
- **Effort:** 3–4h

### 15.2: CLV tracking (Closing Line Value)
- [ ] Porównaj kurs obstawiania vs kurs zamknięcia
- [ ] Kolumny w tabeli `predictions` już przygotowane
- **Effort:** 3–5h

### 15.3: Odds comparison — STS/Fortuna/LV BET
- [ ] Playwright login → porównaj kursy, wybierz najwyższy
- **Effort:** 1–2 tygodnie

### 15.4: Dashboard UX v2
- [ ] Filtrowanie po lidze/dacie/typie, accuracy per liga, bankroll chart
- **Effort:** 1–2 dni

### 15.5: Telegram komendy interaktywne
- [ ] `/status`, `/kupon`, `/void <id>`, `/stats`
- **Effort:** 4–6h

### 15.6: Multi-user support
- [ ] Per-user bankroll, risk profile, Telegram chat_id
- **Effort:** 3–5 dni

---

## Fazy ukończone

Phase 1–14: ✅ DONE — szczegóły: `git log`, `docs/archive/`
