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

## 🎯 JAKOŚĆ λ (lambda) — sufit accuracy

- [x] Kontuzje: naprawione (były martwym kodem + bug) — przeliczają λ i prawdopodobieństwa
  dwustronnie (napastnik out→własne λ↓, obrońca out→λ rywala↑), cap ±20% (06-17)
- [x] **xG pogłębione** (06-17): blend uwzględnia obronę rywala — λ_dom=(xGF_dom+xGA_gość)/2;
  prefetch Understat już zasila cache przed Poissonem. Było: tylko własny xGF.
- [ ] Kontuzje v2: waga udziałem w golach (utrata kluczowego strzelca > rezerwowy) —
  wymaga scrape per-gracz (SofaScore goals) — większy nakład
- [ ] Opponent-adjusted λ (Dixon-Coles attack/defense ratings) — λ skorygowane o siłę rywala

---

## 🔍 AUDYT CORE (06-17) — sygnały liczone ale NIEwpięte w daily

> Wzorzec jak bug z kontuzjami: feature istnieje, ale autonomiczny pipeline go pomijał.
> A1-A3 NAPRAWIONE 06-17.

### ✅ A1: Daily λ — heurystyka + klasyfikacja wpięte (b55b5ef8f)
- quick_picks buduje HeurystaZmeczeniaRotacji + KlasyfikatorMeczu z df_mecze,
  przekazuje do predict_match. Zmęczenie/rotacja wpływa teraz na daily λ.
- [ ] **ImportanceIndex wciąż blocked** — wymaga tabeli ligi (standings), brak źródła
  w ścieżce Bzzoiro. TODO: dociągnąć standings (np. football-data.org) i wpiąć motywację.

### ✅ A2: Wagi ensemble 70/30 realnie używane (41b203394)
- quick_picks używa `ensemble_probs(liga=liga)` zamiast hardcode 50/50.
- ensemble_weights.json zregenerowany (_default 70/30). Wagi strojone po danych z paper-tradingu.

### ✅ A3: Renormalizacja 1X2 po kalibracji (fee8d91e0)
- pw/pr/pp renormalizowane do sumy 100% po isotonic. Podwójnej kalibracji brak
  (calibrate_candidates dodaje osobne pole, nie nadpisuje).

### ✅ Poprawnie wpięte (zweryfikowane)
- Kontuzje (fix 06-17), xG+obrona (06-17), heurystyka/klasyfikacja (A1),
  ensemble 70/30 (A2), h2h/fortress, referee/lineup → decision_score, kalibracja+renorm (A3).

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
- [x] form + weekly_picks._typy_pewne — `tests/test_form_weekly.py` (11 testów, 06-17)
- [ ] daily_io — czysta integracja DB (glue nad coupon_tracker/bankroll już testowanymi);
  niska wartość vs nakład (fixture sqlite). Opcjonalne.

### 15.6: Multi-user support — ✅ DONE (06-17)
- [x] Per-user bankroll (bankroll_state.user_id, funkcje biorą user_id) — było wcześniej
- [x] Per-user risk profile (bot_settings per user_id) — było wcześniej
- [x] Per-user Telegram chat_id: migracja 6, `send_message_to_user`, endpoint
  `POST /auth/telegram`, pole w Ustawieniach. Globalny flow nietknięty (additive).
- [ ] 15.7: weryfikacja własności czatu (nonce /start przez webhook bota) — przed realnymi userami (security MEDIUM)

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
