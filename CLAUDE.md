# FootStats v3.4-stable
Lang: PL. Context: Soccer predictions (Poisson + RAG + LLM).

## Commands
- Run: `python -m footstats.<module>`
- Test: `pytest tests/ -v`
- API: Port 8000. Dashboard: `/preview`
- UI: `streamlit run src/footstats/dashboard.py`
- Brain: `python scripts/visualize_brain.py`

## Rules
- Autonomy: Python, pytest, git, files, subagents.
- ASK: `pip install`, `.env` changes, destructive ops (reset/force push/rm).
- Style: PEP8, Type hints, PL comments/logs.

## Subagent team (.claude/agents/)
Ja = orchestrator. Workflow feature: subagent-driven-development (planner→coder→reviewer, 2-stage review, branch+TDD+commit per task).
- `footstats-planner` (opus) — spec→plan TDD, read-only.
- `footstats-coder` (sonnet) — implementer 1 task, TDD, commit.
- `footstats-reviewer` (opus) — spec + quality review.
- `footstats-data-guard` (sonnet) — guard: prod Neon writes / Telegram spam / lookahead.
- `footstats-model-analyst` (opus) — walk-forward, kalibracja, A/B, λ (Poisson/Dixon-Coles).
- `footstats-explorer` (haiku) — read-only lokalizator kodu (tani, oszczędza kontekst).
- `footstats-debugger` (opus) — root-cause hunt (np. live≪offline: Groq/settlement).
- `footstats-scribe` (sonnet) — kronikarz sesji: TODO→CHANGELOG, STATUS refresh, commit docs.
- `footstats-gui-verifier` (sonnet) — screenshot Playwright po zmianie GUI (desktop+mobile), checklist design-system.
- `footstats-test-medic` (sonnet) — pytest triage: naprawia testy (nie kod prod), zgłasza bugi prod.
- `footstats-calibration-reporter` (sonnet) — co 2-3 dni: calibration_monitor + flip-advisor, licznik settled → progi 20/88.
- `footstats-ops-monitor` (sonnet) — daily: Cloud Run Jobs/Scheduler health (gcloud read-only), GREEN/AMBER/RED.
- `footstats-postmatch-analyst` (sonnet) — po zakończonych meczach: rozlicza (też kupony papierowe), tworzy wnioski pomeczowe, klastruje powtarzalne przyczyny błędów. Analizuje TRAFIONE tak samo jak nietrafione. Domyślnie `--dry`, zapis do prod `ai_feedback` tylko za zgodą.

## Architecture (Pointers)
- Structure: See `PROJECT_STRUCTURE.md`
- Core: `src/footstats/` (AI, Core, Scrapers)
- DB: `data/footstats_backtest.db` (SQLite)
- Pipeline: Cloud Run Jobs (`footstats-final` 11:00 + `footstats-evening` 23:00, Cloud Scheduler). Lokalny `run_daily.bat` wyłączony — patrz `docs/cloud_migration.md`.

## Tech Stack
- Backend: FastAPI, Playwright (Scraping), Groq SDK (Llama 3.1 8B).
- Frontend: Streamlit, vis-network (Brain Graph).
- Logic: Poisson, Kelly Criterion, RAG Feedback Loop.

## Design System (GUI - React/Tailwind v4)
Tokens in `src/footstats/gui/src/index.css` `:root` — reuse these, don't invent new colors.
- Colors: bg `--bg-deep` #0f172a / `--bg-darker` #020617. Accent: indigo `--accent-primary` #818cf8 + pink `--accent-secondary` #f472b6 — ONE accent pairing, no extra colors for emphasis.
- Text: `--text-main` #f8fafc (no pure white), `--text-muted` #94a3b8 for secondary/labels. No pure black/white text anywhere.
- Glass cards: `.glass-card` (blur+border+shadow, radius 16px) — primary container pattern. Prefer whitespace over hard borders/dividers.
- Buttons: `.btn-primary` (gradient accent) for primary actions; `.btn-see-all` style (subtle bg, muted text) for secondary.
- Type scale: keep limited — `h1/h2/h3`/`.brand` use Outfit font, body Inter. Differentiate hierarchy via font-weight/color (text-main vs text-muted), not extra sizes.
- Icons (lucide-react): standardize on 16px (inline/labels) or 20px (nav/headers) — avoid one-off 13/14/15/18px sizes.
- Spacing/radius: glass-card radius 16px, btn radius 8px — reuse, don't add new radii.

### Workflow rule
After ANY GUI layout/style change: verify visually via Playwright MCP screenshot (relevant view, desktop + mobile if layout-affecting) before reporting done.
