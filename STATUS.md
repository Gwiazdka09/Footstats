# FootStats — Project Status Report

**Last Updated:** 2026-06-22
**Current Version:** v3.4-stable
**System State:** FUNCTIONAL — PRODUCTION

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Accuracy (model offline)** | ✅ | Walk-forward 10 lig: DC **51.3%** > baseline 49.6% (NED 54.9%), kalibracja monotoniczna |
| **Accuracy (live)** | 🟡 | 31.7% (stare 58 settled, sprzed fixów Cel B) — czeka na świeże dane po fixach |
| **Model fixes** | ✅ | Cel B root-cause USUNIĘTY (bug 1 conf + bug kalibracji per-wynik 1X2, `11cc57232`) + D3 część 1+2 (prob modelu w `predictions` + guard `koryguj_tip_wg_modelu`, `4823ac9c0`) + Dixon-Coles w prod (flaga ON) + Faza 17 + A1-A3 + λ |
| **Kalibracja** | 🟡 | Gate `CALIBRATION_ENABLED` OFF (identity) — zdegenerowana krzywa psuła Kelly/value-bet. Auto-refit co +30 settled wpięty (D2), czeka na próg ~88 settled |
| **Kursy (odds)** | ✅ | Fallback chain Bzzoiro → API-Football `/odds` (live OK, zero anti-bot) → Sofascore (403, niski priorytet) |
| **Data collection** | ✅ | System paper-trading (single-leg, bez Groq) autonomiczne od 06-16 |
| **Email transakcyjny** | ✅ | Resend (`utils/mailer.py`) wpięty — welcome po `/auth/register` (live OK, dostarczony). Limit Free 100/dzień, 3000/mc. FROM=test-sender, podmień przed prod |
| **Rynki bukmacherskie** | ✅ | + "Mecz & gol w każdej połowie" (GG2H, Poisson half-model) + HT capture z API-Football (`67f5f418b`) |
| **Tests** | ✅ | 1209 testów pass / 4 skip (telegram zmockowane; +cli/analyzer/daily_io/stealth 06-21; +D3/email/rynek GG2H 06-22) |
| **Automation** | ✅ | Task Scheduler: draft 08:00 (zapisuje wszystko, enrich) + final 11:00 + evening 23:00. No-faza `FootStats-DailyAgent` WYŁĄCZONY (D5, redundantny) |
| **API** | ✅ | FastAPI + Sentry + SlowAPI + CORS + Timeout |
| **DB** | ✅ | Neon PG (prod), keepalives, pool maxconn=10, migracja 6 (telegram_chat_id) |
| **Security** | ✅ | Rate limit 60/min, SQL parametryzowane, walidacja telegram chat_id |
| **Auth** | ✅ | JWT, login/register/delete, per-user (bankroll/settings/telegram) |
| **RODO** | ✅ | Cookie consent, polityka, regulamin, self-delete UI |
| **SEO** | ✅ | meta/OG/Twitter, sitemap.xml, robots.txt |

---

## DEPLOYMENT STATUS

| Komponent | Status | URL/Info |
|-----------|--------|----------|
| **Frontend** | ✅ Vercel | bot-opal-nu.vercel.app |
| **Backend API** | ✅ Cloud Run | footstats-api-949240532526.europe-west1.run.app |
| **DB** | ✅ Neon.tech | europe-west |
| **Monitoring** | ✅ Sentry | aktywne w Cloud Run |
| **Uptime** | ✅ UptimeRobot | monitor 803305270, /health HEAD+GET |
| **Daily Agent** | ✅ | Task Scheduler 08:00 Draft + 11:00 Final + System paper-trading (no-faza task WYŁĄCZONY, D5) |
| **Evening Agent** | ✅ | Task Scheduler 23:00 |

---

## OTWARTE PROBLEMY

| # | Problem | Priorytet |
|---|---------|-----------|
| 1 | Live accuracy 31.7% (stare 58 settled, sprzed fixów) — root-cause Cel B **USUNIĘTY w całości**: bug 1 (conf=Groq fallback) + bug kalibracji per-wynik 1X2 (`11cc57232`, 06-20). Bug 2 (ai_tip=selekcja Groq, D3) — część 1+2 ZROBIONE 06-22 (prob modelu + guard, `4823ac9c0`); pełna decyzja a/b/c czeka na ≥20 ŚWIEŻYCH settled z zapisanym prob | 🟡 P1 |

### Cel A — walk-forward offline (10 lig, 2026-06-19, out-of-sample, n=25738)
- **A/B:** dixoncoles **51.3%** > baseline 49.6% > poisson_only 48.1%. DC +1.7pp — generalizuje (NED było +1.9pp).
- **Kalibracja MONOTONICZNA** na wszystkich 10 ligach: 37.5% → 43.2% → 46.4% → 58.8% (pasmo 65%+ = strefa zakładów).
- Per liga (DC): NED 54.9, SCO 54.8, ENG 53.4, ITA 53.1, GER 51.5, ESP 51.2, BEL 50.4, FRA 49.8, AUT 47.8, POL 44.6.
- Narzędzie: `python scripts/run_walkforward_prod.py [--liga X] [--max N]` (offline, bez kluczy, zapis `data/walkforward.db`).

