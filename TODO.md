# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-18
**Wersja:** v3.4-stable
**Accuracy:** 31.7% live (41 settled) — pipeline + λ naprawione, **czeka na świeże dane**
**Cel:** M1 = 55% win rate

> Ukończone: `git log`. Fazy DONE: 16-20, GUI/UX, SEO, RODO, multi-user (15.6),
> audyt core (A1-A3), λ: kontuzje + xG+obrona. Suite: 1037 testów pass.

---

## 🔍 AUDYT GŁĘBOKI (06-18) — bugi side-effect / cruft

> Wzorzec: kod tworzony wcześnie z efektami ubocznymi na PRODUKCJI lub martwy.

### ✅ Bug 1: Testy Telegram wysyłały realnie (5e77b517c)
- "Arsenal-Chelsea 3:2" na prawdziwy Telegram przy każdym pytest z kluczami. Zmockowane.

### ✅ Bug 2: Testy auth tworzyły userów w PROD Neon (598063e02)
- `test_delete_account_flow` + `test_create_and_deactivate_user` → 30 z 41 userów w prod
  to test garbage (22 testuser_ + 8 deleted_user_). Gate DATABASE_URL→FOOTSTATS_TEST_DB.
- [x] **Wyczyszczono 30 test-userów z prod** (06-18): backup + FK-aware DELETE
  (30 bankroll_state + users). Prod: 41→11 userów, 0 śmieci. Zostali realni + System.

### 🔴 Bug 3: Mock matches leak do realnych userów
- `coupons.py:_fetch_predictions` zwraca `_mock_predictions()` (Legia/Lech/Ajax — FAKE)
  gdy brak BZZOIRO_KEY / Bzzoiro down / off-season. Realny user w GUI widzi nieistniejące
  mecze jako realne, może budować kupony. **Fix: gate DEMO_MODE, inaczej pusta lista.**

### 🟡 Dead code (cruft — featury działają przez inne ścieżki, NIE broken)
- ~25 nieużywanych funkcji (duplikaty/alternatywy). Zweryfikowane że działające odpowiedniki:
  RAG przez `post_match_analyzer`, lineup przez `lineup_ok`, CLV przez `record_closing_odds`.
- Kandydaci do usunięcia: `_generate_lesson`, `lineup_confidence_penalty`,
  `batch_record_closing_odds`, `fetch_match_xg`, `export/json_export.*` (4), `send_trening_raport`,
  `dozwolone_dodatki` (tylko test), cache cleanup funkcje. **Niski priorytet — czyszczenie.**

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M1** | 55% win rate | 🔴 W toku | świeże settled + walidacja A/B |
| **M2** | 60% win rate | ⏸️ | Po M1 — tuning |
| **M3** | 65% selected | ⏸️ | Po M2 |
| **BETA** | Testerzy | ⏸️ | Po M1 |

---

## 🔴 PRIORYTET — WALIDACJA (czekaj i mierz, NIE dokładaj zmian λ)

> **Decyzja 06-18:** wpięto 6 zmian λ (kontuzje, xG+obrona, heurystyka, klasyfikacja,
> wagi 70/30, renorm 1X2) — wszystkie NIEzwalidowane na danych. Dalsze zmiany psują
> atrybucję (nie wiadomo co pomogło). STOP na nowe λ aż zbierzemy dane.

- [ ] Co kilka dni: `python scripts/calibration_monitor.py` (Neon, read-only)
  - czy kalibracja przestała być **odwrócona** (była: 90%+ pewność → 11% trafność)
  - System (bez Groq) vs Pipeline (Groq) — werdykt bottlenecku LLM (potrzeba ≥15 System settled)
  - czy accuracy ruszyła z 31.7%
- [ ] Po ~20 świeżych settled z naprawionego pipeline → A/B, ocena które λ-zmiany pomogły
- **Zbieranie:** System paper-trading autonomiczne (Task Scheduler 08:00). ~1-2 tyg.
- **Stare 41 settled** są sprzed fixów → wciąż odwrócone, to oczekiwane.

---

## 🎯 JAKOŚĆ λ — kandydaci PO walidacji (nie wcześniej)

- [ ] **Dixon-Coles opponent-adjusted** — λ skorygowane o siłę rywala (z istniejącej historii,
  bez nowych danych). Najwyższy następny lewar.
- [ ] **Kontuzje v2** — waga udziałem w golach (utrata strzelca > rezerwowy); wymaga scrape per-gracz.
- [ ] **ImportanceIndex** (motywacja spadek/tytuł) — `football_data.tabela(kod)` daje kolumny,
  ale brak: mapy nazwa-ligi Bzzoiro→kod football-data.org + cache standings. **Tylko końcówka
  sezonu** ma wartość → odłożone do startu lig (teraz off-season = NORMAL).

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

## 🟡 TECHNICZNE / SECURITY

- [ ] 15.7: weryfikacja własności czatu Telegram (nonce /start przez webhook) —
  przed realnymi userami (security MEDIUM). Teraz: walidacja formatu numerycznego.
- [ ] daily_io — testy (czysta integracja DB, glue nad już-testowanym; niska wartość). Opcjonalne.

---

## 💡 OPCJONALNE rozszerzenia

- [ ] Rynki: dokładny wynik / multigoal (rozliczalne, dużo opcji)
- [ ] Kartki/rożne — wymaga feedu zdarzeń (API-Football statistics) + settlement
- [ ] BetBuilder: Bzzoiro odds dla compound + settlement combo "1 & Over 1.5"
  (teraz kurs = fair 1/szansa; złożone typy nie przechodzą weryfikacji Bzzoiro)

---

## 📋 Następne kroki

1. **Pasywne (priorytet):** monitor co kilka dni, czekaj na ~20 świeżych settled → walidacja
2. **Po walidacji:** Dixon-Coles (jeśli accuracy nadal poniżej celu)
3. **Wymaga Ciebie:** Email (Resend key) → JDG + prawnik → płatności
