# FootStats TODO — Czerwiec / Lipiec 2026

**Ostatnia aktualizacja:** 2026-06-14
**Wersja:** v3.4-stable
**Accuracy baseline:** 33% (12/35 live settled, Neon.tech)
**Cel na koniec lipca:** M1 = 55% win rate

> Historia ukończonych zadań: `git log` (commity TD/16.x/15.x mają opisowe nazwy)

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

## 🔴 FAZA 16: ACCURACY FIXES (przed betą)

### 16.3: Draw bias — model faworyzuje remisy
- [x] Root cause: FINAL_REMIS_BOOST overshoot dla niskich lambd
- [x] Fix: sufit p_remis=40% w poisson.py
- [ ] A/B: porównaj trafność remisów vs 1/2 w ostatnich 35 settled (warunek: 50 settled)
- **Effort:** A/B po 16.4 | 🔴 P1

### 16.4: Kalibracja modelu (po 50 settled)
- [ ] `python -m footstats.core.probability_calibrator`
- [ ] A/B test wag: 50/50 → 60/40 → 70/30 Poisson/Bzzoiro
- [ ] Zapisać `data/model_calibration.json`
- **Effort:** 2–3h | Warunek: min. 50 settled live kuponów

### 16.5: Zbieranie danych (pasywne — 3 tygodnie)
- [ ] Daily agent działa automatycznie (Task Scheduler 08:00 + 11:00 + 23:00)
- [ ] Monitorować logi: `logs/kupon_YYYY-MM-DD.txt`
- [ ] Cel: 50 settled kuponów z filtrowanymi ligami
- [x] match_stats (timeline zdarzeń) zapisywane do `predictions` (06-12)

---

## 🟡 TECHNICZNE

### TD-31: Testy core modules — ✅ DONE (06-14)
- [x] Priorytetowe: coupon_settlement, bankroll, kelly, value_bet, quick_picks
- [x] bankroll: nowy `tests/test_bankroll.py` (8 testów, sqlite fixture)
- [x] coupon_settlement/kelly/value_bet/quick_picks: już pokryte (60 testów)

---

## ⏸️ NA PÓŹNIEJ

### 15.6: Multi-user support
- [ ] Per-user bankroll, risk profile, Telegram chat_id
- **Effort:** 3–5 dni | ⏸️ po M1

## Licencja
- [x] LICENSE zmienione MIT → All Rights Reserved + klauzula portfolio/CV (06-12)
- [ ] Konsultacja z prawnikiem przed komercyjnym udostępnieniem (ToS bukmacherów + ochrona baz danych)

---

## 💡 Pomysły od betatesterów

### Rozszerzenie oferty zakładów (rożne/kartki)
- STS Bet Builder: rożne, kartki, rzut karny, czerwona kartka
- zawodtyper.pl: dane per-kategoria, zawodtyper_referees: avg_yellow/avg_red per sędzia
- Pomysł: `fetch_team_corners`/`fetch_team_cards` + Poisson → nowe tipy
- **Effort:** 2-3 dni | po M1
### Przycisk dla admina — ✅ DONE (06-14)
- [x] nowa zakładka "Panel" (tylko dla adm): "Sprawdź wyniki meczów" (POST /coupons/settle) + "Zarządzaj użytkownikami" (GET/POST/DELETE /admin/users)
### Zmiana nazwy konta — nieaktualne
- [x] system już używa `username` (nie email) do logowania/wyświetlania — brak akcji
### Błąd w przeglondarce na telefonie — ✅ DONE (06-14)
- [x] mobile topbar (logo + ☰) + fullscreen drawer nav (X zamyka), sidebar desktop ukryty <1024px
### P1!
Please fix the following security issue:

<issue>
Detected a Generic API Key, potentially exposing access to various services and sensitive operations.

Exposed secrets can allow attackers to access sensitive systems or data, potentially leading to unauthorized actions, data breaches, or financial loss.

A secret value, such as an API key or password, is stored directly in the repository and committed to version control, making it publicly or internally accessible.
</issue>

<locations>
.vexp/manifest.json:4
.vexp/manifest.json:26
.vexp/manifest.json:76
.vexp/manifest.json:108
.vexp/manifest.json:109
</locations>

<fix>
If the API key isn’t sensitive, you can ignore this. Otherwise, remove it from the repository and provide it through the environment, or better yet, use a secrets manager to inject it at runtime. Then regenerate any compromised secrets.
</fix>

<fix_impact>
null
</fix_impact>

Keep the changes minimal - only make the necessary code changes to fix the security issue.
After making the code changes to fix the security issue, tell me about the non-code changes I need to make.

Please fix the following security issue:

<issue>
Command injection from dynamic arguments in Python subprocess call

Command injection lets attackers execute arbitrary OS commands, read or modify data, pivot laterally, and fully compromise the host process.

Subprocess commands are constructed from variables and may invoke a shell, allowing untrusted input to influence executed command lines.
</issue>

<locations>
src/footstats/ai/post_match_analyzer.py:171
src/footstats/cli.py:1094-1097
src/footstats/core/backtest.py:186-190
src/footstats/daily_agent_scheduler.py:23-37
src/footstats/daily_agent_scheduler.py:68-82
src/footstats/evening_agent.py:312-317
src/footstats/operator/runner.py:64-71
src/footstats/operator/workflow.py:120-126
</locations>

<fix>
Avoid shell=True. Execute a fixed executable with an argument list using subprocess.run(..., shell=False, check=True). Pass untrusted data only as separate arguments. Validate or whitelist allowed values. If a shell is unavoidable, carefully quote with shlex.quote().
</fix>

<fix_impact>
If code relied on shell features (globbing, pipes, redirects, expansions), replacing shell=True with direct argument lists will change behavior and require explicit implementations.
</fix_impact>

Keep the changes minimal - only make the necessary code changes to fix the security issue.

Please fix the following security issue:

<issue>
SQL injection from string concatenation in raw SQL queries in SQLAlchemy

SQL injection could expose or modify data, run unauthorized queries, and bypass authorization, compromising database integrity and confidentiality.

Untrusted values are interpolated into SQL strings and executed via Connection.execute, allowing crafted input to alter the SQL structure.
</issue>

<locations>
src/footstats/ai/rag.py:215-218
</locations>

<fix>
Use parameterized queries with sqlalchemy.text() and named parameters. Example: stmt = text('SELECT * FROM users WHERE id=:id'); conn.execute(stmt, {'id': user_id}). For complex queries, use SQL Expression Language or the ORM. Never use +, %, format, or f-strings to build SQL.
</fix>

<fix_impact>
null
</fix_impact>

Keep the changes minimal - only make the necessary code changes to fix the security issue.

