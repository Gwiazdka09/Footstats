# FootStats — Project Status Report

**Last Updated:** 2026-08-14
**Current Version:** v3.4-stable
**System State:** FUNCTIONAL — PRODUCTION (pipeline PC-off na Cloud Run Jobs, DB = Supabase, dziennik kuponów J1-J6 live)
**Suite:** **4375 testów** (11 skipped), ruff + bandit czyste
**Nowe (08-14):** rozliczenia przestały gubić predykcje (okno bez nadrabiania → 95 sierot; migracja 12 + limit prób) · rozjazd wag ensemble zlikwidowany (joby = API = 0.70) · `CRON_SECRET` → `secretKeyRef` + rotacja · wyłączona wersja 1 sekretu `DATABASE_URL` (zawierała hasło Neona)
**Nowe (08-13):** siła drużyny liczona też ze strzałów celnych (Brier 0.6454→0.6064) · raport uczenia czyta `model_log` · lekcje także z trafień
**Nowe (07-27):** auth hardening po incydencie logowania (malformed hash → 401 nie 500, MCP tylko poza prod, CD re-asercje sekretów, LoginView rozróżnia błąd serwera od złych danych) + skrypt backfillu users Neon→Supabase
**Nowe (07-21/22):** dziennik kuponów J1-J6 (statystyki usera, krzywa postępu, ręczny wpis, leaderboard v2, predykcja jako sygnał) + match-linking + auto-settle manual

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Accuracy (model offline)** | ✅ | Walk-forward 10 lig: DC **51.3%** > baseline 49.6% (NED 54.9%), kalibracja monotoniczna |
| **Accuracy (live)** | 🟡 | 231 predykcji / 133 rozliczonych. Backfill z Neona **zrobiony**. Główne źródło to `model_log` (oceny PRZED filtrami): poisson-dc **65.2%** (15/23), bzzoiro-ml 50.0% (41/82) — próba wciąż mała |
| **Model faktycznie grający live** | ✅ | **`poisson-dc`** — parquet w obrazach jobów i API (08-13), a `QUICK_PICKS_USE_POISSON_CACHE` przestawione 0→1 na API (14.08). Przy `=0` draft z definicji chodził na `bzzoiro-ml`, stąd 218 vs 10 w historii |
| **Czy model bije rynek (1X2)** | 🔴 | **NIE.** WF 14.08, n=3578, 3 grupy: przy niezgodzie model↔rynek (510 meczów) rynek trafia **42.9%**, model **29.8%**. ROI ujemne przy KAŻDEJ wadze. Poprawki z 13.08 tego nie zmieniły |
| **RAG factors** | 🟡 | `factors='[]'` to **NIE bug** (werdykt 13.08) — odtworzenie łańcucha offline na tych samych 18 meczach daje 0/18 tak samo jak live. TWIERDZA wymaga serii ≥5, grane drużyny miały 0-3. Na próbce 300 meczów tagi zapalają się w 31.7%. Wąskie gardło = liczba predykcji |
| **Rozliczenia** | ✅ | Okno gubiło predykcje **bezpowrotnie** (95 sierot, mecze od 7 maja; 13 do odzyskania, 82 stracone). Naprawione 14.08: zaległości wracają paczkami po 15, limit 5 prób, migracja 12 `settle_attempts`. Joby migrują teraz same |
| **Model fixes** | ✅ | Cel B root-cause USUNIĘTY (bug 1 conf + bug kalibracji per-wynik 1X2, `11cc57232`) + D3 część 1+2 (prob modelu w `predictions` + guard `koryguj_tip_wg_modelu`, `4823ac9c0`) + Dixon-Coles w prod (flaga ON) + Faza 17 + A1-A3 + λ |
| **Kalibracja** | 🟡 | Gate `CALIBRATION_ENABLED` OFF (identity) — zdegenerowana krzywa psuła Kelly/value-bet. Auto-refit co +30 settled wpięty (D2), czeka na próg ~88 settled |
| **Kursy (odds)** | ✅ | Fallback chain Bzzoiro → API-Football `/odds` (live OK, zero anti-bot) → Sofascore (403, niski priorytet) |
| **Data collection** | ✅ | System paper-trading (single-leg, bez Groq) od 06-16 + **cloud-draft PC-niezależny** (`/cron/draft` + Cloud Scheduler `footstats-draft-morning` 07:30 CEST, requests-only, dry_run=false live) — draft już nie zależy od PC |
| **Ensemble waga** | ✅ | `ENSEMBLE_MARKET_WEIGHT=0.70` (30/70 model/rynek) na API **oraz jobach** — rozjazd zlikwidowany 14.08. Do tego dnia joby chodziły na 70/30, więc ten sam mecz dawał inną predykcję zależnie od ścieżki. Przeliczony WF n=3578 potwierdził przewagę rynku |
| **quick_picks Poisson** | ✅ | **fix schema mismatch 06-26** — `load_cached()` (eng) walidowany jako pl → Poisson cicho pomijany → Bzzoiro-ML. Adapter `adapt_to_prod_schema`, default ON (`QUICK_PICKS_USE_POISSON_CACHE`). Realna poprawa na restart lig klubowych (sierpień) |
| **Email transakcyjny** | ✅ | Resend (`utils/mailer.py`) wpięty — welcome po `/auth/register` (live OK, dostarczony). Limit Free 100/dzień, 3000/mc. FROM=test-sender, podmień przed prod |
| **Rynki bukmacherskie** | ✅ | + "Mecz & gol w każdej połowie" (GG2H, Poisson half-model) + HT capture z API-Football (`67f5f418b`) |
| **Scrapery multi-source** | ✅ | `scrapers/sources/` — `MatchData`+`ResultsSource`+`aggregator`; 3 źródła (API-Football, football-data.co.uk, FlashScore mobi); live cross-walidacja: AF 79+FlashScore 98 meczów, 27 potwierdzonych ≥2 źródła, 0 rozjazdów (`5c0a9adc2` i nast.) |
| **Brain graph** | ✅ | `scripts/visualize_brain.py` przepisany — 41 węzłów, warstwowa architektura aktualna (agenty/AI/model/settlement/scrapery/sources/API/DB) (`53499bbfc`) |
| **CI/CD** | ✅ | `ci.yml` 5 jobów: lint (`ruff` E9+F / `mypy` sources) + security (`bandit` + `pip-audit`) + secrets (`gitleaks`) + test + docker-health. Dependabot (pip/npm/actions) + pre-commit. CI+CD green na main (06-25) |
| **Standardy kodu** | ✅ | god-moduły rozbite: `superbet.py` 1128→867 (06-25), `daily_agent.py` 1078→818 (output+decision), `utils/logging.py` 723→539 (exceptions+safe_http). Ruff lint gate w CI |
| **Dziennik kuponów** | ✅ | **J1-J6 DONE (07-21/22):** `core/user_stats.py` (ROI/win-rate/streak) · `StatsView` + `ProgressChart` (recharts) · ręczny wpis kuponu (`POST /api/coupon/manual`, kolumna `bookmaker`) · leaderboard v2 (sort+filtr dni, shared-only opt-in) · podgląd sygnału modelu w formularzu (`/api/coupon/preview-signal`) |
| **Match-linking** | ✅ | `core/match_linker.py` (STRICT `_norm_ascii`, exact-only) + `settle_manual_coupons` all-legs-or-nothing + `POST /cron/settle-manual` (**NIE wpięty w scheduler** — decyzja usera) |
| **Tests** | ✅ | **1656 testów zebranych**; 23 integracyjne biją w `DATABASE_URL` z `.env` (dług testowy: marker `@pytest.mark.integration` + test-DB) |
| **Automation** | ✅ | **Cloud Run Jobs** `footstats-final` 11:00 + `footstats-evening` 23:00 + Scheduler (draft 07:30, settle 06:00/21:30). Lokalne Task Scheduler taski **WYŁĄCZONE** (`.bat/.vbs` zostają na rollback) |
| **API** | ✅ | FastAPI + Sentry + SlowAPI + CORS + Timeout. `/mcp` montowany **tylko poza prod** (07-27) |
| **DB** | 🟡 | **Supabase free** (session pooler eu-west-1) od 20.07, RLS na 11 tabelach. Neon zablokowany quota do **1.08** → backfill (`scripts/backfill_users_from_neon.py`, users gotowe; predictions+coupons do dopisania) |
| **Security** | ✅ | **Auth hardening 07-27** (po incydencie): login odporny na malformed `password_hash` (401 nie 500), `/mcp` off w prod, CD jawnie re-asertuje krytyczne sekrety przy deployu (self-heal po zgubieniu env), LoginView rozróżnia błąd serwera/limit/sieć od złych danych. Audyt auth: 6 znalezisk, rdzeń szczelny. **Hardening OWASP API Top 10 LIVE (06-25)**: `/health` bez danych biznesowych, `/metrics` za METRICS_TOKEN (401), `/docs`+`/openapi` off w prod (ENV), nagłówki nosniff/DENY/HSTS/no-referrer, rate-limit login 10/min + register 5/min. SQL parametryzowane, JWT_SECRET fail-closed, zero hardcoded sekretów (gitleaks/bandit/pip-audit czyste), telegram chat_id allowlist |
| **Auth** | ✅ | JWT, login/register/delete, per-user (bankroll/settings/telegram) |
| **RODO** | ✅ | Cookie consent, polityka, regulamin, self-delete UI |
| **SEO** | ✅ | meta/OG/Twitter, sitemap.xml, robots.txt |

