# FootStats — Project Status Report

**Last Updated:** 2026-05-22  
**Current Version:** v3.4-stable  
**Build Status:** ✅ Passing (99 source modules, 45 test files, 6299 LOC tests)  
**System State:** Fully Autonomous Production Ready

---

## ✅ RECENT MILESTONES (Completed)

### v3.4 — Poisson Model Auto-Calibration
- `lambda_optimizer.py`: Walk-forward kalibracja na 200 meczach.
- Safety Rail [0.85–1.15], `data/model_calibration.json`.
- `poisson.py` integracja z graceful fallback.

### Operator Agent (2026-05-21)
- `python -m footstats.operator_agent` — preflight, smoke API (coupon wizard), pipeline, review.
- Konto docelowe: `OPERATOR_ADMIN_USERNAME=Admin_JG` (`resolve_admin_user_id`).
- Preview Kreator: dynamiczny user, widoczny CTA kroku 1.

### Phase 4 hygiene (2026-05-21)
- P4.1 Version sync → v3.4-stable w config.py i CLAUDE.md.
- P4.2 SQLite context managers w referee_db.py i dashboard.py.
- P4.6 częściowy cleanup importów (cli, data_fetcher, form).
- P4.7 martwe zależności Postgres usunięte z requirements.txt.

### Architectural Refactor & Cleanup
- Standardized Project Structure, Source Management.

### AI & Automation
- Ultra-Skeptical AI Engine, RAG Lessons Learned, Autonomous Scheduler.

### Data & Intelligence
- Superbet API (1400+ markets), BetBuilder, Referee DB.

---

## PROJECT HEALTH METRICS

| Metric | Status | Value |
|--------|--------|-------|
| **Syntax** | ✅ Clean | 99/99 .py files parse OK |
| **Tests** | ✅ Solid | 45 test files, 6299 LOC |
| **AI Accuracy** | ✅ Stable | ~75% on 75%+ confidence |
| **Automation** | ✅ Full | Zero-touch daily loop |
| **API Cache** | ✅ Wired | response_cache na 5 endpointach |
| **DB** | ✅ OK | backtest.db 1.1MB, footstats.db 256KB |
| **Cache dir** | ✅ OK | 2 pliki, 6.3MB |

---

## KNOWN ISSUES (2026-05-22 audit)

| Issue | Severity | Details |
|-------|----------|---------|
| 223x `except Exception` | 🔴 High | Top: sts(16), superbet(15), base_playwright(14), daily_agent(13), analyzer(13) |
| `_RESPONSE_CACHE` unbounded | 🔴 High | Brak max_size/eviction → memory leak przy dlugim uptime API |
| Duplikat `from langfuse import Langfuse` | 🟠 Med | analyzer.py linia 17 i 25 — podwójny import |
| `asyncio.get_event_loop()` deprecated | 🟠 Med | async_utils.py — Python 3.12+ deprecation warning |
| ~70x potentially unused imports | 🟠 Med | fatigue.py, classifier.py + reszta |
| `tests/scratch` plik w repo | 🟡 Low | Stary skrypt debug, do usunięcia |
| `brain_graph.html` duplikat w root | 🟡 Low | Kopia z assets/ — root do usunięcia |
| `validation_errors.csv` duplikat w root | 🟡 Low | Kopia z data/ — root do usunięcia |
| `data/lf_sig.txt` / `lf_ver.txt` | 🟡 Low | Langfuse SDK garbage dump, do usunięcia |
| `data/env_wzor.txt` | 🟡 Low | Przestarzały wzorzec .env (jest .env.example) |
| `data/.fuse_hidden*` artefakty | 🟡 Low | FUSE mount artefakty (2x 32KB), nieszkodliwe |
| `node_modules` 3.1GB | 🟡 Info | GUI node_modules (gitignored, ale zajmuje dysk) |
| `gui/counter.ts` / `typescript.svg` / `vite.svg` | 🟡 Low | Scaffolding pliki Vite, nieużywane |

---

## CURRENT FOCUS (Phase 4: Maintenance & Hygiene)

- **P4.3** Exception Handling: top 5 plikow (223 bare excepts) → specific exceptions + logging
- **P4.5** Root Cleanup: brain_graph.html, validation_errors.csv, tests/scratch, lf_*.txt
- **P4.6** Unused imports: fatigue.py, classifier.py
- **P4.8** response_cache.py: dodac MAX_ENTRIES + LRU eviction
- **P4.9** analyzer.py: usunac duplikat import langfuse
- **P4.10** async_utils.py: migracja z get_event_loop() na get_running_loop()

---

## DEPLOYMENT LOGS
- **Daily Agent**: Task Scheduler, stable.
- **Dashboard**: Streamlit live.
- **API**: 17 endpoints, response_cache wired on 5.
- **Pipeline**: run_daily.bat → backup → draft-wait-final → settlement.
