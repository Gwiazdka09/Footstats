# FootStats — Project Status Report

**Last Updated:** 2026-06-16
**Current Version:** v3.4-stable
**System State:** FUNCTIONAL — PRODUCTION

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Accuracy** | 🟡 | 31.7% live (41 unikalnych settled, Neon) — Faza 17 fixy wdrożone |
| **Model fixes** | ✅ | Faza 17 (pewność z prob, longshot filtr, whitelist, dedup) DONE |
| **Data collection** | ✅ | System paper-trading (single-leg) autonomiczne od 06-16 |
| **Syntax** | ✅ | 0 SyntaxError |
| **Tests** | ✅ | ~990 testów pass (dodano core/betbuilder/system_paper) |
| **Automation** | ✅ | Task Scheduler: draft 08:00 + final + evening 23:00 |
| **API** | ✅ | FastAPI + Sentry + SlowAPI + CORS + Timeout |
| **DB** | ✅ | Neon PG (prod), keepalives, pool maxconn=10 |
| **Security** | ✅ | Rate limit 60/min, SQL parametryzowane, brak sekretów |
| **Auth** | ✅ | JWT, login/register/delete account (UI w Ustawieniach) |
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
| 1 | Accuracy 31.7% — czeka na świeże settled z naprawionego pipeline (Faza 17.7 A/B) | 🔴 P1 |
| 2 | Email transakcyjny (Resend) — wymaga klucza od użytkownika | 🟡 P2 |
| 3 | JDG rejestracja — przed pierwszym płatnym userem | 🟡 P2 |
| 4 | Płatności (Lemon Squeezy) — nie zintegrowane | 🟡 P2 |
| 5 | 3 moduły core bez testów (daily_io/form/weekly_picks) | ⚪ P4 |

---

## FUNKCJE (recent)

| Funkcja | Faza | Data |
|---------|------|------|
| System paper-trading single-leg (autonomiczne) | 19 | 06-16 |
| Kreator BetBuilder + reguły korelacji | 18 | 06-16 |
| Root-cause accuracy: 6 fixów modelu | 17 | 06-16 |
| Usuwanie konta (RODO) UI + SEO + GUI polish | — | 06-16 |
| Kalibracja + A/B wag 70/30 | 16.4 | 06-16 |

---

## HISTORIA (resolved)

| Problem | Data |
|---------|------|
| Layout: footer ściskał content (flex-row) | 06-16 |
| Pewność z EV → z prob modelu (kalibracja odwrócona) | 06-16 |
| 47 duplikatów predykcji usuniętych z prod Neon | 06-16 |
| Whitelist lig no-op → egzekwowana | 06-16 |
| SPA routing Vercel + frontend deploy | 06-16 |
| Cookie consent + polityka + regulamin (RODO) | 06-15/16 |
| Sentry DSN + Neon idle timeout + UptimeRobot | 06-15 |
| Draw bias fix (p_remis sufit 40%) | 06-12 |
