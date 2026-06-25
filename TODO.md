# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-25
**Wersja:** v3.4-stable
**Accuracy:** model offline **51.8%** (walk-forward A/B, DC W=0.5) | live: świeże ≥06-19 **47.8%** (23 settled, fixy Cel B) vs stare 31%
**Cel:** M1 = 55% win rate

> **Ukończone → `CHANGELOG.md` + `git log`.** Skrót ostatnich (06-24/25): hardening OWASP (live) +
> CI lint/security/coverage gate + Dependabot fix + dekompozycja superbet/daily_agent/utils-logging +
> TheSportsDB 4. źródło + consensus→settlement + CRON_SECRET rotacja + ALLOWED_ORIGINS cleanup +
> Cloud Scheduler audyt + Daily DB Backup (Neon pg_dump) + walk-forward A/B (DC 51.8% potwierdzone) +
> ImportanceIndex zbadane→ślepa uliczka. Wcześniej: Cel A/B/C, D1-D7, multi-source framework, RODO, multi-user.
> Suite: **~1313 testów pass / 6 skip** (coverage ~56%).

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M1** | 55% win rate | 🔴 W toku | świeże settled (~88) → selekcja 65%+ conf (offline=68%) + gating lig |
| **M2** | 60% win rate | ⏸️ | Po M1 — tuning |
| **M3** | 65% selected | ⏸️ | Po M2 |
| **BETA** | Testerzy | ⏸️ | Po M1 |

---

## 🚀 NAJWAŻNIEJSZE — reweight ensemble ku rynkowi (GOTOWE, czeka na flip po walidacji)

> **Model R&D zakończone 06-25** (4 eksperymenty, 1 win — szczegóły → CHANGELOG):
> ImportanceIndex −0.1pp ❌ · W_BAYESIAN 0.5 już optimum ❌ · LightGBM 51.6% < rynek 53.1% ❌ ·
> **reweight ku rynkowi +1.4pp ✅**. Wniosek: model przy praktycznym suficie, **rynek (kursy) ~53% nieprzekraczalny**.
> Skuteczność ≠ accuracy; realna gra = **value** (model vs rynek) + **selekcja high-conf** + dane.

- [ ] **FLIP po walidacji: `ENSEMBLE_MARKET_WEIGHT=0.70`** (=30/70 model/rynek). Gotowe + otestowane
  (flaga env, **default OFF = zero zmiany prod teraz**). WF A/B: 70/30→51.8% vs 30/70→52.8% (z kursami 52.5→53.8).
  Zostawia 30% głosu modelu na value. Przy flipie: calibration check (log-loss, bo stare 70/30 było log-loss-opt).
- [ ] (opcj.) re-optymalizacja per-league wag ku rynkowi (`ensemble_optimizer`).

---

## 🔴 PRIORYTET — WALIDACJA (pasywne — NIE dokładaj zmian λ)

> Root-cause'y Cel B usunięte. Kalibracja OFF (`CALIBRATION_ENABLED`), auto-refit czeka na dane (D2).
> STOP na nowe λ aż zbierzemy świeże dane (zmiana teraz zaciemnia czy fixy działają).

- [ ] **D3 — PEŁNA decyzja a/b/c** (próg guardu, czy argmax na stałe) — po ~20 ŚWIEŻYCH settled z zapisanym prob.
  Zwaliduj że guard pomaga, dostrój próg. (D3 część 1+2 prob+guard ZROBIONE 06-22 → CHANGELOG.)
- [ ] **DECYZJA (nie bug):** Bzzoiro etykietuje towarzyskie kadr jako "World Cup 2026" → whitelist MŚ (D1a).
  Niska szkoda + downstream łapią. Opcje: (a) zostaw MŚ [domyślnie], (b) wyklucz kadry z kuponów Groq,
  (c) zawęź whitelist do realnych fixture'ów WC.
- [ ] Co kilka dni: `python scripts/calibration_monitor.py` (Neon, read-only) — System vs Pipeline,
  czy accuracy ruszyła, licznik settled (D2 auto-refit przy delcie +30 od n_train).
- [ ] Po ~88 settled → D2 auto-refit sam; gdy krzywa zdrowa → włącz `CALIBRATION_ENABLED=1`.
- **Zbieranie:** draft lokalny (Task Scheduler 08:00) + settle cloud (06:00/21:30 UTC) + lokalny 23:00.
  ⚠️ **Draft TYLKO lokalny** — PC off = 0 nowych predykcji/dzień (bottleneck danych do walidacji).

