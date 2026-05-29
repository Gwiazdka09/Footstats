# FootStats TODO — Updated 2026-05-29

## Completed Phases (Archive)

### Phase 1–9: ALL COMPLETE ✅
### Phase 10.0–10.1, 10.3: COMPLETE ✅

---

## KRYTYCZNE BUGI (P0) — natychmiastowe

### BUG-1: Ten sam kupon na Telegramie od kilku dni ✅
- [x] Zbadać filtr daty w quick_picks.py — lookback 2h wstecz usunięty (teraz tylko `teraz <= dm`)
- [x] Dodać deduplication kuponów przed wysyłką — hash SHA256 w data/telegram_dedup.json

### BUG-2: Brak logowania do /preview (Cloud Run)
- [ ] Zbadać endpoint /preview — auth broken na produkcji
- [ ] Sprawdzić seed_admin / env vars na Cloud Run
- [ ] Naprawić login i zweryfikować

---

## Phase 10: CODE QUALITY & ACCURACY (aktywna)

### 10.2: Broad Except Cleanup (P2) — IN PROGRESS
- [x] sts.py — 3x zamienione
- [x] superbet.py — częściowo
- [x] daily_agent.py — 5x zawężone (13→8)
- [x] cli.py — 10x zamienione/noqa
- [ ] **~190x remaining** w całym projekcie (pozostałe pliki)

### 10.4: Large File Refactoring (P3)
- [x] daily_agent.py — _build_parser() wydzielony
- [ ] analyzer.py (1393 LOC) — wydzielić: prompts, scoring, output formatting
- [ ] superbet.py (1128 LOC) — wydzielić: auth, scraping, parsing
- [ ] cli.py (1112 LOC) — wydzielić komendy do submodułów

### 10.6: Timeout Audit (P1) — COMPLETE ✅
- [x] AST scan: 0 requests calls bez timeout — wszystkie pliki już miały timeout

### 10.7: Subprocess Cleanup (P2) — COMPLETE ✅
- [x] Audit: wszystkie Popen to fire-and-forget z właściwym stdio — no cleanup needed

### 10.8: Asyncio Modernization (P3) — COMPLETE ✅
- [x] async_utils.py:56 — get_event_loop() → new_event_loop() (deprecated fallback usunięty)

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
