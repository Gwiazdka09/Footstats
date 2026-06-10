# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-10  
**Wersja:** v3.4-stable  
**Accuracy baseline:** 26.7% (15 live settled, Neon.tech)  
**Cel na koniec lipca:** M1 = 55% win rate

---

## Milestones

| Milestone | Cel | Status | Warunek |
|-----------|-----|--------|---------|
| **M0** | 42% baseline | ✅ Done | 33 kupony SQLite lokalny |
| **M0b** | 26.7% live baseline | ✅ Done | 15 kuponów Neon.tech |
| **M1** | 55% win rate | 🔴 W toku | min. 50 settled + kalibracja |
| **M2** | 60% win rate | ⏸️ | Po M1 — tuning wag ensemble |
| **M3** | 65% selected | ⏸️ | Po M2 — stop-loss + filtrowanie lig |
| **BETA** | Testerzy | ⏸️ | Po M1 — stabilna accuracy |

---

## 🔴 FAZA 16: ACCURACY FIXES (przed betą — teraz)

### ~~16.1~~ — ✅ DONE
- `LIGI_WHITELIST` + `LIGI_BLACKLIST_KEYWORDS` + `LIGA_FILTER_ENABLED=True` w config.py
- `_pre_filtruj_ligi` wywoływana w KROK 1 daily_agent; fix `ImportError: LIGI_BLACKLIST`

### ~~16.2~~ — ✅ DONE
- `PROG_DRAFT=50`, `PROG_DRAFT_FALLBACK=40` w `decision_score.py`; fallback aktywny w main()

### ~~16.3~~ — ✅ DONE
- Kupon #33 (Legia/Ajax-PSV) → VOID w Neon.tech

### 16.4: Kalibracja modelu (po 50 settled)
- [ ] `python -m footstats.core.probability_calibrator`
- [ ] A/B test wag: 50/50 → 60/40 → 70/30 Poisson/Bzzoiro
- [ ] Zapisać `data/model_calibration.json`
- **Effort:** 2–3h | Warunek: min. 50 settled live kuponów

### 16.5: Zbieranie danych (pasywne — 3 tygodnie)
- [ ] Daily agent działa automatycznie (Task Scheduler 08:00 + 11:00 + 23:00)
- [ ] Monitorować logi: `logs/kupon_YYYY-MM-DD.txt`
- [ ] Cel: 50 settled kuponów z filtrowanymi ligami

---

## 🔧 TECH DEBT

### ~~TD3~~ — ✅ DONE
- superbet.py 4x narrowed; pozostałe pliki z listy były już czyste lub justified noqa

### ~~TD4~~ — ✅ DONE
- `daily_agent.py` 1486→1325 LOC: filtry→`core/daily_filters.py`, zapis DB→`core/daily_io.py`
- `analyzer.py` 1175→959 LOC: helpery→`ai/analyzer_helpers.py`

### ~~TD9~~ — ✅ DONE (06-09)
- `git add -A && git commit` — v3.4 na main

### ~~TD10~~ — ✅ DONE (06-09)
- `pre-edit-backup.js` hook → backup .py/.json/.md >5KB do `f:/bot/.backups/` przed każdym Edit/Write
- Zarejestrowany w `.claude/settings.local.json` (projekt-only)

### ~~TD11~~ — ✅ DONE (verified 06-09)
- `src/footstats/__init__.py` → `__version__ = "3.4"` — potwierdzone: plik zawiera "3.4"

### ~~TD12~~ — ✅ DONE (06-09): `timeout=7200` w draft + final subprocess.run
### ~~TD13~~ — ✅ DONE (06-09): __pycache__, .gitignore, archiwum daily reports
### ~~TD14~~ — ✅ DONE (06-09): PROJECT_STATE.md v3.3 → v3.4
### ~~TD15~~ — ✅ DONE (06-09): `atexit.register(_SESSION.close)` w understat_xg.py
### ~~TD16~~ — ✅ DONE (06-10): .fuse_hidden + empty WAL cleaned, brain_graph.html → .gitignore, DAILY_REPORT → archive

