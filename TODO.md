# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-14
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

### 16.3: Draw bias — model faworyzuje remisy
- [x] Root cause: FINAL_REMIS_BOOST overshoot dla niskich lambd
- [x] Fix: sufit p_remis=40% w poisson.py
- [ ] A/B: porównaj trafność remisów vs 1/2 w ostatnich 35 settled (warunek: 50 settled)
- **Effort:** A/B po 16.4 | 🔴 P1

### 16.4: Kalibracja modelu (po 50 settled)
- [ ] `python -m footstats.core.probability_calibrator`
- [ ] A/B test wag: 50/50 → 60/40 → 70/30 Poisson/Bzzoiro
- [ ] Zapisać `data/model_calibration.json`
- **Effort:** 2–3h | Warunek: min. 50 settled live kuponów

### 16.5: Zbieranie danych (pasywne — 3 tygodnie)
- [ ] Daily agent działa automatycznie (Task Scheduler 08:00 + 11:00 + 23:00)
- [ ] Monitorować logi: `logs/kupon_YYYY-MM-DD.txt`
- [ ] Cel: 50 settled kuponów z filtrowanymi ligami
- [x] match_stats (timeline zdarzeń) zapisywane do `predictions` (06-12)

---

## 🔴 KRYTYCZNE (wykryte 06-14)

### TD-39: Kupony #113-115 (06-13) zablokowane w DRAFT — promocja do final/ACTIVE
- [ ] Coupons #113-115 (06-13) status=DRAFT, nigdy promowane do final/ACTIVE (pre-fix root
      cause TD-38 = Bzzoiro `waliduj()` timeout → exit=1, naprawione 06-14, ale historyczne
      kupony #113-115 wciąż wisą w DRAFT)
- [ ] Zdecydować: rozliczyć ręcznie / promować do ACTIVE / oznaczyć VOID
- **Effort:** ~30min | 🔴 P2

---

## 🟡 TECHNICZNE

### TD-31: Testy core modules (24 moduły bez testów)
- [ ] Priorytetowe: coupon_settlement, bankroll, kelly, value_bet, quick_picks
- [ ] Minimum: smoke test importu + 2-3 unit testy per moduł
- **Effort:** 4-6h | 🟡 P3

---

## ⏸️ NA PÓŹNIEJ

### 15.6: Multi-user support
- [ ] Per-user bankroll, risk profile, Telegram chat_id
- **Effort:** 3–5 dni | ⏸️ po M1

## Licencja
- [x] LICENSE zmienione MIT → All Rights Reserved + klauzula portfolio/CV (06-12)
- [ ] Konsultacja z prawnikiem przed komercyjnym udostępnieniem (ToS bukmacherów + ochrona baz danych)

---

## 💡 Pomysły od betatesterów

### Rozszerzenie oferty zakładów (rożne/kartki)
- STS Bet Builder: rożne, kartki, rzut karny, czerwona kartka
- zawodtyper.pl: dane per-kategoria, zawodtyper_referees: avg_yellow/avg_red per sędzia
- Pomysł: `fetch_team_corners`/`fetch_team_cards` + Poisson → nowe tipy
- **Effort:** 2-3 dni | po M1
### Przycisk dla admina
- przycisk dla admina aby mógł kliknąć i wywołać sprawdzanie meczów praz api oraz scraper 
- **Effort:** 1-2 dni | na teraz 
### Zmiana nazwy konta
- zmiana nazwy konta na `username` (zamiast `email`)
- **Effort:** 1-2 dni | na teraz
