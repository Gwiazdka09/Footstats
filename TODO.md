# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-16
**Wersja:** v3.4-stable
**Accuracy baseline:** 33% live (Neon.tech, 49/50 settled)
**Cel:** M1 = 55% win rate (min. 50 settled + kalibracja)

> Historia ukończonych zadań: `git log`

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

## 🔴 FAZA 16: ACCURACY FIXES

### 16.3: Draw bias
- [ ] A/B: porównaj trafność remisów vs 1/2 (warunek: 50 settled)

### 16.4: Kalibracja modelu ✅ DONE (06-16)
- [x] `python -m footstats.core.probability_calibrator` — 67 próbek
- [x] A/B test wag: 70/30 Poisson/Bzzoiro (log-loss 0.961 vs 1.027 przy 45/55)
- [x] Zapisano `data/model_calibration.json` + `data/calibration.json`
- **Wynik: accuracy 34.3%, sufit kalibracji ~34% — bottleneck to model, nie wagi**

### 16.5: Zbieranie danych (pasywne) — trwa
- [ ] Monitorować logi: `logs/kupon_YYYY-MM-DD.txt`
- [x] Cel 50 settled — przekroczony: **67 settled (WON 22 + LOST 45)** — 06-16

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