### TD17: response_cache sync_wrapper race condition
- [ ] `sync_wrapper` (linia 171) czyta `_RESPONSE_CACHE.get()` bez `_CACHE_LOCK` — race z zapisem
- [ ] Fix: owinąć odczyt w `with _CACHE_LOCK:` (tak jak async_wrapper)
- **Effort:** 5 min | 🟡 P2

### TD18: base.py recursive retry bez limitu
- [ ] `_http_get()` na 429 wywołuje samą siebie — brak max depth → stack overflow przy ciągłym 429
- [ ] Fix: dodać parametr `_retry=0` i `if _retry >= 3: return None`
- **Effort:** 5 min | 🟡 P2

### TD19: cache/ 353MB — brak eviction policy
- [ ] Rozważ max age dla plików cache (np. >7 dni → usuwaj)
- [ ] Lub skrypt `scripts/evict_cache.py` w pipeline
- **Effort:** 30 min | ⚪ P4

### TD20: Uncommitted changes (29 plików)
- [ ] `git add -A && git commit -m "v3.4 daily updates" && git push`
- **Effort:** 2 min | 🔴 P1

### ~~TD1~~ ~~TD2~~ ~~TD5~~ ~~TD6~~ ~~TD7~~ ~~TD8~~ — ✅ DONE

---

## ⚪ FAZA 15: NOWE FEATURE'Y

### ~~15.1~~ — ✅ DONE
- `data/agent_state.json` pause flag; `is_agent_paused`, `set_agent_paused`, `check_and_auto_pause` w bankroll.py
- daily_agent: check na starcie + auto-pause + Telegram `send_stop_loss_alert`
- dashboard: PAUSED status, drawdown metric, Resume/Pause buttons

### ~~15.2~~ — ✅ DONE (było wcześniej)
- `clv_tracker.py` + evening_agent `record_closing_odds` + dashboard CLV section

### 15.3: Odds comparison — STS/Fortuna/LV BET
- [ ] Playwright login → porównaj kursy, wybierz najwyższy
- **Effort:** 1–2 tygodnie | ⏸️ odkładamy

### ~~15.4~~ — ✅ DONE
- Sidebar filtry liga + typ zakładu (multiselect) — `dashboard.py`
- accuracy per liga, bankroll chart, CLV — były wcześniej

### ~~15.5~~ — ✅ DONE
- `telegram_bot.py` — raw HTTP polling, /status /kupon /void /stats /help
- Uruchomienie: `python -m footstats.telegram_bot`

### 15.6: Multi-user support
- [ ] Per-user bankroll, risk profile, Telegram chat_id
- **Effort:** 3–5 dni | ⏸️ po M1

---

## Fazy ukończone

Phase 1–14: ✅ DONE — szczegóły: `git log`, `docs/archive/`

## Pomysły na zmiany od betatesterów

- ~~Przycisk od kreatora kuponów "Analizuj wybrane mecze" powinien być dla wygody poruszać się na dole ekranu po prawej stronie na dole.~~ ✅
- ~~Flagi przy ligach w kreatorze kuponów.~~ ✅ (06-10, App.jsx LEAGUE_FLAGS)
- ~~codzienne proponowane kupony risk low/medium/high~~ ✅ (06-10): `core/risk_proposals.py` + `GET /api/coupons/daily-proposals`, sekcja "Propozycje dnia" w Dashboard
- ~~zakładka najlepsi typerzy~~ ✅ (06-10): migracja #5 (`coupons.shared` + konto "System"), `PATCH /api/coupon/{id}/share`, `GET /api/leaderboard`, `GET /api/leaderboard/{username}/coupons`, tab "Najlepsi typerzy" w App.jsx
  - ~~TODO follow-up: "System" konto generuje propozycje dnia~~ ✅ (06-10): `core/system_coupons.py::generate_system_coupons` + hook w `daily_agent.py` (faza draft) — zapisuje 3 kupony risk_low/medium/high jako shared=TRUE, idempotentne per dzień
