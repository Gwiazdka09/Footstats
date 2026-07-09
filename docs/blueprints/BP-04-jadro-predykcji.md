# BP-04 — Jądro predykcji: money/math fixes (deep-dive 2026-07-09)

## KONTEKST
Deep-dive audyt jądra predykcji (sekcja „Deep-dive 2026-07-09" w `docs/audits/AUDIT_2026-07-07.md`) znalazł błędy w ścieżce money/selekcji: filtr value liczy EV złym kursem (D1), Under 2.5 dostaje 100% przy braku danych (D2), settlement może podwójnie kredytować (D3), plus poprawki matematyczne (D4-D8). To są zmiany WPŁYWAJĄCE NA SELEKCJĘ I PIENIĄDZE.

## ⛔ KIEDY WYKONYWAĆ
**PO POWROCIE WŁAŚCICIELA (≥19.07) i PO jego decyzji.** Faza pasywnej walidacji M1 (zbieranie settled do progów 20/88) wymaga NIEZMIENIONEJ selekcji — fix D1/D2/D4 zmienia, które typy przechodzą, co zaciemnia porównanie z baseline (117 settled, 49.6%). Wyjątek dopuszczalny od zaraz: **T3 (settlement guard)** — nie zmienia selekcji, tylko chroni przed podwójnym kredytem.

## INWARIANTY
- Zero zmian λ/modelu Poissona poza opisanymi (D5/D8 tylko po decyzji — wpływają na backtest baseline 51.8%).
- Testy: SQLite `tmp_path`/mocki, nigdy prod Neon.
- Każdy fix z testem regresji odtwarzającym błąd (RED przed fixem).
- Nie „naprawiaj przy okazji" — jeden task = jeden commit.

## ZADANIA

### T1 — D1: kurs per-typ w `filter_value_bets` [HIGH, zmienia selekcję]
- **Pliki:** `src/footstats/core/value_bet.py`; test `tests/test_value_bet*.py` (Glob).
- **Test-first:** `test_get_best_odds_uzywa_kursu_typu` — kandydat tip="1", odds={home:1.5, away:6.0} → EV liczone z 1.5 (teraz: 6.0 → RED).
- **Implementacja:** mapa tip→klucz jak `system_paper._ODDS_KEY` (wyciągnij do wspólnego modułu, np. `core/markets.py`, żeby nie duplikować); `_get_best_odds(k)` → `_odds_dla_typu(k)`; kandydat bez typu/kursu → zachowaj obecne „keep" (bez odds nie liczymy EV).
- **Akceptacja:** testy green; log porównawczy: ile kandydatów przechodzi filtr przed/po (spodziewany SPADEK — odnotuj liczbę w PR).

### T2 — D2: Under 2.5 bez o25 = None, nie 100% [HIGH, zmienia selekcję]
- **Pliki:** `src/footstats/core/system_paper.py:51-59`; test `tests/test_system_paper*.py`.
- **Test-first:** `test_najlepszy_typ_brak_o25_nie_wybiera_under` — w bez "o25", odds z under_2_5=1.8 → najlepszy_typ NIE zwraca Under (teraz zwraca z prob=100 → RED).
- **Implementacja:** `_prob_dla_typu`: `o25 = w.get("o25")`; "Over 2.5"/"Under 2.5" → `None` gdy `o25 is None`.
- **Akceptacja:** testy green + istniejące testy system_paper bez regresu.

### T3 — D3: settlement compare-and-swap [HIGH, NIE zmienia selekcji — można od razu]
- **Pliki:** `src/footstats/core/coupon_settlement.py:359-394`; test `tests/test_coupon_settlement*.py`.
- **Test-first:** `test_podwojne_settle_kredytuje_raz` — kupon WON rozliczony dwukrotnie (symulacja drugiego przebiegu) → bankroll +payout tylko raz.
- **Implementacja:** `UPDATE coupons SET status=? ... WHERE id=? AND status='ACTIVE'`; kredyt bankrollu TYLKO gdy `cur.rowcount == 1`. Dodatkowo D7: `else: log.warning("WON bez bankroll_state uid=%s", owner_uid)`.
- **Akceptacja:** test green; pełny suite green.

### T4 — D4: EV netto w filtrze value [decyzja usera: próg]
- **Pliki:** `value_bet.py`; `kelly.ev_netto` jako źródło wzoru.
- **Decyzja przed startem:** (a) `calculate_ev` → netto (podatek 12%) z progiem 3% netto [zalecane], (b) zostawić brutto, podnieść próg do ~14%. Wpisz decyzję tutaj.
- **Test-first:** `test_filter_value_bets_odrzuca_netto_ujemne` — p=0.5, kurs 2.10 (brutto +5%, netto -7.6%) → odrzucone.

### T5 — D5: Over2.5 bez normalizacji sumą 1X2 [zmienia predykcje finałów]
- **Pliki:** `poisson.py:229-255`; testy `tests/test_core_pure*` (poisson).
- **Test-first:** `test_over25_final_bez_znieksztalcenia` — jest_single=True: over25 identyczne jak dla tego samego λ bez boostu (teraz niższe → RED).
- **Implementacja:** `over25 = min(over25_raw, 1.0)` (macierz już znormalizowana); jeśli D8 → decyzja „licz z finalnej macierzy" — zrób razem.
- **UWAGA:** przelicz walk-forward po zmianie (`/backtest`) — baseline 51.8% może drgnąć; odnotuj.

### T6 — D6: `_dodaj_kelly` — błąd → 0.0 + log; None-check pewnosc_pct
- **Pliki:** `core/daily_phases.py:485-505`; test `tests/test_daily_phases*.py`.
- **Test-first:** wyjątek z kelly_stake (mock) → `kelly_stake == 0.0` i warning w caplog (teraz 1.0 → RED); `pewnosc_pct=0` → nie zamienia się w 50.
- **Implementacja:** wzorzec None-check z `value_bet.py:44-51`.

### T7 — D10-D12 drobnica [LOW, bezpieczne od razu]
- `ensemble.py:51-52` fallback 0.45/0.55 → `_DEFAULT_WEIGHTS`; `kelly_kupon`/`dynamic_stake` → docstring DEPRECATED (albo usuń + testy); `poisson.py:206` log.debug przy xG cache-miss.

### T8 — D9: weryfikacja `use_calibration` w wf_harness [analiza, nie kod]
- Sprawdź jak fitowana `load_calibration()` (lambda_optimizer): na jakim oknie danych? Jeśli pokrywa okno replay → policz wf z `use_calibration=False`, porównaj z 51.8%, zdecyduj czy baseline do korekty. Raport, zero zmian kodu bez decyzji.

## DEFINITION OF DONE
Po T1-T6: pełny suite green + **świeży walk-forward** (`scripts/run_walkforward_prod.py`) z zapisanym wynikiem przed/po w PR — to zmiany jądra, offline baseline musi być przeliczony świadomie. Pozycje D1-D12 odhaczone w audycie.

## ESKALACJA
T1/T2/T4/T5 zmieniają selekcję → wykonanie tylko po decyzji usera i najlepiej po domknięciu progów walidacji M1 (n≥88) albo świadomie „reset baseline". Wątpliwość → STOP.
