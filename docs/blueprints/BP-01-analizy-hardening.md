# BP-01 — Hardening zakładki „Analizy meczowe"

## KONTEKST
Zakładka „Analizy" (commity `a84b79e05`→`629de7042`, 07-06/07) agreguje kartę meczu (model 1X2/O-U/BTTS + gole/mecz z `team_stats` + goal_share kontuzji) i generuje analizę LLM on-demand z cache po data-hash. Audyt 2026-07-07 (`docs/audits/AUDIT_2026-07-07.md`) znalazł: endpoint LLM publiczny z promptem kontrolowanym przez klienta (H1), brak danych SQLite na prod Cloud Run (H2), brak walidacji wejścia (M1), bug skali `_norm` (M2), brak walk-back sezonu (M3), silent except (M4), nity GUI (L3/L5).

**Pliki bazowe:** `src/footstats/api/routes/analyses.py`, `src/footstats/core/match_analysis.py`, `src/footstats/core/player_db.py`, `src/footstats/gui/src/components/MatchAnalysisView.jsx`, testy: `tests/test_match_analysis.py`.

## INWARIANTY
- Zero zapisu do prod Neon z testów; testy SQLite → `tmp_path`, nigdy `data/footstats_backtest.db`.
- `GET /analyses/matches` ma pozostać szybki (bez LLM w środku).
- Nie zmieniaj logiki modelu predykcji ani flag env — to warstwa prezentacji/API.
- GUI: design system z CLAUDE.md (tokeny, lucide 16/20px, jeden accent pairing).

## ZADANIA

### T1 — Walidacja wejścia POST /analyses/llm (Pydantic)
- **Pliki:** `analyses.py`; test `tests/test_analyses_endpoint.py` (utwórz jeśli brak; jeśli endpoint testowany w innym pliku — Grep `analyses_llm` w tests/ i dopisz tam).
- **Test-first:** `test_analyses_llm_odrzuca_body_bez_home` — POST `{"foo": 1}` → oczekuj **422** (teraz: 500 KeyError → RED).
- **Implementacja:** model `MatchCardIn(BaseModel)` z polami wymaganymi przez `card_data_hash` (`home, away, data, model, home_stats, away_stats, injuries_home, injuries_away`, opcjonalne `lineups, liga, host, top_scorers_*`); `card: MatchCardIn` w sygnaturze, dalej `card.model_dump()`.
- **Akceptacja:** `pytest tests/test_analyses_endpoint.py -q` green; malformed body = 422, poprawny = 200.

### T2 — Auth na endpointach analiz
- **Pliki:** `analyses.py`; wzorzec auth: Grep `require_user\|get_current_user` w `src/footstats/api/routes/coupons.py` i skopiuj dokładnie ten mechanizm.
- **Test-first:** `test_analyses_llm_wymaga_auth` — POST bez tokenu → **401**; analogicznie GET matches (decyzja: GET może zostać publiczny — jeśli tak, tylko POST chronimy; domyślnie chroń oba).
- **Implementacja:** `dependencies=[Depends(require_user)]` na routerze lub per-route. GUI: `MatchAnalysisView.jsx` — użyj centralnego fetch-helpera z `App.jsx` (Grep `Authorization` → `App.jsx:66`) zamiast gołego `fetch`.
- **Akceptacja:** testy auth green + zakładka działa po zalogowaniu (lokalnie: `npm run dev` + login).

### T3 — Skala prawdopodobieństw: usuń heurystykę `_norm`
- **Pliki:** `analyses.py:33-37`; źródło prawdy: Grep `prob_home_win` w `src/footstats/scrapers/bzzoiro.py` / miejscu budowy `pred_ml` — ustal czy skala to 0-1 czy 0-100.
- **Test-first:** `test_norm_pewniak_100pct` — dla skali 0-1: `_norm(1.0) == 100.0` (teraz zwraca 1.0 → RED).
- **Implementacja:** po ustaleniu skali — jedna ścieżka (np. zawsze `*100` dla 0-1), bez `if p > 1`. Jeśli źródła mieszają skale — normalizuj U ŹRÓDŁA, nie w endpoincie, i zostaw komentarz PL skąd skala.
- **Akceptacja:** test green; wartości na kartach niezmienione dla typowych probów (0.45 → 45.0).

