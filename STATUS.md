# FootStats — Project Status Report

**Last Updated:** 2026-06-16
**Current Version:** v3.4-stable
**System State:** FUNCTIONAL — PRODUCTION

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Accuracy** | 🟡 | 33% live (49 settled, Neon) — Faza 16 w toku |
| **Settled** | 🟡 | 49/50 — brakuje 1 do kalibracji M1 |
| **Syntax** | ✅ | 0 SyntaxError |
| **Tests** | ✅ | 73 test files, ~813 test functions |
| **Automation** | ✅ | Task Scheduler: 4 zadania, LastResult=0 (06-15) |
| **API** | ✅ | FastAPI + Sentry + SlowAPI + CORS + Timeout |
| **DB** | ✅ | Neon PG (prod), keepalives, pool maxconn=10 |
| **Security** | ✅ | Rate limit 60/min, SQL parametryzowane, brak sekretów |
| **Auth** | ✅ | JWT, login/register/delete account |
| **RODO** | ✅ | Cookie consent, polityka prywatności, DELETE /api/auth/me |

---

## DEPLOYMENT STATUS

| Komponent | Status | URL/Info |
|-----------|--------|----------|
| **Frontend** | ✅ Vercel | bot-opal-nu.vercel.app |
| **Backend API** | ✅ Cloud Run | footstats-api-949240532526.europe-west1.run.app |
| **DB** | ✅ Neon.tech | europe-west-4 |
| **Monitoring** | ✅ Sentry | aktywne w Cloud Run |
| **Uptime** | ✅ UptimeRobot | monitor 803305270, /health HEAD+GET |
| **Daily Agent** | ✅ | Task Scheduler 08:00 + 11:00 |
| **Evening Agent** | ✅ | Task Scheduler 23:00 |

---

## OTWARTE PROBLEMY

| # | Problem | Priorytet |
|---|---------|-----------|
| 1 | Accuracy 33% live — czekamy na 50. settled kupon | 🔴 P1 |
| 2 | Email transakcyjny (Resend) — brak konfiguracji | 🟡 P2 |
| 3 | JDG rejestracja — przed pierwszym płatnym userem | 🟡 P2 |
| 4 | Płatności (Lemon Squeezy) — nie zintegrowane | 🟡 P2 |
| 5 | SEO — brak meta tags, sitemap, robots.txt | 🟡 P3 |
| 6 | 20 modułów core bez testów | ⚪ P4 |

---

## HISTORIA (resolved)

| Problem | Data |
|---------|------|
| SPA routing Vercel (rewrite rule) | 06-16 |
| Frontend deploy: bot-opal-nu.vercel.app | 06-16 |
| Cookie consent banner (RODO) | 06-16 |
| Self-service usunięcie konta DELETE /api/auth/me | 06-15 |
| UptimeRobot HEAD fix (/health) | 06-15 |
| Sentry DSN w Cloud Run | 06-15 |
| Neon idle timeout (keepalives) | 06-15 |
| Polityka prywatności (/polityka-prywatnosci) | 06-15 |
| Draw bias fix (p_remis sufit 40%) | 06-12 |
| TD-31 testy bankroll/coupon/kelly | 06-14 |
| Kupony z halucynowanymi kursami Groq (TD-38) | 06-14 |