---

## DEPLOYMENT STATUS

| Komponent | Status | URL/Info |
|-----------|--------|----------|
| **Frontend** | ✅ Vercel | bot-opal-nu.vercel.app |
| **Backend API** | ✅ Cloud Run | footstats-api-949240532526.europe-west1.run.app |
| **DB** | ✅ Supabase free | session pooler eu-west-1 (od 20.07). Neon: quota-block do 1.08, do backfillu + rotacji hasła |
| **Monitoring** | ✅ Sentry | aktywne w Cloud Run |
| **Uptime** | ✅ UptimeRobot | monitor 803305270, /health HEAD+GET |
| **Daily Agent** | ✅ Cloud Run Job | `footstats-final` 11:00 (PC-off). Lokalne taski Windows wyłączone |
| **Cloud-draft** | ✅ | Cloud Scheduler `footstats-draft-morning` 07:30 CEST → `/api/cron/draft?dry_run=false` (idempotentny). ⚠️ `model_source=bzzoiro-ml` — parquet nie w obrazie (P0/A) |
| **Settle (cloud)** | ✅ | Cloud Scheduler `footstats-settle-morning` (06:00 UTC) + wieczorny. `/cron/settle-manual` istnieje, **nie wpięty** |
| **Evening Agent** | ✅ Cloud Run Job | `footstats-evening` 23:00 |

