# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-16
**Wersja:** v3.4-stable
**Accuracy baseline:** 31.7% live (Neon, 41 unikalnych / 67 z duplikatami)
**Cel:** M1 = 55% win rate

> Historia ukończonych zadań: `git log`

---

## 🚨 FAZA 17: ROOT CAUSE ACCURACY (analiza 06-16)

> **Diagnoza dlaczego 31.7%.** Dane: 41 unikalnych settled, kalibracja **ODWRÓCONA**
> (90%+ pewność → 11% trafność, 60-69% → 38%). Bottleneck NIE w wagach ensemble —
> w sposobie liczenia pewności i selekcji meczów. 5 bugów, kolejność wg wpływu.

### 17.1: 🔴 P0 — Pewność liczona z EV, nie z prawdopodobieństwa (KILLER)
- **Plik:** `ai/analyzer_helpers.py:152`
  ```python
  conf = min(95, max(50, int(60 + float(ev) * 2))) if ev is not None else 65
  ```
- **Problem:** `ai_confidence` = `60 + ev_netto*2`. EV rośnie z kursem → wysoki kurs
  (longshot) = wysoki EV = pewność wbita w sufit 95%. Matematycznie GWARANTUJE
  antykorelację pewność↔trafność. Stąd 95% pewności = 11% trafności.
- **Dowód:** wszystkie 9 typów z conf≥90 to "2"/"X" na kursach 18–52. Germany vs
  Curaçao tip=2 (Curaçao wygrywa!) kurs 52.58 conf=95.
- **Fix:** pewność = skalibrowane `p_modelu` (Poisson/ensemble), NIE EV. EV używać
  tylko do value_bet/Kelly, nie jako proxy pewności.
- **Effort:** 0.5d | odblokowuje całą resztę

### 17.2: 🔴 P0 — Model goni longshoty (EV chasing)
- **Problem:** skoro pewność = f(EV), pipeline preferuje typy o najwyższym EV =
  najwyższym kursie = najmniejszej szansie. tip "2" (away): avg kurs 18.80, **21.7%** trafność.
- **Powiązane z 17.1** — po fixie pewności EV-chasing zniknie, ale dodać twardy filtr:
  odrzuć typy z kursem > 4.0 lub p_modelu < 40%.
- **Effort:** 0.5d

### 17.3: 🔴 P1 — top3 NIE jest weryfikowany przez Bzzoiro
- **Plik:** `daily_agent.py:422` `_weryfikuj_kupony` obejmuje tylko `kupon_a..d`.
  `save_predictions` (`analyzer_helpers.py:175`) zapisuje TEŻ `top3`.
- **Problem:** halucynowane kursy Groq w top3 trafiają do `predictions` bez
  weryfikacji. To źródło kursów 52.58 z conf=95.
- **Fix:** uruchom weryfikację też dla top3 albo nie zapisuj niezweryfikowanych nóg.
- **Effort:** 0.5d

### 17.4: 🟡 P1 — Whitelist lig to no-op (garbage leagues)
- **Plik:** `core/daily_filters.py:65-68`
  ```python
  if liga in LIGI_WHITELIST:
      wynik.append(k); continue
  wynik.append(k)   # dopisuje WSZYSTKO i tak
  ```
- **Problem:** `LIGI_WHITELIST` nic nie filtruje — każda liga przechodzi. Tylko
  blacklist "friendl" działa (i to dziurawo — 20 friendlies w DB, 40% trafność).
  Dominują Botola Pro, Veikkausliiga, Saudi — niska jakość danych Poissona.
- **Fix:** albo egzekwuj whitelist (return tylko whitelisted), albo świadomie usuń
  i polegaj na rozszerzonej blackliście. Decyzja: ograniczyć do lig z λ-danymi.
- **Effort:** 0.5d (+ decyzja biznesowa które ligi)

### 17.5: 🟡 P2 — Duplikaty predykcji (ten sam mecz × kupon_type)
- **Problem:** `save_predictions` zapisuje osobny wiersz dla top3 + kupon_a + kupon_c
  → ten sam mecz+tip 2-5x w `predictions`. "67 settled" to faktycznie **41 unikalnych**.
  Psuje wszystkie statystyki accuracy + kalibrację (uczy się na duplikatach).
- **Fix:** UNIQUE constraint (team_home, team_away, match_date, ai_tip) lub dedup
  przy zapisie. Backfill: usunąć istniejące duplikaty.
- **Effort:** 0.5d

### 17.6: 🟢 P3 — Niestabilna pewność dla tego samego meczu
- **Problem:** Germany vs Curaçao: conf=95 (top3) vs 65 (kupon_a/c) — różne EV w
  różnych ścieżkach zapisu dla identycznego meczu/tipu. Konsekwencja 17.1.
- **Fix:** wynika z 17.1 (jedno źródło pewności).

### 17.7: A/B po fixach
- [ ] Po 17.1–17.5: nowy A/B accuracy na świeżych kuponach (cel: kalibracja monotoniczna)
- [ ] Re-fit `calibration.json` na zdeduplikowanych danych

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

### 16.3: Draw bias ✅ DONE (06-16)
- [x] A/B: X=38.7% (31 typy) vs 2=21.7% (23 typy) vs 1=25% (4 typy)
- **Wynik: remisy trafiane powyżej średniej — draw bias fix działa. Away win (typ 2) najsłabszy.**

### 16.4: Kalibracja modelu ✅ DONE (06-16)
- [x] `python -m footstats.core.probability_calibrator` — 67 próbek
- [x] A/B test wag: 70/30 Poisson/Bzzoiro (log-loss 0.961 vs 1.027 przy 45/55)
- [x] Zapisano `data/model_calibration.json` + `data/calibration.json`
- **Wynik: accuracy 34.3%, sufit kalibracji ~34% — bottleneck to model, nie wagi**

### 16.5: Zbieranie danych ✅ DONE (06-16)
- [x] Cel 50 settled — przekroczony: **67 settled (WON 22 + LOST 45)**
- [x] Task Scheduler działa autonomicznie (08:00 + 11:00 + 23:00)
- Logi bieżące: `logs/kupon_YYYY-MM-DD.txt`

---

## 🟡 TECHNICZNE

### Testy (TD-31 częściowo done)
- [ ] Brak testów: bet_builder, classifier, confidence, daily_filters, daily_io, form, fortress, h2h, importance, lambda_optimizer, weekly_picks
- **Effort:** 3–5 dni | ⏸️ po M1

### 15.6: Multi-user support
- [ ] Per-user bankroll, risk profile, Telegram chat_id
- **Effort:** 3–5 dni | ⏸️ po M1

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
- [ ] ALLOWED_ORIGINS Cloud Run: sprawdź czy `bot-opal-nu.vercel.app` jest dodane ✓ (zrobione 06-16)
- [ ] Custom domain (opcjonalne)

### SEO
- [ ] Meta tags w index.html
- [ ] sitemap.xml, robots.txt

### Inne
- [ ] Rozszerzenie zakładów: rożne, kartki (po M1)

---

## 📋 Następne kroki (priorytet)

1. **Jutro:** Sprawdź logi — czy 50. kupon settled (brakuje 1)
2. **Po 50 settled:** Uruchom 16.4 kalibrację
3. **Równolegle:** Email transakcyjny (Resend — wymaga klucza od użytkownika)
4. **Przed betą:** JDG rejestracja
