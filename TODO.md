# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-05  
**Wersja:** v3.4-stable  
**Accuracy baseline:** 26.7% (4/15 z live Neon.tech)  
**Cel na koniec lipca:** M1 = 55% win rate

---

## Fazy ukończone

Phase 1–14: ✅ DONE  
Szczegóły: git log, docs/archive/

---

## ⏳ FAZA 13: KALIBRACJA I POMIAR (pasywna — tydzień 2–3)

Nie wymaga kodowania. Daily agent zbiera dane automatycznie.

### 13.1: Zebranie minimum 50 predykcji z live'u
- [ ] Monitorować logi codziennie (5 min/dzień): `logs/kupon_YYYY-MM-DD.txt`
- [ ] Cel: 50 settled kuponów z nowymi feature'ami (Poisson+xG, referee, H2H)
- **Effort:** ~2 tygodnie pasywne

### 13.2: Uruchomienie kalibratora (po zebraniu danych)
- [ ] `python -m footstats.core.probability_calibrator`
- [ ] Sprawdzić czy Bzzoiro raw 70% → kalibrowane prob bliżej realności
- [ ] Zapisać `data/model_calibration.json` z nową krzywą
- **Effort:** 1h

### 13.3: Pomiar accuracy per feature (po zebraniu danych)
- [ ] Porównać accuracy: Poisson top-5 vs reszta, sędzia vs bez, H2H vs bez
- **Effort:** 2–3h

### 13.4: A/B test — ensemble wagi (po 13.3)
- [ ] Przetestować 50/50 → 60/40 → 70/30 Poisson/Bzzoiro
- [ ] Backtest walkforward, zapisać optymalne wagi w config
- **Effort:** 3–4h

---

## ⚪ FAZA 15: NOWE FEATURE'Y (P3 — lipiec, po M1=55%)

### 15.1: Stop-loss mechanizm
- [ ] Auto-stop gdy strata > X% bankrollu w ciągu dnia/tygodnia
- [ ] Konfigurowalne progi w config.py + Telegram alert
- **Effort:** 3–4h

### 15.2: STS/Superbet scraper z auth
- [ ] Playwright login STS + Superbet → porównanie kursów z BetExplorer
- **Effort:** 3–5 dni

### 15.3: Dashboard UX
- [ ] Filtrowanie po lidze/dacie/typie, wykresy accuracy + bankroll over time
- **Effort:** 1–2 dni

### 15.4: Multi-user support
- [ ] Per-user profile ryzyka, bankroll, Telegram notifications
- **Effort:** 3–5 dni

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M0** | 42% baseline | ✅ Done | 33 kupony (SQLite lokalny) |
| **M0b** | 26.7% live baseline | ✅ Done | 15 kuponów Neon.tech po cleanup |
| **M1** | 55% win rate | 🔴 Waiting | Faza 13 — min. 50 settled kuponów |
| **M2** | 60% win rate | ⏸️ | Po M1 — tuning wag ensemble |
| **M3** | 65% selected | ⏸️ | Po M2 — stop-loss + filtrowanie lig |

---

## Blockers (stan na 2026-06-05)

Wszystkie blokery z fazy 12 zlikwidowane. Jedyne ograniczenie: brak danych do kalibracji (zbieramy na żywo).

---

## Drobne porządki

- [ ] 12.5: Cloud Run — admin seed ✅ done, zweryfikowane przez /health
- [ ] Naprawić 2 pre-existing testy: `test_quick_picks_ensemble::test_blend_50_50_applied` + `test_telegram::test_send_kupon_test_data`
