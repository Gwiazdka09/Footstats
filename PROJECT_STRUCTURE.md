# FootStats Project Structure

Zaktualizowano: 2026-07-27 (po migracji do chmury + Supabase + sprzątaniu repo). Predykcje piłkarskie: Poisson/Dixon-Coles + RAG + Groq LLM.

```plaintext
bot/
├── README.md / README.pl.md   # Dokumentacja (EN / PL)
├── CLAUDE.md                   # Instrukcje projektu dla Claude Code
├── STATUS.md                   # Metryki i zdrowie projektu
├── TODO.md / CHANGELOG.md      # Backlog / historia zmian
├── PROJECT_STRUCTURE.md        # Ten plik
├── LICENSE                     # MIT
│
├── pyproject.toml              # Konfiguracja + zależności (extras: api, ai, scraper)
├── requirements-api.lock       # Przypięte wersje — instaluje Dockerfile.api (+ skan CVE w CI)
├── requirements-jobs.lock      # Przypięte wersje — instaluje Dockerfile.jobs (+ skan CVE w CI)
├── manage.py                   # Entry point pomocniczy
├── .env.example                # Wzór zmiennych środowiskowych (bez sekretów)
│
├── Dockerfile.api              # Obraz API (Cloud Run Service)
├── Dockerfile.jobs             # Obraz batch (Cloud Run Jobs: Playwright+chromium)
├── docker-compose.yml          # Lokalny stack (DB + API)
├── vercel.json                 # Deploy frontendu (Vercel)
│
├── src/footstats/              # === KOD ŹRÓDŁOWY ===
│   ├── __main__.py / cli.py    # CLI (python -m footstats.<modul>)
│   ├── config.py               # Konfiguracja i env
│   ├── daily_agent*.py         # Pętla predykcji (faza draft/final) + decision/output/scheduler
│   ├── evening_agent.py        # Rozliczanie + raport wieczorny
│   ├── operator_agent.py       # Operator (nadzór)
│   ├── betbuilder.py           # BetBuilder (Poisson gole, korelacja)
│   ├── telegram_bot.py         # Wysyłka kuponów/raportów na Telegram
│   ├── weekly_report.py        # Raport tygodniowy (ręczny)
│   ├── ai/                     # LLM: Groq, RAG feedback loop, post-match
│   ├── core/                   # Modele: Poisson, Dixon-Coles, Kelly, kalibracja, settlement, backtest
│   ├── scrapers/               # Zbieranie danych: Bzzoiro API, Playwright, football-data, API-Football
│   ├── api/                    # FastAPI: routes, auth (JWT), admin
│   ├── db/                     # Supabase Postgres: connect, migrations
│   ├── export/                 # Eksport PDF / raporty
│   ├── gui/                    # Frontend React/Vite/Tailwind v4 (Brain Graph)
│   └── utils/                  # Logging, cache, DB helpers, betting math
│
├── scripts/                    # === AUTOMATYZACJA / NARZĘDZIA ===
│   ├── run_job.sh              # Dispatch Cloud Run Jobs (JOB_PHASE: final|draft|evening)  [CLOUD]
│   ├── hooks/guard_live_ops.py # PreToolUse guard: blok lokalnego LIVE pipeline
│   ├── backup_db.py            # Backup DB do GCS
│   ├── settle_coupons.py       # Rozliczanie kuponów (util)
│   ├── run_walkforward_prod.py # Walk-forward backtest
│   ├── calibration_monitor.py  # Monitor kalibracji
│   ├── visualize_brain.py      # Generator Brain Graph (brain_graph.html)
│   ├── accuracy_report.py / sanity_check.py / preflight_footstats.py / evict_cache.py
│   └── run_daily.bat, run_operator.bat, schedule_agents.ps1, silent_run.vbs  [LEGACY LOKALNE — rollback]
│
├── tests/                      # Pytest (1656 testów zebranych, gate cov 56%)
├── docs/                       # Dokumentacja rozszerzona (cloud_migration.md, scheduler_setup.md, blueprints/, roasts/)
│   ├── archive/                # [gitignored] stare raporty PDF + logi kuponów (przeniesione 07-27)
│   └── screenshots/            # [gitignored] screenshoty QA Playwright
├── .claude/                    # Konfiguracja Claude Code: agents/, commands/, rules/, settings
├── .github/workflows/          # CI (ci.yml), CD (cd.yml), backup (backup.yml)
│
├── data/                       # SQLite (legacy backtest) + parquet — NIE RUSZAĆ
├── cache/ · logs/ · .backups/  # Artefakty runtime (gitignored)
└── assets/ · lib/              # Zasoby statyczne / vendored
```

## Pipeline produkcyjny (PC-niezależny)
Cały pipeline działa w **Google Cloud** (projekt `footstats-495009`, `europe-west1`) — patrz `docs/cloud_migration.md`:
- **Cloud Run Jobs:** `footstats-final` (11:00, kupony), `footstats-evening` (23:00, rozliczenie).
- **Cloud Scheduler:** triggery final/evening + draft 07:30 + settle 06:00/21:30.
- **API:** Cloud Run Service (FastAPI). **Frontend:** Vercel. **DB:** Supabase (session pooler eu-west-1) od 20.07 — Neon quota-block do 1.08.
- Lokalne Windows Task Scheduler taski — WYŁĄCZONE (skrypty `.bat/.vbs/.ps1` w `scripts/` zostają na wypadek rollbacku).
- ⚠️ Obraz `footstats-jobs` jest starszy niż commit parquetu → live gra `bzzoiro-ml`, nie Poisson-DC. Rebuild+redeploy = **P0/A** w `TODO.md`.
