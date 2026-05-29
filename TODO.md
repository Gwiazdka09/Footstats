# FootStats TODO — Updated 2026-05-29

## Completed Phases (Archive)

### Phase 1–9: ALL COMPLETE ✅
### Phase 10.0–10.1, 10.3: COMPLETE ✅

---

## Phase 10: CODE QUALITY & ACCURACY (aktywna)

### 10.2: Broad Except Cleanup (P2) — IN PROGRESS
- [x] sts.py — 3x zamienione
- [x] superbet.py — częściowo
- [x] daily_agent.py — 5x zawężone (13→8)
- [ ] **216x remaining** w całym projekcie
- Top: superbet(15), base_playwright(14), sts(13), analyzer(13), cli(10)

### 10.4: Large File Refactoring (P3)
- [x] daily_agent.py — _build_parser() wydzielony
- [ ] analyzer.py (1393 LOC) — wydzielić: prompts, scoring, output formatting
- [ ] superbet.py (1128 LOC) — wydzielić: auth, scraping, parsing
- [ ] cli.py (1112 LOC) — wydzielić komendy do submodułów

### 10.6: Timeout Audit (P1) — NEW
- [ ] **17x requests.get/post bez timeout** — dodać timeout=15
- Pliki: coupon_settlement, source_manager, api_football, lineup_scraper, bzzoiro, enriched, results_updater

### 10.7: Subprocess Cleanup (P2) — NEW
- [ ] **5x Popen bez proper cleanup** — backtest, post_match_analyzer, cli, evening_agent, daily_agent

### 10.8: Asyncio Modernization (P3)
- [ ] async_utils.py — zamienić get_event_loop() na asyncio.run()

### 10.9: Commit & Push (P2)
- [ ] **36 uncommitted changes** — przejrzeć i commitować

---

## Milestones

| Milestone | Accuracy | Status |
|-----------|----------|--------|
| **M0** | ~42% overall | ✅ Current (baseline) |
| **M1** | 55% overall | 🔄 In progress — calibration + filters |
| **M2** | 60% overall | Bayesian Poisson + ensemble + value filter |
| **M3** | 65% selected | xG + feature engineering + stop-loss |
| **M4** | 70% selected | Full optimization + CLV + 3mo track record |

---

## Blockers
- **Accuracy 42%** — poniżej M1 target, wymaga pracy nad kalibracją
