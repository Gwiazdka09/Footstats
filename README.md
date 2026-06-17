# ⚽ FootStats v3.4 — Autonomous AI Soccer Prediction Engine

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: Portfolio](https://img.shields.io/badge/License-All%20Rights%20Reserved-yellow.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)
[![Playwright](https://img.shields.io/badge/Playwright-1.40-45ba4b.svg)](https://playwright.dev/)
[![Tests](https://img.shields.io/badge/tests-1037-brightgreen.svg)](tests/)

**FootStats** to autonomiczny system typowania piłkarskiego łączący statystykę Bayesowską (Poisson + Dixon-Coles), ML (CatBoost/Bzzoiro), analizę xG (Understat) oraz LLM (Groq/Llama 3.1). Działa w pełni bezobsługowo: scraping → analiza → generowanie kuponu → rozliczenie → nauka na błędach. Frontend React/Vite (Vercel), backend FastAPI (Cloud Run), DB Neon PostgreSQL.

---

## 🚀 Dla Rekrutera

Projekt demonstruje zaawansowane techniki inżynierii oprogramowania:

| Obszar | Implementacja |
|--------|--------------|
| **Autonomous Agents** | Scheduler Draft→Final, Evening Agent (23:00), Operator Agent |
| **RAG Feedback Loop** | Groq analizuje przegrane kupony → wektory → kontekst następnej predykcji |
| **Feature Engineering** | Poisson + xG (atak×obrona rywala) + forma H/A + zmęczenie/rotacja + kontuzje (dwustronne) + sędzia |
| **Bayesian Statistics** | Isotonic kalibracja + renorm 1X2, ensemble Poisson+ML (wagi per-liga), CLV tracking |
| **Advanced Scraping** | Playwright (Superbet, FlashScore, STS), requests (Understat, Bzzoiro, API-Football) |
| **Full-Stack** | FastAPI REST (Cloud Run) + React/Vite SPA (Vercel) + Neon PostgreSQL + multi-user (JWT) |
| **Quality** | 1037 testów pytest, regression gate na broad-except, CI + Docker health + daily DB backup |

---

## 🏗️ Architektura Systemu

```mermaid
graph TD
    A[daily_agent_scheduler] -->|08:00 Draft| B(Pobierz kandydatów)
    A -->|Match -70min Final| C(Wzbogać składy + sędzia)

    subgraph "Data Sources"
        D[API-Football]
        E[Bzzoiro ML / CatBoost]
        F[Playwright Scrapers]
        G[Understat xG]
    end

    B --> D & E
    C --> F & D

    B --> H[Poisson Bayesian]
    G -->|20% blend| H
    H --> I[Groq AI Analyzer]

    I -->|lekcje| J[(RAG: Lessons DB)]
    J -->|kontekst| I
    I --> K[Coupon Generation]

    K --> L[(footstats_backtest.db)]
    L --> M[React SPA Vercel]
    L --> N[FastAPI /api]

    O[Evening Agent 23:00] --> L
    O -->|CLV| P[API-Football /odds]
    O -->|rozliczenie| L
```

---

## 🛠️ Tech Stack

| Warstwa | Technologia |
|---------|-------------|
| **AI / ML** | Groq (Llama 3.1 70B/8B), CatBoost (Bzzoiro), Poisson Bayesian, Ensemble |
| **Feature Eng.** | xG (Understat), forma H/A (`core/form.py`), zmęczenie (`core/fatigue.py`), kontuzje |
| **Scraping** | Playwright, requests + BS4, Understat JSON, API-Football v3 |
| **Backend** | FastAPI, Uvicorn, Neon PostgreSQL (prod) / SQLite (dev), Pydantic v2 |
| **Frontend** | React/Vite SPA (Vercel) — kreator kuponów, BetBuilder, katalog rynków; Streamlit/Rich (dev/CLI) |
| **Tracking** | CLV (Closing Line Value), A/B accuracy tab, weekly per-liga raport |
| **Ops** | Windows Task Scheduler, Cloud Run (GCP), Docker, Sentry |

---

## 🌟 Główne Funkcje

### Predykcja
- **Bayesian Poisson v2.6** — walk-forward kalibracja biasu, blending 20% xG z Understat
- **Ensemble Model** — Poisson + Bzzoiro CatBoost, `roznica_modeli` jako feature pewności
- **xG Integration** — Understat scraper (bezpłatny), 6h cache, prefetch przed pętlą predykcji
- **Feature Engineering** — forma domowa/wyjazdowa, H2H patent, zmęczenie, sędzia, kontuzje, murawa

### Zarządzanie Ryzykiem
- **Kelly Criterion v2** — dynamiczne stawki na podstawie bankrollu i hit-rate
- **Stop-Loss** — dzienny (−10% bankrollu) + streak detection (−stawki przy 3+ z rzędu)
- **Value Bet Filter** — EV > 3%, Kelly > 1%, pre-filtr przed Groq (oszczędność tokenów)

### Automatyzacja
- **Draft Phase (08:00)** — kandydaci z Bzzoiro + API-Football Ekstraklasa, Poisson, Groq
- **Final Phase (mecz −70 min)** — składy z API-Football, decyzja kuponu, wysyłka Telegram
- **Evening Agent (23:00)** — rozliczenie ACTIVE kuponów, CLV capture, auto-trainer po 20+ wynikach
- **RAG Feedback Loop** — post-match AI analiza porażek → wektory → kontekst

### Monitoring
- **CLV Tracking** — automatyczny zapis closing odds z API-Football po każdym meczu
- **Dashboard A/B** — porównanie accuracy wariantu A vs B
- **Weekly Report** — skuteczność per liga, ROI, accuracy trend
- **Second Mind Graph** — vis-network wizualizacja wiedzy bota (`brain_graph.html`)

---

## 📦 Struktura Projektu

```plaintext
src/footstats/
├── ai/            # analyzer.py (Groq prompt), trainer.py, RAG, post_match_analyzer
├── core/          # poisson.py, backtest.py, bankroll.py, clv_tracker.py, form.py, fatigue.py
├── scrapers/      # bzzoiro.py, superbet.py, understat_xg.py, api_football.py, kursy.py …
├── api/           # FastAPI routes (coupons, predictions, bankroll, status)
├── utils/         # telegram_notify.py, db.py, normalize.py, cache.py
├── daily_agent.py         # główny agent (1400 LOC)
├── evening_agent.py       # rozliczanie kuponów @ 23:00
├── daily_agent_scheduler.py
└── operator_agent.py      # smoke + pipeline + review orchestrator
tests/             # 1037 testów pytest
scripts/           # preflight, backup_db, visualize_brain, run_operator.bat
data/              # footstats_backtest.db, model_calibration.json
cache/             # api_football/, understat_xg/, flashscore/, kursy/
```

---

## 🛠️ Instalacja i Uruchomienie

```bash
# 1. Klonowanie i środowisko
git clone https://github.com/user/footstats.git
cd footstats
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e .
playwright install chromium

# 2. Konfiguracja
cp .env.example .env
# Uzupełnij: GROQ_API_KEY, APISPORTS_KEY, BZZOIRO_KEY, JWT_SECRET

# 3. Dashboard
streamlit run src/footstats/dashboard.py

# 4. Daily Agent (ręcznie)
python -m footstats.daily_agent --dni 3 --faza draft

# 5. Evening Agent (ręcznie)
python -m footstats.evening_agent --date 2026-05-27

# 6. Kalibracja modelu Poisson
python -m footstats.core.lambda_optimizer

# 7. Second Mind Graph
python scripts/visualize_brain.py
# → otwórz brain_graph.html
```

---

## 🤖 Operator Agent

Orchestrator uruchamia preflight → smoke API → `daily_agent` draft → review Groq.

```bash
python scripts/preflight_footstats.py
python -m footstats.operator_agent --only smoke
python -m footstats.operator_agent --faza full
python -m footstats.operator_agent --only review
```

Logi: `data/logs/operator_agent.log` | Raporty: `data/operator_reports/`

---

## 🧪 Testy

```bash
pytest tests/ -v                          # 1037 testów
pytest tests/test_poisson.py -v           # Bayesian Poisson + edge cases
pytest tests/test_clv_tracker.py -v       # CLV tracking
pytest tests/test_broad_except_audit.py   # regression gate: brak nowych broad except
pytest tests/test_version_consistency.py  # pyproject.toml == config.VERSION
```

---

## 📊 Status Accuracy

| Milestone | Cel | Status |
|-----------|-----|--------|
| **M0** | ~42% (baseline) | ✅ Aktualne |
| **M1** | 55% overall | 🔄 W toku — kalibracja + xG blend |
| **M2** | 60% overall | Bayesian ensemble + value filter |
| **M3** | 65% selected | Full xG + stop-loss + CLV gate |
| **M4** | 70% selected | 3-miesięczny track record |

---

## Licencja

All Rights Reserved — kod udostępniony do przeglądu portfolio/CV, bez prawa kopiowania,
redystrybucji ani użycia w innych projektach. Szczegóły: [LICENSE](LICENSE).
