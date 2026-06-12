# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-12
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
- [x] Zbadaj dlaczego predictions 06-05/06-06/06-12 to masowo "X" @1.92 (fair_odds(p_remis≈52%))
- [x] Root cause: dla niskich lambd (slabe/egzotyczne druzyny) czysty Poisson daje
      p_remis ~45-50%, a FINAL_REMIS_BOOST (×1.25, config.py) po renormalizacji
      przepycha to >50% — "X" staje sie najwyzszym prob i dominuje liste typow
- [x] Fix: sufit p_remis=40% w poisson.py (core/poisson.py) — nadwyzka
      przenoszona proporcjonalnie na 1/2. 65/65 testow poisson OK
- [ ] A/B: porównaj trafność remisów vs 1/2 w ostatnich 35 settled (warunek: 50 settled)
- **Effort:** done (cap) | A/B po 16.4 | 🔴 P1

### 16.4: Kalibracja modelu (po 50 settled)
- [ ] `python -m footstats.core.probability_calibrator`
- [ ] A/B test wag: 50/50 → 60/40 → 70/30 Poisson/Bzzoiro
- [ ] Zapisać `data/model_calibration.json`
- **Effort:** 2–3h | Warunek: min. 50 settled live kuponów

### 16.5: Zbieranie danych (pasywne — 3 tygodnie)
- [ ] Daily agent działa automatycznie (Task Scheduler 08:00 + 11:00 + 23:00)
- [ ] Monitorować logi: `logs/kupon_YYYY-MM-DD.txt`
- [ ] Cel: 50 settled kuponów z filtrowanymi ligami
- [x] match_stats (statystyki + timeline zdarzeń gole/kartki z API-Football) zapisywane do `predictions` — dane do analizy gotowe (06-12)

---

## ⏸️ NA PÓŹNIEJ

### 15.6: Multi-user support
- [ ] Per-user bankroll, risk profile, Telegram chat_id
- **Effort:** 3–5 dni | ⏸️ po M1

## Licencja
- [x] LICENSE zmienione MIT → All Rights Reserved + klauzula portfolio/CV (06-12)
- [ ] Polskie prawo: scraping kursow (STS/Bzzoiro/Superbet) do analizy wlasnej —
      to gray-area ToS (ryzyko bana konta, nie przestepstwo). Bot NIE organizuje
      zakladow (Ustawa o grach hazardowych dot. organizatorow), tylko analizuje —
      niskie ryzyko. Przed jakimkolwiek publicznym/komercyjnym udostepnieniem:
      konsultacja z prawnikiem (ToS bukmacherow + ochrona baz danych).
---

## 💡 Pomysły od betatesterów

### Rozszerzenie oferty zakładów (rożne/kartki) — wzorem STS Bet Builder
- STS Bet Builder ma rynki: Rzuty rożne (handicap/total/per-druzyna), Kartki
  (total/per-druzyna/dokladna liczba), Rzut karny, Czerwona kartka, Spalone, Faule
- `sts_inspiracje.normalize_market_tip` aktualnie zwraca None dla "rożne, kartki,
  polowy, zawodnicy" — niezamodelowane, ale dane dostepne:
  - zawodtyper.pl: 14 stron per-kategoria (rożne, kartki, ...) — śr./mecz per druzyna
  - zawodtyper_referees.py (po fixie 06-12): avg_yellow/avg_red per sędzia poprawne
- Pomysł: `fetch_team_corners`/`fetch_team_cards` (zawodtyper) + prosty model
  Poissona dla rożnych/kartek (śr. team + śr. sędzia) → nowe tipy "Over X.5 rożnych",
  "Over X.5 kartek" jako kolejny market w build_tips
- **Effort:** 2-3 dni | po M1 (nowy market = nowa kalibracja)
