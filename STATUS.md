# FootStats — Project Status Report

**Last Updated:** 2026-06-18
**Current Version:** v3.4-stable
**System State:** FUNCTIONAL — PRODUCTION

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Accuracy** | 🟡 | 31.7% live (41 settled, stare) — pipeline + λ naprawione, czeka na świeże dane |
| **Model fixes** | ✅ | Faza 17 (root-cause) + audyt core A1-A3 + λ (kontuzje, xG+obrona) |
| **Data collection** | ✅ | System paper-trading (single-leg, bez Groq) autonomiczne od 06-16 |
| **Tests** | ✅ | 1037 testów pass (telegram testy zmockowane — koniec spamu) |
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
| 1 | Accuracy 31.7% — czeka na świeże settled (walidacja: monitor + A/B za ~1-2 tyg) | 🔴 P1 |
| 2 | Email transakcyjny (Resend) — wymaga klucza od użytkownika | 🟡 P2 |
| 3 | JDG + prawnik — przed pierwszym płatnym userem | 🟡 P2 |
| 4 | Płatności (Lemon Squeezy) — nie zintegrowane (po JDG) | 🟡 P2 |
| 5 | Telegram 15.7: weryfikacja własności czatu (nonce) — przed realnymi userami | 🟡 P3 |
| 6 | ImportanceIndex λ — blocked (standings map + off-season) | ⚪ P4 |

---

## FUNKCJE (recent)

| Funkcja | Data |
|---------|------|
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
