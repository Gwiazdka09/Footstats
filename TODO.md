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

## 🟡 TECHNICZNE

### TD-31: Testy core modules — ✅ DONE (06-14)
- [x] Priorytetowe: coupon_settlement, bankroll, kelly, value_bet, quick_picks
- [x] bankroll: nowy `tests/test_bankroll.py` (8 testów, sqlite fixture)
- [x] coupon_settlement/kelly/value_bet/quick_picks: już pokryte (60 testów)

---

## ⏸️ NA PÓŹNIEJ

### 15.6: Multi-user support
- [ ] Per-user bankroll, risk profile, Telegram chat_id
- **Effort:** 3–5 dni | ⏸️ po M1

## Licencja
- [x] LICENSE zmienione MIT → All Rights Reserved + klauzula portfolio/CV (06-12)
- [ ] Konsultacja z prawnikiem przed komercyjnym udostępnieniem (ToS bukmacherów + ochrona baz danych)

---

## 💰 MONETYZACJA / LAUNCH (przed publicznym beta)

### Logowanie / rejestracja
- [x] `POST /api/auth/register` — nowe konto (login+email+hasło min.8), auto-login + init bankrolla (06-15)
- [x] Login akceptuje login LUB e-mail
- [x] GUI: LoginView z przełączaniem Logowanie/Rejestracja

### Prawne dokumenty
- [ ] `/regulamin` (ToS) — warunki subskrypcji, zwroty, anulacja
- [x] `/polityka-prywatnosci` (RODO) — strona stworzona (06-15), wymaga uzupełnienia [nazwa firmy/NIP/e-mail]
- [x] Dashboard: "Twoje imperium bukmacherskie" → "Twój asystent analityczny do kuponów" (06-15)
- [ ] Disclaimer w footerze GUI: "FootStats nie jest bukmacherem, nie przyjmuje zakładów, prognozy nie gwarantują wyników, hazard 18+"
- [ ] Rejestracja JDG (jeśli jeszcze nie) — wymóg Stripe/MoR

### Płatności / subskrypcje
- [x] Decyzja: Lemon Squeezy/Paddle (MoR) — wyższe fee, ale VAT/KSeF za nas (06-15)
- [ ] Cennik widoczny przed checkout + jasne warunki auto-renewal
- [ ] Webhooks: subscription.updated/cancelled/payment_failed
- [ ] Email: potwierdzenie, faktura, retry nieudanej płatności, ostrzeżenie przed odnowieniem
- [ ] Upgrade/downgrade planu + proration

### KSeF (od 1 kwietnia 2026 — wszyscy przedsiębiorcy)
- [ ] Faktury Stripe NIE spełniają wymogów KSeF → integrator (Stripto) lub MoR
- **Effort:** konsultacja z księgowym | po wyborze modelu płatności

---

## 💡 Pomysły od betatesterów

### Rozszerzenie oferty zakładów (rożne/kartki)
- STS Bet Builder: rożne, kartki, rzut karny, czerwona kartka
- zawodtyper.pl: dane per-kategoria, zawodtyper_referees: avg_yellow/avg_red per sędzia
- Pomysł: `fetch_team_corners`/`fetch_team_cards` + Poisson → nowe tipy
- **Effort:** 2-3 dni | po M1
### Przycisk dla admina — ✅ DONE (06-14)
- [x] nowa zakładka "Panel" (tylko dla adm): "Sprawdź wyniki meczów" (POST /coupons/settle) + "Zarządzaj użytkownikami" (GET/POST/DELETE /admin/users)
### Zmiana nazwy konta — nieaktualne
- [x] system już używa `username` (nie email) do logowania/wyświetlania — brak akcji
### Błąd w przeglondarce na telefonie — ✅ DONE (06-14)
- [x] mobile topbar (logo + ☰) + fullscreen drawer nav (X zamyka), sidebar desktop ukryty <1024px
### P1! — ✅ DONE (06-15, false positives, zweryfikowane)
- [x] "API key" w .vexp/manifest.json → to SHA256 hashe plików (vexp index), nie sekrety
- [x] "Command injection" w 8 subprocess.run/Popen → wszystkie list-form args, brak shell=True, cap.cmd z hardcoded CAPABILITIES
- [x] "SQL injection" rag.py:215-218 → f-string buduje tylko placeholdery `?,?,?`, wartości idą parametryzowane
