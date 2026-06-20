# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-21
**Wersja:** v3.4-stable
**Accuracy:** model offline 51.3% 10 lig (DC, NED 54.9%, kalibracja monotoniczna) | live 31.7% (stare, sprzed fixów Cel B — czeka na świeże)
**Cel:** M1 = 55% win rate

> Ukończone: `git log` + `CHANGELOG.md`. Fazy DONE: 16-20, GUI/UX, SEO, RODO, multi-user (15.6),
> audyt core (A1-A3), λ: kontuzje + xG+obrona, Cel A (walk-forward), Cel B bug 1,
> Cel C (Dixon-Coles w prod), audyt settlement + audyt głęboki (06-18), dług techniczny #1-#5,
> decyzje D1a/D1b/D2/D4/D5/D6/D7 (06-20/21 → `CHANGELOG.md`). Suite: **1167 testów pass / 4 skip**.

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M1** | 55% win rate | 🔴 W toku | świeże settled + walidacja A/B |
| **M2** | 60% win rate | ⏸️ | Po M1 — tuning |
| **M3** | 65% selected | ⏸️ | Po M2 |
| **BETA** | Testerzy | ⏸️ | Po M1 |

---

## 🔴 PRIORYTET — WALIDACJA (czekaj i mierz, pasywne — NIE dokładaj zmian λ)

> Root-cause'y Cel B (bug 1 conf, kalibracja per-wynik) usunięte. Kalibracja OFF (gate
> `CALIBRATION_ENABLED`), auto-refit czeka na dane (D2). Kursy odblokowane (AF `/odds` fallback).
> STOP na nowe λ aż zbierzemy świeże dane.

- [ ] **D3 — Cel B bug 2 (Groq selekcja).** Czeka na ≥15 ŚWIEŻYCH System settled. Potem decyzja:
  ogranicz Groq / argmax modelu / tnij conf.
- [ ] Co kilka dni: `python scripts/calibration_monitor.py` (Neon, read-only)
  - System (bez Groq) vs Pipeline (Groq) — werdykt bottlenecku LLM (potrzeba ≥15 System settled)
  - czy accuracy ruszyła z 31.7%
  - monitoruj licznik settled (D2 auto-refit odpala się sam przy delcie +30 od n_train, patrz `CHANGELOG.md`)
- [ ] Po ~88 settled → D2 auto-refit odpali sam; gdy krzywa zdrowa → włącz `CALIBRATION_ENABLED=1`.
- **Zbieranie:** System paper-trading autonomiczne (Task Scheduler 08:00, draft-only po D5) + settle 23:00.
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

## 🟡 TECHNICZNE / SECURITY

- [ ] **Sofascore 403 stealth** (OPCJONALNE) — `sofascore_odds.py` + form_scraper blokowane
  anti-botem. Tylko jeśli AF `/odds` coverage okaże się za cienki na egzotyczne ligi/MŚ.
- [ ] **Inne god-moduły** (niski priorytet): `cli.py` 1112 linii, `analyzer.py` 930 linii —
  dekompozycja kiedyś (analogiczna do App.jsx/daily_agent).
- [ ] daily_io — testy (czysta integracja DB, glue nad już-testowanym; niska wartość). Opcjonalne.

---

## 💰 MONETYZACJA / LAUNCH (wymaga Ciebie)

### Prawne
- [ ] **D8 — Konsultacja z prawnikiem (ToS bukmacherów) + JDG (CEIDG)** — WSTRZYMANE (sam koniec).
  User waha się: konsekwencje JDG jak się nie uda; prawnik za drogi. Bez akcji. Wrócić po
  walidacji modelu.

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

## 📋 Następne kroki

> Dług techniczny #1-#5 i decyzje D1a/D1b/D2/D4/D5/D6/D7 ZROBIONE (06-20/21, → `CHANGELOG.md`).
> D3/D8 aktywne/wstrzymane. Suite **1167 pass / 4 skip**. Kursy odblokowane (AF `/odds` fallback, live OK).

1. **Zweryfikuj live (jutro po 08:00):** czy System tworzy kupony — teraz ma kursy (AF fallback)
   + sygnał (kalibracja OFF). Sprawdź `calibration_monitor.py` + liczbę nowych ACTIVE/settled.
2. **Pasywne:** zbieraj świeże settled (wolne tempo OK, mecze nie co godzinę). Pilnuj budżetu AF (100/dzień).
3. **Po walidacji (~88 settled):** D2 auto-refit odpali sam; gdy krzywa zdrowa →
   włącz `CALIBRATION_ENABLED=1`; D3 decyzja Cel B bug 2 (Groq selekcja).
4. **Opcjonalnie:** Sofascore 403 stealth (tylko jeśli AF coverage za cienki na egzotyki).
5. **Sam koniec (D8):** JDG/prawnik — wstrzymane (koszt/ryzyko). Email/płatności po walidacji.
