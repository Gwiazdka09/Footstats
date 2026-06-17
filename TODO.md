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

> Wzorzec jak bug z kontuzjami: feature istnieje, ale autonomiczny pipeline
> (daily_agent → szybkie_pewniaczki_2dni → quick_picks) go pomija. Pełny model
> jest tylko w `pewniaczki_tygodnia` (CLI), NIE w bocie. Ranking wg wpływu na accuracy.

### 🔴 A1: Daily λ to MODEL OKROJONY (wpływ: wysoki)
- quick_picks:179 woła `predict_match` tylko z `fortress_g, h2h_g, h2h_a`.
- **NIE wpięte:** ImportanceIndex (motywacja: spadek/tytuł), Heurystyka (zmęczenie/rotacja),
  KlasyfikatorMeczu (puchar/rewanż boost). Wszystkie istnieją, używane tylko w weekly/CLI.
- Bot codzienny + System paper-trading liczą słabsze λ niż możliwe.
- **Fix:** policzyć importance/heurystyka/klasyfikację w quick_picks i przekazać do predict_match.
  Koszt: importance wymaga tabeli ligi, heurystyka historii — per mecz, wolniej (dlatego okrojono).

### 🔴 A2: Wagi ensemble 70/30 NIE w realnych prob (wpływ: średni)
- quick_picks:184 blenduje Poisson+Bzzoiro **na sztywno 50/50**.
- `ensemble_probs` (wagi 70/30 z Fazy 16.4) używane TYLKO do `roznica_modeli` (diagnostyka
  → decision_score), nie do faktycznych pw/pp/o25.
- Faza 16.4 A/B efektywnie martwa w produkcyjnych predykcjach.
- **Fix:** quick_picks ma użyć `ensemble_probs(... liga=liga)` zamiast hardcode 0.5/0.5.

### 🟡 A3: Kalibracja łamie normalizację 1X2 (wpływ: średni)
- quick_picks:161-163 kalibruje pw/pr/pp **niezależnie** przez isotonic → suma ≠ 100%.
- Możliwa też podwójna kalibracja (quick_picks + daily_filters.calibrate_candidates).
- **Fix:** kalibrować raz + renormalizować 1X2 do sumy 100%.

### ✅ Poprawnie wpięte (zweryfikowane)
- Kontuzje (po fixie 06-17), xG+obrona (06-17), h2h/fortress w daily λ,
  referee/lineup → decision_score, calibrate_confidence w quick_picks.

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
