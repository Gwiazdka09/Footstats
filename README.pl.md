# ⚽ FootStats v3.4 — Autonomous AI Soccer Prediction Engine

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: Portfolio](https://img.shields.io/badge/License-All%20Rights%20Reserved-yellow.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)
[![Playwright](https://img.shields.io/badge/Playwright-1.40-45ba4b.svg)](https://playwright.dev/)
[![Tests](https://img.shields.io/badge/tests-1346-brightgreen.svg)](tests/)

**🌐 [English](README.md) · Polski**

**FootStats** to autonomiczny system typowania piłkarskiego łączący statystykę Bayesowską (Poisson + Dixon-Coles), ML (CatBoost/Bzzoiro), analizę xG (Understat) oraz LLM (Groq/Llama 3.1). Działa w pełni bezobsługowo: scraping → analiza → generowanie kuponu → rozliczenie → nauka na błędach. Frontend React/Vite (Vercel), backend FastAPI (Cloud Run), DB Neon PostgreSQL.

---

## 🚀 Dla Rekrutera

> **TL;DR** — Produkcyjny, autonomiczny system ML do predykcji piłkarskich: statystyka Bayesowska
> (Poisson + Dixon-Coles) + ensemble + LLM, walidowany **walk-forward out-of-sample na 32 400 meczach**.
> Pełny cykl bez człowieka: scraping → predykcja → kupon → rozliczenie → nauka na błędach.

**🔗 Live demo:** [bot-opal-nu.vercel.app](https://bot-opal-nu.vercel.app)  ·  **API:** FastAPI @ Google Cloud Run  ·  **DB:** Neon PostgreSQL

### Dlaczego warto zerknąć
- 🧪 **1346 testów** pytest + CI (lint · security · coverage gate) + regression gate na broad-except — jakość *wymuszana*, nie deklarowana.
- 📊 **Walidacja naukowa, nie marketing** — walk-forward no-lookahead, A/B wariantów modelu, kalibracja per-pasmo. Dixon-Coles **51.8%** out-of-sample; sufit rynku świadomie zmierzony (4 eksperymenty, 3 odrzucone jako ślepe uliczki — decyzje oparte o dane).
- 🤖 **Pełna autonomia** — dzienny pipeline (Windows Task Scheduler + Google Cloud Scheduler), PC-niezależny; predykcja, rozliczenie i RAG-feedback bez interwencji.
- 🔒 **Rygor produkcyjny** — OWASP API hardening (live), JWT multi-user, RODO, DevSecOps w CI (bandit · gitleaks · pip-audit), rollouty za flagami (default-OFF, walidowane przed flipem).
- 🧩 **Architektura** — multi-source scraping z cross-walidacją (4 źródła), graceful degradation, idempotentne writery, dekompozycja god-modułów.

Stos technik zwięźle:

| Obszar | Implementacja |
|--------|--------------|
| **Autonomous Agents** | Scheduler Draft→Final, Evening Agent (23:00), Operator Agent |
| **RAG Feedback Loop** | Groq analizuje przegrane kupony → wektory → kontekst następnej predykcji |
| **Feature Engineering** | Poisson + xG (atak×obrona rywala) + forma H/A + zmęczenie/rotacja + kontuzje (dwustronne) + sędzia |
| **Bayesian Statistics** | Isotonic kalibracja + renorm 1X2, ensemble Poisson+ML (wagi per-liga), CLV tracking |
| **Advanced Scraping** | Playwright (Superbet, FlashScore, STS), requests (Understat, Bzzoiro, API-Football) |
| **Full-Stack** | FastAPI REST (Cloud Run) + React/Vite SPA (Vercel) + Neon PostgreSQL + multi-user (JWT) |
| **Quality** | 1346 testów pytest, regression gate na broad-except, CI (lint/security/coverage) + Docker health + daily DB backup (Neon pg_dump) |

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
tests/             # 1346 testów pytest
scripts/           # preflight, backup_db, visualize_brain, run_operator.bat
data/              # footstats_backtest.db, model_calibration.json
cache/             # api_football/, understat_xg/, flashscore/, kursy/
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
pytest tests/ -v                          # 1346 testów
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
| **M1** | 55% overall | 🔄 W toku — model offline zwalidowany (Dixon-Coles 51.8% A/B, kalibracja monotoniczna 65%+ = 68%); droga = selekcja high-conf + zbieranie świeżych settled |
| **Offline (walk-forward)** | — | ✅ DC 51.8% > baseline 50.3% > poisson 48.8%; w prod od 06-19 (`USE_DIXON_COLES`) + reweight ku rynkowi 30/70 live (`ENSEMBLE_MARKET_WEIGHT=0.70`) |
| **Data collection** | — | ✅ System paper-trading PC-niezależny (Cloud Scheduler draft 07:30 + settle) → świeże dane walidacyjne bez PC |
| **M2** | 60% overall | Bayesian ensemble + value filter |
| **M3** | 65% selected | Full xG + stop-loss + CLV gate |
| **M4** | 70% selected | 3-miesięczny track record |

---

## Licencja

All Rights Reserved — kod udostępniony do przeglądu portfolio/CV, bez prawa kopiowania,
redystrybucji ani użycia w innych projektach. Szczegóły: [LICENSE](LICENSE).