---

## OTWARTE PROBLEMY

| # | Problem | Priorytet |
|---|---------|-----------|
| 1 | **Live gra `bzzoiro-ml`, nie Poisson-DC** — obraz jobs starszy niż commit parquetu → `load_cached()`=None → fallback. Fix: rebuild+redeploy `footstats-jobs`. Timing: powrót lig klubowych ~poł. sierpnia | 🔴 **P0 / A** |
| 2 | **`factors` puste 15/15** — `pred` sub-dict pusty w quick_picks `wyniki` → `wyciagnij_faktory` puste → RAG nie ma się na czym uczyć. Data-independent, TDD | 🔴 **P3 / C** |
| 3 | **Data-starved (6 settled)** — backfill Neon→Supabase `predictions`+`coupons` po 1.08 + rotacja hasła Neon (wisiało plaintext w env Cloud Run) | 🔴 **P2 / B**, twarda data 1.08 |
| 4 | Bug 2 (ai_tip = selekcja Groq, D3) — część 1+2 ZROBIONE 06-22 (prob modelu + guard, `4823ac9c0`); pełna decyzja a/b/c czeka na ≥20 ŚWIEŻYCH settled z zapisanym prob | 🟡 P1 |
| 5 | **CSS cascade-layer bug (app-wide)** — `gui/src/index.css` reset `button {color:inherit}` poza `@layer` → w Tailwind v4 bije utility-klasy, `text-*`/`bg-*` na każdym `<button>` nie działa. Obejście: inline `style var()`. Fix = `@layer base` + regresja wizualna | 🟡 P1 |
| 6 | **Dług testowy** — `config.py` `load_dotenv(override=True)` → 23 testy integracyjne biją w prod `DATABASE_URL`. Fix: marker `@pytest.mark.integration` + test-DB | 🟡 P1 |

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

