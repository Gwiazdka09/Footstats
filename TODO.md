# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-07  
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

### ~~TD1~~ ~~TD2~~ ~~TD5~~ ~~TD6~~ ~~TD7~~ ~~TD8~~ — ✅ DONE

---

## ⚪ FAZA 15: NOWE FEATURE'Y (po M1=55%)

### 15.1: Stop-loss mechanizm
- [ ] Auto-pause gdy strata > 20% bankrollu w ciągu 7 dni
- [ ] Telegram alert + status `PAUSED` + wznowienie przez dashboard
- **Effort:** 3–4h

### 15.2: CLV tracking (Closing Line Value)
- [ ] Porównaj kurs obstawiania vs kurs zamknięcia
- [ ] Kolumny w tabeli `predictions` już przygotowane
- **Effort:** 3–5h

### 15.3: Odds comparison — STS/Fortuna/LV BET
- [ ] Playwright login → porównaj kursy, wybierz najwyższy
- **Effort:** 1–2 tygodnie

### 15.4: Dashboard UX v2
- [ ] Filtrowanie po lidze/dacie/typie, accuracy per liga, bankroll chart
- **Effort:** 1–2 dni

### 15.5: Telegram komendy interaktywne
- [ ] `/status`, `/kupon`, `/void <id>`, `/stats`
- **Effort:** 4–6h

### 15.6: Multi-user support
- [ ] Per-user bankroll, risk profile, Telegram chat_id
- **Effort:** 3–5 dni

---

## Fazy ukończone

Phase 1–14: ✅ DONE — szczegóły: `git log`, `docs/archive/`