### T4 — Walk-back sezonu dla `get_team_stats` + sezon z helpera
- **Pliki:** `player_db.py:246` (`get_team_stats`), `analyses.py:30` (`_SEASON`); test `tests/test_match_analysis.py`.
- **Test-first:** `test_get_team_stats_walkback_poprzedni_sezon` — wpis tylko season=2025, zapytanie o 2026 → zwraca wiersz 2025 (teraz None → RED).
- **Implementacja:** `get_team_stats_recent(team, season, lookback=2)` — pętla jak w `team_goal_shares_recent:184` (NIE zmieniaj istniejącego `get_team_stats` — dodaj wrapper, użyj go w `analyses.py`). `_SEASON`: Grep `_current_season` w src/ — jeśli helper istnieje, użyj; jak nie, zostaw stałą z komentarzem `# TODO: helper sezonu`.
- **Akceptacja:** kluby z danymi 2025 dostają statystyki; kadry (2026) bez zmian.

### T5 — Cache analiz: logging zamiast silent pass + eviction
- **Pliki:** `match_analysis.py:151-180`; `scripts/evict_cache.py` (sprawdź czy zna `analysis_cache` — Grep).
- **Test-first:** `test_set_cached_analysis_loguje_blad_sqlite` — podstaw ścieżkę-katalog jako db_path → oczekuj `log.warning` (caplog), nie wyjątku.
- **Implementacja:** `log = logging.getLogger(__name__)`; w `except sqlite3.Error as e: log.warning("analysis_cache: %s", e)`. Eviction: w `evict_cache.py` dodaj `DELETE FROM analysis_cache WHERE updated_at < datetime('now', '-30 days')` (guard: tabela może nie istnieć).
- **Akceptacja:** testy green; evict_cache przechodzi na bazie bez tabeli (nie crashuje).

### T6 — GUI nity (design system + fetch)
- **Pliki:** `MatchAnalysisView.jsx`.
- **Zmiany:** (a) emoji `⚽` (:49) → lucide `<Volleyball size={16}/>` lub `<Goal size={16}/>` (sprawdź dostępność w lucide-react, kolor `--accent-primary`); (b) `analizuj()`: `if (!r.ok) { setAi('Błąd serwera'); return; }` przed `r.json()`; (c) `useEffect` z AbortController i cleanup; (d) klucze list: `key={`${c.home}-${c.away}-${c.data}`}` zamiast indeksu.
- **Akceptacja:** build `npm run build` czysty + **weryfikacja wizualna agentem `footstats-gui-verifier`** (desktop+mobile) — reguła CLAUDE.md.

### T7 — Dane na prod: GCS-pull SQLite przy starcie API (albo decyzja: Neon)
- **Pliki:** `Dockerfile.api`, `src/footstats/api/main.py` (startup event), wzorzec: `docs/cloud_migration.md` + plan parquet P2 z TODO.md.
- **UWAGA:** to zmiana deploy — **przedstaw plan userowi przed implementacją** (koszt/architektura). Opcje: (a) startup pull `footstats_backtest.db` z GCS bucket (synergia z parquet P2), (b) migracja `team_stats`/`player_stats`/`analysis_cache` do Neon. Rekomendacja: (a) — mniejsza zmiana, jeden mechanizm dla parquet+SQLite.
- **Akceptacja:** karta meczu na prod (Cloud Run) pokazuje gole/mecz i strzelców; `analysis_cache` przeżywa restart (przy (a): upload-back albo akceptacja regeneracji — udokumentuj).

### T8 — Prompt bez „None"
- **Pliki:** `match_analysis.py:118-132` (`analysis_prompt`).
- **Test-first:** `test_analysis_prompt_brak_danych_bez_none` — karta z `gf_pg=None` → prompt zawiera „brak danych", nie „None".
- **Implementacja:** helper `_fmt(v, suffix="")` → `"brak danych"` dla None.
- **Akceptacja:** test green.

## DEFINITION OF DONE
Wszystkie taski: pełny `pytest tests/ -q` green, po 1 commicie per task, T6 zweryfikowany wizualnie, audyt `docs/audits/AUDIT_2026-07-07.md` — pozycje H1,M1-M4,L1,L3,L5 odhaczone (dopisz `✅ fixed <commit>`), H2 po decyzji usera.

## ESKALACJA
T7 wymaga decyzji usera PRZED kodem. Odkryte bugi poza zakresem → raport do orchestratora, nie naprawiaj. 3 nieudane próby → STOP + raport co wiesz.
