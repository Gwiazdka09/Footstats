# Changelog

> Archiwum ukończonych prac (przeniesione z TODO.md przez `footstats-scribe`).
> Aktywne zadania: `TODO.md`. Pełna historia commitów: `git log`.

## 2026-06-19

### Cel A — walk-forward offline, walidacja 10 lig
- Harness `scripts/run_walkforward_prod.py` (classic + Dixon-Coles + ensemble, devig kursów, no-lookahead, zapis `data/walkforward.db` — NIE Neon).
- Cache rozszerzony 5→**10 lig** (32 400 meczów): +ITA Serie A, +FRA Ligue 1, +AUT, +BEL, +SCO.
- **Werdykt 10 lig (out-of-sample, n=25 738):** dixoncoles **51.3%** > baseline 49.6% > poisson_only 48.1%. DC +1.7pp — generalizuje (NED było +1.9pp).
- Kalibracja **MONOTONICZNA** na wszystkich 10 ligach: 37.5→43.2→46.4→58.8% (pasmo 65%+ = strefa zakładów). Per liga (DC): NED 54.9, SCO 54.8, ENG 53.4, ITA 53.1, GER 51.5, ESP 51.2, BEL 50.4, FRA 49.8, AUT 47.8, POL 44.6.
- Fix kodów lig BEL/SCO: format sezonowy B1/SC0 zamiast `/new/` (404) — `c43e0bc3d`.

### Cel B — root cause live ≪ offline (częściowy)
- **bug 1 NAPRAWIONY** (`072ee9035`): `quick_picks` nie budował klucza `pred` → confidence leciało na Groq fallback (overconfident) zamiast prob modelu → inwersja kalibracji live. Fix: `wyniki` dostaje `pred` dict (p_wygrana/p_remis/p_przegrana/btts/over25/under25).
- bug 2 (otwarty, w TODO): `ai_tip` = selekcja Groq (44% remisy, 12.5% wyjazdy hit) zamiast argmax modelu.

### Cel C — Dixon-Coles w produkcji
- Wpięty za flagą `USE_DIXON_COLES` (default ON, env-toggle), `W_BAYESIAN=0.5`. 8 zadań TDD: `b42fd8043`, `ff0da87b5`, `b0e307e94`, `a15b616f5`, `f14255824`, `4e96110d5` (merge `b0a83d8fd`).
- `blend_dixon_coles` (poisson_bayesian): remap pa→pp, blend nad pw/pr/pp, bt/o25 nietknięte, graceful (DC None → classic). Wspólna funkcja z `wf_harness` (parytet prod↔harness).
- Smoke A/B NED: DC 55.2% > baseline 54.0%. Weryfikacja 10 lig po merge = identyczna z przed-merge (lewar nietknięty przez refactor).
- E2e test regresji wiringu (`4cd677820`, merge `e1b8f8809`) — łapie usunięcie wpięcia (dowiedzione RED).
- Code review: `footstats-reviewer` APPROVE z uwagami (0× P1/P2), `footstats-data-guard` SAFE. P3 #1 (luka testu wiringu) naprawiona e2e testem.
- Suita: **1078 pass** / 4 skip.

### Zespół subagentów
- Dodany `footstats-scribe` (kronikarz: sesja → TODO/CHANGELOG/STATUS + commit, archiwizuje zamiast kasować).
