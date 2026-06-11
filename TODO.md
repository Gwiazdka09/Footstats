# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-11
**Wersja:** v3.4-stable
**Accuracy baseline:** 33% (12/35 live settled, Neon.tech)
**Cel na koniec lipca:** M1 = 55% win rate

> Historia ukończonych zadań: `git log` (commity TD/16.x/15.x mają opisowe nazwy)

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

## 🔴 FAZA 16: ACCURACY FIXES (przed betą)

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

### TD23: settle_active_coupons — brak filtra po dacie/test danych
- [ ] Dodać `WHERE status='ACTIVE' AND match_date_first <= today` (lub filtr user_id) — zapobiec ponownemu zapchaniu pętli przez dane testowe
- [ ] Zweryfikować jutrzejszy run FootStats-DailyAgentDraft/Final (08:00/11:00) — czy LastTaskResult=0 po usunięciu 21 śmieciowych kuponów
- **Effort:** 30 min | 🔴 P1

---

## ⚪ FAZA 15: NOWE FEATURE'Y

### 15.3: Odds comparison — STS 1X2 vs nasze predykcje
- [x] `scrapers/sts_kursy.py` + 23 testy — pobiera kursy 1X2 ze STS, liczy EV vs nasze p_wygrana/p_remis/p_przegrana (commit cf36f73c9)
- [ ] Rozszerzyć na Fortuna/LV BET (ten sam wzorzec co sts_kursy.py)
- **Effort:** 1–2 dni per bukmacher | ⏸️ odkładamy

### 15.7: Strefa Inspiracji — sygnał od top typerów STS
- [x] Moduł `scrapers/sts_inspiracje.py`: `parse_popular_tickets` (Strefa Inspiracji "Popularne kupony") + `normalize_market_tip`
- [x] Matching po drużynach (`znajdz_kurs`/`_match_score` z sts_kursy.py) → `dopasuj_do_predykcji`
- [x] Wycena kombo modelem Poisson (`_joint_probability` + `oblicz_tip_correct`) → `ocen_sygnal` (VALUE/NO_VALUE/BRAK_MODELU)
- [x] Testy: `tests/test_sts_inspiracje.py` (18/18 PASS)
- [ ] Wpięcie do daily_agent (krok opcjonalny, nieblokujący)
- **Effort:** 1 dzień | 🟡 w trakcie (parsing+model gotowe, wpięcie do daily_agent zostało)

### 15.8: BetBuilder — rekomendacje ze strony głównej STS
- [x] Homepage `/` karuzela `.bet-builder-recommendation` — parser `parse_betbuilder_carousel` w `scrapers/sts_inspiracje.py`
- [x] Value vs nasze predykcje — wspólna logika `ocen_sygnal`/`dopasuj_do_predykcji` (jak 15.3)
- **Effort:** 0.5 dnia | ✅ gotowe (parsing+wycena), wymaga commitu

### 15.6: Multi-user support
- [ ] Per-user bankroll, risk profile, Telegram chat_id
- **Effort:** 3–5 dni | ⏸️ po M1

---

## 💡 Pomysły od betatesterów

(brak otwartych — dodawaj nowe tutaj)
