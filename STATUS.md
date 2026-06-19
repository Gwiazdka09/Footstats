# FootStats — Project Status Report

**Last Updated:** 2026-06-19
**Current Version:** v3.4-stable
**System State:** FUNCTIONAL — PRODUCTION

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Accuracy (model offline)** | ✅ | Walk-forward 10 lig: DC **51.3%** > baseline 49.6% (NED 54.9%), kalibracja monotoniczna |
| **Accuracy (live)** | 🟡 | 31.7% (stare 58 settled, sprzed fixów Cel B) — czeka na świeże dane po fixach |
| **Model fixes** | ✅ | Cel B root-cause (bug 1 conf naprawiony) + Dixon-Coles w prod (flaga ON) + Faza 17 + A1-A3 + λ |
| **Data collection** | ✅ | System paper-trading (single-leg, bez Groq) autonomiczne od 06-16 |
| **Tests** | ✅ | 1076 testów pass (telegram testy zmockowane — koniec spamu) |
| **Automation** | ✅ | Task Scheduler: draft 08:00 (+System paper) + final + evening 23:00 |
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
| **Daily Agent** | ✅ | Task Scheduler 08:00 (draft+final) + System paper-trading |
| **Evening Agent** | ✅ | Task Scheduler 23:00 |

---

## OTWARTE PROBLEMY

| # | Problem | Priorytet |
|---|---------|-----------|
| 1 | Live accuracy 31.7% (stare settled) — root-cause ZNALEZIONY (Cel B). Bug 1 (conf=Groq fallback zamiast modelu) naprawiony. Bug 2 (ai_tip=selekcja Groq) czeka na ≥15 System settled do decyzji | 🟡 P1 |

### Cel A — walk-forward offline (10 lig, 2026-06-19, out-of-sample, n=25738)
- **A/B:** dixoncoles **51.3%** > baseline 49.6% > poisson_only 48.1%. DC +1.7pp — generalizuje (NED było +1.9pp).
- **Kalibracja MONOTONICZNA** na wszystkich 10 ligach: 37.5% → 43.2% → 46.4% → 58.8% (pasmo 65%+ = strefa zakładów).
- Per liga (DC): NED 54.9, SCO 54.8, ENG 53.4, ITA 53.1, GER 51.5, ESP 51.2, BEL 50.4, FRA 49.8, AUT 47.8, POL 44.6.
- Narzędzie: `python scripts/run_walkforward_prod.py [--liga X] [--max N]` (offline, bez kluczy, zapis `data/walkforward.db`).

### Cel B — root cause live≪offline (2026-06-19)
- **Bug 1 (naprawiony, main):** quick_picks nie budował `pred` → confidence z Groq fallback (overconfident) zamiast modelu → inwersja kalibracji. Fix: quick_picks buduje `pred` dict (072ee9035).
- **Bug 2 (otwarty):** `ai_tip` = selekcja Groq (44% remisy, 12.5% wyjazdy hit) zamiast argmax modelu. Decyzja (a/b/c) po ≥15 System settled.

### Cel C — Dixon-Coles w prod (2026-06-19, main)
- Wpięte za flagą `USE_DIXON_COLES` (default ON, env-toggle), `W_BAYESIAN=0.5`. Blend nad pw/pr/pp przed ensemble, bt/o25 nietknięte, graceful. Lewar +1.7pp zwalidowany. Smoke A/B NED: DC 55.2% > baseline 54.0%.
- Fast-follow: pętla O(n²) — 10 lig ~3-5h; optymalizacja (searchsorted/kursor) w osobnym tasku.
| 2 | Email transakcyjny (Resend) — wymaga klucza od użytkownika | 🟡 P2 |
| 3 | JDG + prawnik — przed pierwszym płatnym userem | 🟡 P2 |
| 4 | Płatności (Lemon Squeezy) — nie zintegrowane (po JDG) | 🟡 P2 |
| 5 | Telegram 15.7: weryfikacja własności czatu (nonce) — przed realnymi userami | 🟡 P3 |
| 6 | ImportanceIndex λ — blocked (standings map + off-season) | ⚪ P4 |

---

## FUNKCJE (recent)

| Funkcja | Data |
|---------|------|
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
