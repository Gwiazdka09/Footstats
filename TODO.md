# FootStats TODO — Updated 2026-05-29

## Completed Phases (Archive)

### Phase 1–9: ALL COMPLETE ✅
### Phase 10.0–10.1, 10.3: COMPLETE ✅

---

## KRYTYCZNE BUGI (P0) — natychmiastowe

### BUG-1: Ten sam kupon na Telegramie od kilku dni ✅
- [x] Zbadać filtr daty w quick_picks.py — lookback 2h wstecz usunięty (teraz tylko `teraz <= dm`)
- [x] Dodać deduplication kuponów przed wysyłką — hash SHA256 w data/telegram_dedup.json

### BUG-2: Brak logowania do /preview (Cloud Run) — częściowo ✅
- [x] Root cause: FOOTSTATS_USER + FOOTSTATS_PASSWORD_HASH nie ustawione na Cloud Run → seed_admin_user() pomija
- [x] Kod: warning log gdy brak env vars (migrations.py)
- [x] Kod: /health rozszerzony o auth.ok + liczba aktywnych userów
- [ ] Deployment: ustawić FOOTSTATS_USER + FOOTSTATS_PASSWORD_HASH w Cloud Run env vars

---

## Phase 10: CODE QUALITY & ACCURACY (aktywna)

### 10.2: Broad Except Cleanup (P2) — COMPLETE ✅
- [x] Wszystkie 48 cichych `except Exception` naprawione (zawężone lub # noqa z uzasadnieniem)
- [x] poisson.py SyntaxError po injekcie logger naprawiony
- [x] test_broad_except_audit: 79 passed

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