### Cel B — root cause live≪offline (2026-06-19/20, USUNIĘTY w całości)
- **Bug 1 (naprawiony, main):** quick_picks nie budował `pred` → confidence z Groq fallback (overconfident) zamiast modelu → inwersja kalibracji. Fix: quick_picks buduje `pred` dict (072ee9035).
- **Bug kalibracji per-wynik 1X2 (naprawiony 06-20, `11cc57232`):** `calibrate_confidence` zaprojektowane dla 1 liczby, stosowane per-wynik (pw/pr/pp/bt/o25) → na zdegenerowanej krzywej spłaszczało do uniform. Fix: nie kalibruj per-wynik. Towarzyszący gate `CALIBRATION_ENABLED` OFF domyślnie (`9faa72067`) — Kelly/value-bet już nie zaniżane.
- **Bug 2 — D3 część 1+2 ZROBIONE (06-22, `4823ac9c0`):** prob modelu (pw/pr/pp) zapisywane w
  `predictions` (migracja 8, prerekwizyt analizy) + guard konserwatywny `koryguj_tip_wg_modelu`
  (Groq tip 1X2 z prob <15% → override na argmax). **Pełna decyzja a/b/c** (próg guardu, czy
  argmax na stałe) — w TODO, czeka na ≥20 ŚWIEŻYCH settled z zapisanym prob.

### Cel C — Dixon-Coles w prod (2026-06-19, main)
- Wpięte za flagą `USE_DIXON_COLES` (default ON, env-toggle), `W_BAYESIAN=0.5`. Blend nad pw/pr/pp przed ensemble, bt/o25 nietknięte, graceful. Lewar +1.7pp zwalidowany. Smoke A/B NED: DC 55.2% > baseline 54.0%.
- Fast-follow: pętla O(n²) — 10 lig ~3-5h; optymalizacja (searchsorted/kursor) w osobnym tasku.

### Kursy 2. źródło — D1b/D6 (2026-06-20/21, ROZWIĄZANE)
- Fallback chain: Bzzoiro → API-Football `/odds` (`131abc1bf`, PODSTAWOWY, zero anti-bot, live smoke potwierdził) → Sofascore (`6b3b2bfd1`, 2. fallback, obecnie 403 anti-bot — niski priorytet).

| 2 | Email transakcyjny (Resend) — wpięty 06-22 (`8dcb76a27`), live OK; FROM=test-sender, podmień domenę przed prod | 🟢 P3 |
| 3 | JDG + prawnik — przed pierwszym płatnym userem (D8: WSTRZYMANE, user się waha — koszt/ryzyko) | 🟡 P2 |
| 4 | Płatności (Lemon Squeezy) — nie zintegrowane (po JDG) | 🟡 P2 |
| 5 | ImportanceIndex λ — blocked (standings map + off-season) | ⚪ P4 |
| 6 | Sofascore 403 anti-bot (odds + form_scraper) — OPCJONALNE stealth, tylko jeśli AF coverage za cienki | ⚪ P4 |

---

## FUNKCJE (recent)

| Funkcja | Data |
|---------|------|
| **D3 część 1+2** — prob modelu w `predictions` (migracja 8) + guard `koryguj_tip_wg_modelu` (Groq tip <15% prob → override argmax) | 06-22 |
| **Email transakcyjny Resend** — welcome po rejestracji (live OK) + **rynek GG2H + HT capture** (Poisson half-model, settlement z HT) | 06-22 |
| **Cel B root cause USUNIĘTY w całości** (bug kalibracji per-wynik 1X2, `11cc57232`) + gate `CALIBRATION_ENABLED` OFF | 06-20 |
| **Kursy 2. źródło** — fallback chain Bzzoiro → API-Football `/odds` (live OK) → Sofascore (D1b/D6) | 06-20/21 |
| **Dług techniczny #1-#5** — App.jsx 2144→267, daily_agent 1553→1046, health-check scraperów, backtest_engine usunięty, kalibracja gate | 06-20/21 |
| **D2 auto-refit kalibracji** co +30 settled (evening_agent) + **D7 Telegram nonce** (weryfikacja własności czatu) | 06-21 |
| **Dixon-Coles w prod (flaga USE_DIXON_COLES, +1.7pp 10 lig)** | 06-19 |
| **Cel B root cause (bug 1 conf naprawiony) + walk-forward 10 lig** | 06-19 |
| **Cel A walk-forward harness offline (replay prod, no-lookahead, SQLite)** | 06-18 |
| Audyt core A1-A3 (ensemble 70/30, heurystyka/klasyfikacja, renorm 1X2) | 06-17 |
| λ: kontuzje (dwustronne) + xG+obrona rywala — koniec martwego kodu | 06-17 |
| Multi-user 15.6 (per-user bankroll/settings/telegram) | 06-17 |
| System paper-trading single-leg + katalog rynków (Faza 19/20) | 06-16 |
| Root-cause accuracy Faza 17 + BetBuilder Faza 18 | 06-16 |

---

## HISTORIA (resolved — wybrane)

| Problem | Data |
|---------|------|
| **Telegram spam (Arsenal-Chelsea 3:2)** — testy wysyłały realnie, zmockowane | 06-17 |
| backup.yml padał — przywrócono backup_db.sh (błędnie usunięty) | 06-17 |
| 5 sygnałów λ liczonych ale niewpiętych w daily (audyt core) | 06-17 |
| Layout footer ściskał content; pewność z EV; 47 duplikatów predykcji | 06-16 |
| Whitelist lig no-op; SPA routing Vercel; frontend deploy | 06-16 |
| Cookie consent + RODO; Sentry; Neon idle timeout; UptimeRobot | 06-15/16 |