| 7 | Email transakcyjny (Resend) — wpięty 06-22 (`8dcb76a27`), live OK; FROM=test-sender, podmień domenę przed prod | 🟢 P3 |
| 8 | JDG + prawnik / płatności (Lemon Squeezy) — **ARCHIWUM** (pivot 07-06: zero monetyzacji; kierunek 07-21: prywatny użytek + beta-testerzy) | 🗄️ |
| 9 | ImportanceIndex λ — blocked (standings map + off-season) | ⚪ P4 |
| 10 | Sofascore 403 anti-bot (odds + form_scraper) — OPCJONALNE stealth, tylko jeśli AF coverage za cienki | ⚪ P4 |

---

## FUNKCJE (recent)

| Funkcja | Data |
|---------|------|
| **Auth hardening po incydencie logowania** — redeploy zgubił env Cloud Run (JWT_SECRET itd.) → login 500 udający „złe hasło". Fix rev 00313-mf5 + `335df65bb` (malformed hash → 401) + `0cded9b4d` (`/mcp` off w prod) + `b5c49484a` (CD re-asercje sekretów) + `cc4574d16` (LoginView) + `17a2ecea4` (backfill users Neon→Supabase) | 07-27 |
| **Dziennik kuponów J1-J6** — statystyki usera (`core/user_stats.py`) + `StatsView` + krzywa postępu (recharts) + ręczny wpis kuponu + leaderboard v2 (sort/filtr dni) + predykcja jako sygnał w formularzu. Match-linking (`core/match_linker.py`) + auto-settle manual (`/cron/settle-manual`, nie wpięty) | 07-21/22 |
| **Migracja DB → Supabase** (Neon quota-block) + `.gcloudignore` fix (image jobs bez `footstats.data`) + None-guardy Groq (`kupon=None` crash) — pierwszy zielony `footstats-final` od 13.07 | 07-20 |
| **Cloud-draft PC-niezależny** (`/cron/draft` + scheduler 07:30 CEST, requests-only) + **reweight 30/70 live** (rev 00274) + **quick_picks Poisson schema fix** (eng load_cached → pl, default ON) + ml_features/standings (infra ML, dead-end) | 06-26 |
| **Scrapery multi-source + cross-walidacja** — framework `scrapers/sources/` (MatchData/ResultsSource/aggregator) + 3 źródła (API-Football, football-data.co.uk, FlashScore); live 27 meczów potwierdzonych ≥2 źródła, 0 rozjazdów; **brain graph szczegółowy** (41 węzłów) | 06-23 |
| **FlashScore live-leak fix** — `_parse_mobi_html` ignorował `class="fin"`, mecz w trakcie zwracany jako końcowy → kupony #240/241/242 LOST błędnie; fix + revert do ACTIVE + cache wyczyszczony | 06-23 |
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
