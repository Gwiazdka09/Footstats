# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-16
**Wersja:** v3.4-stable
**Accuracy baseline:** 31.7% live (Neon, 41 unikalnych / 67 z duplikatami)
**Cel:** M1 = 55% win rate

> Historia ukończonych zadań: `git log`

---

## ✅ FAZA 17: ROOT CAUSE ACCURACY — FIXY DONE (06-16)

> **Diagnoza dlaczego 31.7%.** Kalibracja była **ODWRÓCONA** (90%+ pewność → 11%
> trafność). Bottleneck w liczeniu pewności i selekcji meczów, NIE w wagach ensemble.
> 6 bugów naprawionych. Pozostał A/B na świeżych danych (17.7).

### 17.1: ✅ Pewność liczona z EV → z prawdopodobieństwa (cd1843490)
- Było: `conf = 60 + ev_netto*2` → longshot = wysoki EV = sufit 95% = antykorelacja.
- Fix: `pewnosc_z_modelu()` — pewność = p_modelu Poissona dla typu. Curaçao 95%→5%.

### 17.2: ✅ Twardy filtr longshotów (4d4e1bbf7)
- `_powod_odrzucenia_longshot`: odrzuca nogę gdy kurs > 4.0 LUB p_modelu < 40%.
- tip "2" away (avg kurs 18.80, 21.7% trafność) — teraz odsiewany.

### 17.3: ✅ top3 weryfikowany przez Bzzoiro (bc6d85ec7)
- `_weryfikuj_noge` reużywalny; `_weryfikuj_kupony` obejmuje top3 + kupon_a..d.
- Halucynowane kursy Groq (52.58) nie wchodzą już do predictions.

### 17.4: ✅ Whitelist lig egzekwowana (4baba70a5)
- Było no-op (każda liga przechodziła). Teraz tylko LIGI_WHITELIST, z normalizacją
  nazw (akcenty/prefiks kraju). Env `LIGA_WHITELIST_ENFORCE=0` wyłącza.

### 17.5: ✅ Dedup predykcji (7448dd9ad + backfill)
- Guard w `save_prediction` (mecz+tip idempotentny). Backfill: usunięto 47 duplikatów
  z prod Neon (148→101 wierszy, 67→41 settled), re-point 28 ai_feedback. 0 duplikatów.

### 17.6: ✅ Stabilna pewność (single source of truth)
- `pewnosc_z_modelu()` deterministyczna per (typ, pred) — koniec conf=95 vs 65 dla
  tego samego meczu. Test regresyjny `tests/test_pewnosc_z_modelu.py` (7 testów).

### 17.7: ⏳ A/B + re-fit po fixach (DO ZROBIENIA)
- [x] Re-fit `calibration.json` na zdeduplikowanych 41 settled (krzywa monotoniczna 28.6→35%)
- [ ] Monitorować świeże kupony: czy kalibracja monotoniczna (wyższa pewność → wyższa trafność)
- [ ] A/B accuracy po zebraniu ~20 nowych settled z poprawionym pipeline
- **Zbieranie przyspieszone:** FAZA 19 (System paper-trading) tworzy single-leg kupony
  codziennie → szybszy zbiór czystych per-tip wyników. Warunek: ~1-2 tygodnie.

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M0** | 42% baseline | ✅ Done | 33 kupony SQLite |
| **M0b** | 26.7% live baseline | ✅ Done | 15 kuponów Neon |
| **M1** | 55% win rate | 🔴 W toku | min. 50 settled + kalibracja |
| **M2** | 60% win rate | ⏸️ | Po M1 |
| **M3** | 65% selected | ⏸️ | Po M2 |
| **BETA** | Testerzy | ⏸️ | Po M1 |

---

## ✅ FAZA 16: ACCURACY FIXES — DONE (06-16)
- 16.3 draw bias (X=38.7% vs away=21.7%), 16.4 kalibracja + wagi 70/30,
  16.5 zbieranie (Task Scheduler autonomiczny). Szczegóły: `git log`.

---

## 🟡 TECHNICZNE

### Testy modułów core (TD-31)
- [x] classifier, confidence, h2h, fortress — `tests/test_core_pure_modules.py` (16 testów, 06-16)
- [x] bet_builder, lambda_optimizer.injury_correction, importance — `tests/test_core_pure_modules2.py` (27 testów, 06-16)
- [x] daily_filters — `tests/test_daily_agent_prefilter.py` (whitelist, 06-16)
- [ ] Pozostałe: daily_io (DB), form (scraper Rich), weekly_picks (651 linii, integracja)
  — wymagają mockowania DB/Playwright, większy nakład
- **Effort:** 1–2 dni | ⏸️ po M1

### 15.6: Multi-user support
- [ ] Per-user bankroll, risk profile, Telegram chat_id
- **Effort:** 3–5 dni | ⏸️ po M1

### Obserwacja: bet_builder compound tips nie przechodzą weryfikacji
- bet_builder DZIAŁA (Poisson macierz, podpięty `daily_agent.py:1358`, karmi prompt Groq).
- ALE złożone typy (`1 & Over 1.5`, `Handicap -1`) nie mają klucza w `_TYP_DO_ODDS_KEY`
  → `_weryfikuj_noge` je usuwa (brak kursu Bzzoiro). Efektywnie tylko kontekst dla AI.
