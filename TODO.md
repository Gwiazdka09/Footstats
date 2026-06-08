# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-08  
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

### TD9: Commit + push (80 uncommitted changes)
- [ ] `git add -A && git commit -m "v3.4: fix truncation, restore 30 files, gitignore update"`
- [ ] `git push origin main`
- **Priorytet:** 🔴 P1 — ryzyko utraty pracy

### TD10: Zbadać przyczynę powtarzającej się truncacji plików
- [ ] 06-07: 26 plików truncated + 4 z null bytes (kolejny raz!)
- [ ] Prawdopodobna przyczyna: Claude Code edycja dużych plików lub dysk/antywirus
- [ ] Rozwiązanie: backup pre-edit hook w `.claude/hooks/`
- **Priorytet:** 🔴 P1

### TD11: __init__.py version desync
- [ ] `src/footstats/__init__.py` ma `__version__ = "2.7"` — powinno być `"3.4"`
- **Priorytet:** 🔴 P1 — 1 minuta fix

### TD12: subprocess.run bez timeout w daily_agent_scheduler.py
- [ ] Linia 23 i 67: `subprocess.run(...)` bez `timeout=`
- [ ] Dodać `timeout=7200` (2h max na fazę draft/final)
- **Priorytet:** 🟡 P2

### TD13: Wyczyść __pycache__ i .fuse_hidden
- [ ] `find . -name __pycache__ -not -path ./.venv/\* -exec rm -rf {} +`
- [ ] `rm .fuse_hidden*`
- [ ] Dodać `DAILY_REPORT_*.md` do .gitignore
- **Priorytet:** ⚪ P4

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

- Przycisk od kreatora kuponów "Analizuj wybrane mecze" powinien być dla wygody poruszać się na dole ekranu po prawej stronie na dole.
- Flagi przy ligach w kreatorze kuponów. 