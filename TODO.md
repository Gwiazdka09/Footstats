# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-16
**Wersja:** v3.4-stable
**Accuracy:** 31.7% live (41 settled) — pipeline naprawiony (Faza 17), czeka na świeże dane
**Cel:** M1 = 55% win rate

> Ukończone: `git log`. Fazy DONE: 16 (accuracy fixes), 17 (root-cause), 18 (BetBuilder),
> 19 (System paper-trading), 20 (katalog rynków), GUI/UX polish, SEO, RODO.

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M1** | 55% win rate | 🔴 W toku | świeże settled z naprawionego pipeline + A/B |
| **M2** | 60% win rate | ⏸️ | Po M1 — tuning |
| **M3** | 65% selected | ⏸️ | Po M2 |
| **BETA** | Testerzy | ⏸️ | Po M1 |

---

## 🔴 PRIORYTET — walidacja modelu (17.7)

- [x] Narzędzie monitoringu: `python scripts/calibration_monitor.py` (Neon, read-only) —
  monotoniczność kalibracji + per-tip + ROI System paper-trading
- [ ] Uruchamiać monitor co kilka dni — czy kalibracja przestaje być odwrócona na świeżych danych
- [ ] A/B accuracy po ~20 nowych settled z naprawionego pipeline
- **Zbieranie:** System paper-trading działa autonomicznie (Task Scheduler 08:00). ~1-2 tyg.
- **Obecnie:** stare 41 settled wciąż odwrócone (sprzed Fazy 17) — to oczekiwane

---

## 💰 MONETYZACJA / LAUNCH (wymaga Ciebie)

### Prawne
- [ ] Konsultacja z prawnikiem (ToS bukmacherów) przed komercją
- [ ] Rejestracja JDG (CEIDG, 1 dzień) — przed pierwszym płatnym userem

### Email transakcyjny
- [ ] Resend.com — załóż konto, podaj `RESEND_API_KEY` + FROM adres
- [ ] Potwierdzenie rejestracji, reset hasła, faktura

### Płatności (Lemon Squeezy / Paddle — zdecydowane, po JDG)
- [ ] Cennik przed checkout + warunki auto-renewal
- [ ] Webhooks: subscription.updated/cancelled/payment_failed
- [ ] Email: potwierdzenie, faktura, retry, ostrzeżenie przed odnowieniem
- [ ] Upgrade/downgrade + proration

### Hosting
- [ ] Custom domain (opcjonalne)

---

## 🟡 TECHNICZNE (po M1)

### Testy modułów core (TD-31) — pozostałe
- [ ] daily_io (DB), form (scraper Rich), weekly_picks (651 linii) — wymagają mocków DB/Playwright

### 15.6: Multi-user support
- [ ] Per-user bankroll, risk profile, Telegram chat_id — **Effort:** 3–5 dni

---

## 💡 OPCJONALNE rozszerzenia

- [ ] Rynki: dokładny wynik / multigoal (rozliczalne, dużo opcji)
- [ ] Kartki/rożne — wymaga feedu zdarzeń (API-Football statistics) + settlement
- [ ] BetBuilder: Bzzoiro odds dla compound + settlement combo "1 & Over 1.5"
  (teraz kurs = fair 1/szansa; złożone typy nie przechodzą weryfikacji Bzzoiro)

---

## 📋 Następne kroki (priorytet)

1. **Pasywne:** System paper-trading zbiera dane codziennie → po ~20 settled A/B (17.7)
2. **Wymaga Ciebie:** Email (Resend key)
3. **Przed płatnym userem:** JDG + prawnik
4. **Płatności:** Lemon Squeezy/Paddle po JDG