---

## 🎯 JAKOŚĆ λ — kandydaci PO walidacji (nie wcześniej)

> **Walk-forward A/B (06-25, out-of-sample, n=7934, kalibracja OFF):** poisson_only 48.8 < baseline 50.3
> < **dixoncoles (DC W=0.5) 51.8**. Sweep W_BAYESIAN: **0.5 optimum** (nie ruszać). Opponent-adjusted λ
> (atak×obrona) + DC τ + bayesian ramię **JUŻ w prod** (`USE_DIXON_COLES=1`). **Kalibracja: 65%+ conf = 68%**
> (robustnie). Per-liga: NED 56/SCO 55/ITA 54/ENG 54 ≥M1; POL 44/ESP 49/FRA 49 w dół.
> **WNIOSEK M1:** model OK, droga = **SELEKCJA** (65%+ subset) + gating lig. Zgodne z Cel B (gap=selekcja).

- [ ] **Selekcja na confidence (M1 lever #1)** — podnieś próg budowy kuponu do pasma 65%+ (=68% offline).
  Deploy PO walidacji (~88 fresh), zwaliduj że live trzyma kalibrację.
- [ ] **Gating słabych lig (M1 lever #2)** — POL/ESP/FRA <50% offline; faworyzuj NED/ITA/ENG/SCO/AUT.
- [ ] **Schedule-adjusted ratings** — `_oblicz_sile_wazona` atak=gole/średnia bez korekty siły rywala.
  Iteracyjne ratingi ~+0.5-1pp do raw. Drugorzędne vs selekcja (i częściowo pokryje to model ML / pi-ratings).
- [ ] **Kontuzje v2** — waga udziałem w golach (utrata strzelca > rezerwowy); wymaga scrape per-gracz.

### Zbadane → odrzucone (nie wracać)
- **ImportanceIndex** (crude ±20% multiplier): backtest A/B −0.1pp, high-stakes −0.59pp → ślepa uliczka
  (CHANGELOG 06-25). `core/standings.py` zostaje jako CECHY do modelu ML.
- **LightGBM / własny model ML** (pomysł B): 51.6% (z kursami) / 50.9% (bez) < rynek 53.1% < baseline.
  Rynek nieprzekraczalny (jak literatura). `core/ml_features.py` zostaje jako infra (pi-ratings/elo).
  Jedyny realny owoc = reweight ensemble ku rynkowi (sekcja NAJWAŻNIEJSZE).

---

## 💰 MONETYZACJA / LAUNCH (wymaga Ciebie)

- [ ] **D8 — prawnik (ToS bukmacherów) + JDG (CEIDG)** — WSTRZYMANE (koszt/ryzyko). Wrócić po walidacji.
- [ ] Resend FROM: `onboarding@resend.dev` (test) → zweryfikowana domena przed prod. (Resend wpięty ✅ → CHANGELOG.)
- [ ] Reset hasła — flow tokenów (`send_password_reset_email` jest) + endpoint.
- [ ] Płatności (Lemon Squeezy/Paddle, po JDG): cennik+auto-renewal, webhooks, email potwierdzenie/faktura, upgrade/proration.
- [ ] Faktura (po płatnościach). Custom domain (opcjonalne).

---

## 🌐 SCRAPERY — kolejne źródła (opcjonalne)

- [ ] **Ocena per-stabilność/anti-bot:** Soccer24 (klon FlashScore — redundancja, skip),
  Meczyki/LiveScore (anti-bot, scraping), Transfermarkt (raczej squad/value niż wyniki).
  (4 źródła wpięte: AF/football-data.co.uk/FlashScore/TheSportsDB ✅ → CHANGELOG.)

---

## 📋 Następne kroki

1. **Pomysł B (ML LightGBM)** — sekcja AKTYWNE wyżej (w toku).
2. **Pasywne:** zbieraj świeże settled (draft musi lecieć — pilnuj PC/Scheduler). Budżet AF 100/dzień.
3. **Po walidacji (~88 settled):** D2 auto-refit sam → `CALIBRATION_ENABLED=1`; D3 decyzja; selekcja 65%+ + gating lig.
4. **Sam koniec (D8):** JDG/prawnik (wstrzymane). Email/płatności po walidacji.
