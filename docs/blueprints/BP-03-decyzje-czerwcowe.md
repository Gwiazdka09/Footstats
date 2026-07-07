# BP-03 — Otwarte HIGH-e z audytu 06-27 (wymagają decyzji usera)

## KONTEKST
Audyt 2026-06-27 naprawił większość znalezisk (fazy 0-3 + C1/C2, commity f0e0ec12f…61b014157). Zostało 5 pozycji **money/prod-krytycznych** świadomie odłożonych na decyzję usera. Audyt 07-07 potwierdził: wciąż otwarte. Ten blueprint = opcje + rekomendacja + gotowe taski TDD per decyzja. **Coder wykonuje task DOPIERO po wpisanej decyzji.**

## INWARIANTY
- Money-path (`daily_io`, bankroll, settlement): każda zmiana za testem regresji NAJPIERW; zero zmian „przy okazji".
- Zachowanie backtestu offline niezmienione (walk-forward 51.8% = baseline porównań).
- Prod Neon: testy nigdy nie piszą.

## DECYZJE

### D1 — `af_budget` RMW bez locka (`utils/logging.py:330` + `utils/cache.py`)
**Problem:** read-modify-write `af_budget.json` bez synchronizacji; API (Cloud Run, multi-instance) + job równolegle → zgubione inkrementy → przekroczenie quoty API-Football (429 → dziury w danych).
**Opcje:** (a) `filelock` (cross-proces, nowa zależność — wymaga `pip install`, ASK user); (b) `threading.Lock` (tylko in-proc — NIE rozwiązuje multi-instance); (c) licznik w Neon (atomowy `UPDATE ... RETURNING`, cross-instance, +1 zapytanie na call).
**Rekomendacja:** (c) — jedyna poprawna przy Cloud Run multi-instance; (a) nie działa między kontenerami.
**Task po decyzji (c):** test-first `test_budget_use_atomowy_wspolbiezny` (dwa „procesy" symulowane → suma się zgadza); tabela `af_budget` w Neon (migracja); `bezpieczny_budget_use` → UPDATE atomowy; fallback JSON gdy brak DB (dev offline). Pliki: `utils/logging.py`, `db/migrations.py`, `tests/test_api_football_budget.py`.

### D2 — `daily_io` DRAFT nie idempotentny (double `process_bet`)
**Problem:** powtórka fazy (retry joba / double-trigger Schedulera) → podwójny zapis betu = MONEY.
**Opcje:** (a) dedup po kluczu naturalnym (match_date+teams+tip+faza) przed insertem; (b) unikalny constraint w DB + `ON CONFLICT DO NOTHING`; (c) marker fazy „już przetworzona" (data+faza w tabeli runs).
**Rekomendacja:** (b) — DB wymusza, kod nie musi pamiętać; (c) jako uzupełnienie dla całych faz.
**Task po decyzji:** test-first `test_double_process_bet_jeden_zapis` (dwukrotne wywołanie → 1 wiersz); migracja unique index; obsługa konfliktu z logiem PL. Pliki: `daily_io` (Grep `process_bet`), `db/migrations.py`, testy.

### D3 — `_wyciagnij_json` cicho fabrykuje `{"typ": "brak"}` (`ai/analyzer_helpers.py:387`)
**Problem:** nieparsowalna odpowiedź LLM → sentinel wygląda jak prawdziwa odpowiedź; pipeline nie wie że LLM zawiódł. Po odsunięciu LLM od picków (07-06) waga spadła — ale analizy/podsumowania dalej przez to przechodzą.
**Opcje:** (a) zostaw sentinel + dodaj log.warning i licznik metryki (minimalna zmiana); (b) raise `BladParsowaniaLLM` + explicit fallback u callerów (zmiana zachowania pipeline).
**Rekomendacja:** (a) teraz (LLM już nie wybiera picków, ryzyko małe), (b) przy najbliższym refactorze analyzera.
**Task po decyzji (a):** test-first `test_wyciagnij_json_smieci_loguje_warning` (caplog); dodaj log + licznik do istniejącego mechanizmu metryk. Pliki: `ai/analyzer_helpers.py`, testy analyzer_helpers.

### D4 — `system_paper` idempotencja nieatomowa
**Problem:** check-then-insert bez transakcji → duplikaty przy wyścigu.
**Rekomendacja:** jak D2(b) — unique constraint + upsert.
**Task po decyzji:** analogiczny do D2.

### D5 — double auto-trainer spawn bez guarda
**Problem:** dwa procesy auto-trainera równolegle (double-trigger) → wyścig na plikach modelu.
**Opcje:** (a) plik-lock/PID marker; (b) marker w DB z TTL.
**Rekomendacja:** (b) spójnie z D1(c) jeśli wybrane.
**Task po decyzji:** test-first `test_drugi_spawn_trainera_odmawia`; guard na wejściu traina. Pliki: Grep `auto_trainer` w src/.

### D6 (nowe, audyt 07-07 H2) — dane SQLite na prod API
Patrz **BP-01/T7** — decyzja architektoniczna (GCS-pull vs Neon) dotyka też parquet P2 z TODO. Rekomendacja: GCS-pull przy starcie (jeden mechanizm dla parquet + SQLite).

## DEFINITION OF DONE
Każda decyzja: wpis w tym pliku (`DECYZJA: <opcja> — <data>`), task wykonany TDD, pozycja odhaczona w `docs/audits/AUDIT_2026-07-07.md`, pełny suite green.

## ESKALACJA
Wszystko tutaj = money/prod. Wątpliwość → STOP + pytanie do usera. Żaden task nie startuje bez wpisanej decyzji.