- Opcje: (a) dodać klucze odds dla compound + źródło kursów, albo (b) świadomie
  zostawić jako hint Groq. Decyzja przy implementacji kreatora BetBuilder (niżej).

---

## 🤖 FAZA 19: SYSTEM PAPER-TRADING (single-leg) — DONE (06-16)

> Bot tworzy 1 single-leg kupon/mecz na koncie System → czysty per-tip win rate/ROI
> (multi-leg AKO topił sygnał). Cel: szybka walidacja modelu po Fazie 17 na realnych danych.

### 19.1: ✅ Moduł + wiring
- [x] `core/system_paper.py` — `najlepszy_typ` (max p_modelu po filtrach Fazy 17),
  `build_single_leg_coupons` (whitelist lig + longshot + idempotencja per mecz/data)
- [x] Flaga `--system-paper` w daily_agent (krok 2b), flat stake 2 PLN, konto System (id=408)
- [x] Kupony NIE shared → poza leaderboardem; auto-settle przez coupon_settlement
- [x] 7 testów `tests/test_system_paper.py`
- [x] **Aktywacja:** wpięte w `daily_agent_scheduler` (faza draft) + `run_daily.bat`
  (flaga `--system-paper` forwarduje przez scheduler) — autonomiczne od następnego runu Task Scheduler

---

## 🎰 FAZA 18: KREATOR BETBUILDER (manualny, z zabezpieczeniami)

> Cel: w kreatorze kuponów dodać tryb BetBuilder — user buduje combo z 1 meczu,
> z regułami korelacji blokującymi sprzeczne/trywialne kombinacje.

### 18.1: ✅ Silnik reguł korelacji (b788bd4ee)
- [x] SPRZECZNE (1 vs X vs 2), TRYWIALNE (1 ⇒ Over 0.5), DOZWOLONE (1 + Over 1.5)
- [x] Podejście zbiorów wyników (h,a) na siatce 0..7 — bez ręcznych tabel
- [x] `core/betbuilder_rules.py` + 20 testów `tests/test_betbuilder_rules.py`

### 18.2: ✅ GUI BetBuilder w CouponWizard (347dcec60 + 335d3ac42)
- [x] Endpoint `POST /api/betbuilder/markets` (single source of truth reguł)
- [x] `BetBuilderPanel` w kroku 3 per mecz: chipy rynków z szansą Poissona
- [x] Sprzeczne/trywialne wyszarzone + przekreślone z tooltipem powodu (live)
- [x] Combo szansa skorelowana + kurs; addCombo dodaje 1 nogę "BB: 1 + Over 1.5"
- [x] Zweryfikowane Playwright: "1" blokuje X/2 (sprzeczne) + Over 0.5 (trywialne) ✓

### 18.3: ⏳ Do rozważenia (opcjonalne)
- [ ] Bzzoiro odds dla compound (teraz kurs = fair 1/szansa, nie rynkowy)
- [ ] Zapis BB combo do settlement (jak rozliczać "1 & Over 1.5")

---

## 💰 MONETYZACJA / LAUNCH

### Prawne
- [ ] Konsultacja z prawnikiem przed komercyjnym udostępnieniem (ToS bukmacherów)
- [ ] Rejestracja JDG (CEIDG, 1 dzień, darmowe) — przed pierwszym płatnym userem

### Płatności (Lemon Squeezy / Paddle — zdecydowane)
- [ ] Cennik widoczny przed checkout + warunki auto-renewal
- [ ] Webhooks: subscription.updated/cancelled/payment_failed
- [ ] Email: potwierdzenie, faktura, retry, ostrzeżenie przed odnowieniem
- [ ] Upgrade/downgrade + proration

### Email transakcyjny
- [ ] Resend.com — potrzebny `RESEND_API_KEY` + FROM adres (użytkownik musi założyć konto)
- [ ] Potwierdzenie rejestracji, reset hasła, faktura

### Hosting
- [x] ALLOWED_ORIGINS Cloud Run: `bot-opal-nu.vercel.app` dodane (06-16)
- [ ] Custom domain (opcjonalne)

### SEO
- [x] Meta tags w index.html (06-16)
- [x] sitemap.xml, robots.txt (06-16)

### Inne
- [ ] Rozszerzenie zakładów: rożne, kartki (po M1)

---

## 🎨 GUI / UX — DONE (06-16)
- [x] Fix layoutu (footer był dzieckiem flex-row → ściskał content)
- [x] Usuwanie konta (RODO) w Ustawieniach — DELETE /api/auth/me (ukryte dla admina)
- [x] Polska odmiana "typ" (1 typ / 2 typy / 5 typów)
- [x] Liczby metryk w foncie brandowym Outfit (`.metric-num`)
- [x] Hover lift tylko dla klikalnych kart (statyczne bez "skoku")
- [x] BetBuilder w kreatorze (FAZA 18)

---

## 📋 Następne kroki (priorytet)

1. **Pasywne (17.7):** System paper-trading działa autonomicznie (Task Scheduler 08:00) —
   zbiera single-leg kupony codziennie. Po ~20 settled → A/B czy kalibracja monotoniczna.
2. **Wymaga Ciebie:** Email transakcyjny — załóż konto Resend.com, podaj `RESEND_API_KEY` + FROM.
3. **Przed pierwszym płatnym userem:** JDG (CEIDG, 1 dzień) + konsultacja prawnik.
4. **Płatności:** Lemon Squeezy/Paddle — integracja po JDG.
