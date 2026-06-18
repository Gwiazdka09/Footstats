# Design: Offline Walk-Forward Validation Harness (Cel A)

**Data:** 2026-06-18
**Wersja projektu:** v3.4-stable
**Autor:** brainstorming session (Jakub + Claude)
**Cel nadrzędny:** M1 = 55% win rate. Ten spec realizuje **Cel A** — walidacja zmian λ offline, bez czekania na świeże dane live.

---

## 1. Problem

Accuracy live = 31.7% (41 settled, stare). TODO blokuje dalsze zmiany λ ("czekaj na ~20 świeżych settled, NIE dokładaj λ") bo zmiany psują atrybucję. Realnie: **6 zmian λ wpiętych ale niezwalidowanych** (kontuzje, xG+obrona, heurystyka, klasyfikacja, wagi 70/30, renorm 1X2). Czekanie ~1-2 tyg na dane live to wąskie gardło rozwoju.

Dodatkowy sygnał: kalibracja była **ODWRÓCONA** (90%+ pewności → 11% trafność). To nie wzorzec słabego modelu (ten daje kalibrację losową), lecz systematycznego błędu. Trzeba to zmierzyć, nie zgadywać.

## 2. Kluczowy insight

Gate "czekaj na dane live" dotyczy **tylko warstwy Groq/selekcji** (LLM wybiera typ — nieodtwarzalne offline bez tokenów i kontekstu kursów). Warstwa **statystyczna** (λ: kontuzje-wagi, xG+obrona, Dixon-Coles, wagi ensemble 70/30, renorm 1X2) **da się zwalidować offline DZIŚ** na 14 634 meczach historycznych.

## 3. Stan obecny (audyt)

**Działa:**
- `historical_loader.load_cached()` → 14 634 mecze, 5 lig, 2012-2026, kolumny: `date, league, season, home, away, hg, ag, result, hs, as_, hst, ast, hc, ac, odds_h, odds_d, ...` (+ Elo).
- `walkforward.py` — rusza offline, ma raport trafności **per pasmo pewności**.
- `calibration_monitor.py` — read-only na Neon (warstwa live).
- `poisson.py::predict_match` — produkcyjny model v2.6 (enrichmenty domyślnie neutralne 1.0).
- `poisson_bayesian.py::predict_match_bayesian` — **już ma Dixon-Coles** (atak/obrona + shrink) + `blend_with_classic`.
- `ensemble.py::ensemble_probs(p_poisson, p_bzzoiro, wagi, liga)` — ważona średnia.

**Problemy do naprawy w tym specu:**
1. 🔴 `walkforward.py::predict_single` to **model-zabawka** (goła średnia goli + prosta forma). Nie woła prod λ → jego trafność ≠ produkcja. Nie waliduje 6 zmian λ.
2. 🔴 `backtest_engine.py` FAŁSZUJE Poissona (pw/pr/pp = 50/25/25 placeholder, l.140-147), pisze `predictions`+`ai_feedback` do **PROD Neon** (zanieczyszcza prod+RAG), wymaga kluczy+żywego API+Groq. **Poza zakresem A** — tylko udokumentowany jako anty-wzorzec; nie używamy go do Toru 1.
3. 🟡 `walkforward.py` pisze `wf_results` do prod Neon — przenieść do osobnej backtest DB.

## 4. Rozwiązanie — dwa tory

### Tor 1 — wierny walk-forward modelu statystycznego (BUDUJEMY)

Podmiana silnika predykcji walk-forward na produkcyjny stack statystyczny, replay na 14k meczów.

**Komponenty:**

- **Adapter schematu** (`walkforward`-local): kolumny historical_loader (`home/away/hg/ag/odds_h/odds_d`) → schema prod oczekiwana przez `predict_match`/`predict_match_bayesian` (`gospodarz/goscie/gole_g/gole_a`). Jedna funkcja czysta, bez mutacji wejścia.
- **Devig kursów → p_bzzoiro**: z `odds_h/odds_d` (+ implikowany odds_a) policz prawdopodobieństwa implikowane bukmachera, usuń marżę (normalizacja do 1.0). To wejście `p_bzzoiro` do `ensemble_probs` — pozwala wiernie odtworzyć ensemble offline na danych historycznych.
- **Produkcyjny predykt**: dla każdego meczu (historia = mecze PRZED datą, no-lookahead):
  1. `predict_match(g, a, df_hist_prod_schema, ...)` z enrichmentami **neutralnymi** (importance/heurystyka/h2h/fortress/klasyfikacja = default 1.0; live-only, nieodtwarzalne historycznie).
  2. `predict_match_bayesian(g, a, df_hist)` (Dixon-Coles).
  3. `blend_with_classic` / `ensemble_probs(p_poisson, p_bzzoiro, liga=...)` → finalne p(win/draw/loss).
  4. Tip = argmax, conf = max p.
- **Flagi A/B**: każda zmiana λ + warstwa (classic / bayesian / ensemble-weight) togglowalna param funkcji → run on/off → zmierz wkład. Domyślne wartości = obecna produkcja.
- **Output**:
  - Trafność 1X2 globalnie + per liga.
  - **Kalibracja per pasmo pewności** (kluczowe: odpowiada "czy nadal odwrócona?").
  - Tabela porównawcza A/B (model/flaga → accuracy, n, ROI flat).
- **Zapis**: osobna **backtest DB** (SQLite `data/footstats_backtest.db` już istnieje, lub nowa tabela `wf_results` w niej) — NIE prod Neon. Naprawia problem #3.

**Czego Tor 1 NIE robi (świadomie, YAGNI):**
- Nie odtwarza Groq/RAG/kontuzje-scrape (warstwa live).
- Nie używa `backtest_engine.py` (anty-wzorzec).
- Nie dotyka prod Neon.

### Tor 2 — warstwa Groq/selekcja (PASYWNY, bez zmian kodu)

`calibration_monitor.py` + eksperyment System-vs-Groq (już zaimplementowane). Czeka na świeże settled (Task Scheduler 08:00 + settle 23:00). To JEDYNA rzecz która musi czekać. Bez nowego kodu w tym specu — tylko uruchamianie monitora co kilka dni.

## 5. Architektura / przepływ danych (Tor 1)

```
load_cached() [14k df English schema]
   │
   ├─ filtr ligi / min_date / sort by date
   │
   ▼ (pętla walk-forward, dla każdego meczu)
hist = df[date < match.date]                  # no-lookahead
   │
   ├─ adapter_schema(hist) → hist_prod         # gospodarz/goscie/gole_g/gole_a
   ├─ predict_match(g,a,hist_prod, flags)       # classic v2.6, enrichY neutral
   ├─ predict_match_bayesian(g,a,hist_prod)     # Dixon-Coles
   ├─ devig(match.odds_h, odds_d) → p_bzzoiro
   └─ ensemble_probs(p_poisson, p_bzzoiro, liga)→ p_final
        │
        ▼
   tip=argmax(p_final), conf=max(p_final)
   correct = (tip == actual_result)
        │
        ▼
   record → backtest DB (wf_results, osobna)
        │
        ▼ (po pętli)
   raport: accuracy global/per-liga + kalibracja per pasmo + A/B table
```

## 6. Obsługa błędów / walidacja

- Brak historii (< MIN_HIST meczów drużyny) → skip meczu (jak teraz), licz osobno ile pominięto.
- Brak kursów (`odds_h/odds_d` NaN) → ensemble degraduje do samego Poissona (`ensemble_probs` już obsługuje brak klucza), oznacz rekord flagą `no_odds`.
- Brak `result` (H/D/A) → skip z licznikiem.
- `predict_match` zwraca None → skip z licznikiem.
- Adapter: walidacja obecności wymaganych kolumn na wejściu, fail fast z czytelnym błędem.
- Zero zapisów do prod Neon — test/guard że connection string ≠ prod (lub osobny moduł DB dla backtest).

## 7. Testy

- **Unit**: adapter schematu (mapowanie kolumn, brak mutacji, brak wymaganej kolumny → błąd).
- **Unit**: devig (suma p = 1.0; marża usunięta; NaN → None).
- **Unit**: no-lookahead (hist zawiera tylko mecze < date — test na syntetycznym df).
- **Integration**: pełen walk-forward na małym wycinku (1 liga, ~200 meczów) → zwraca accuracy + kalibrację, n > 0, brak zapisu do prod.
- **Regression**: flaga A/B off = obecna produkcja (wartości λ niezmienione → wynik deterministyczny).
- Coverage ≥ 80% nowego kodu. Mock DB (backtest SQLite tymczasowa).

## 8. Kryteria sukcesu

1. Jedno polecenie CLI uruchamia wierny walk-forward na 14k meczów offline, bez kluczy API, bez czekania.
2. Raport pokazuje **czy kalibracja nadal odwrócona** (per pasmo pewności, n≥5 na pasmo).
3. Tabela A/B mierzy wkład każdej z 6 zmian λ + classic vs bayesian vs ensemble.
4. Zero zapisów do prod Neon.
5. Wynik daje decyzję: które λ zostają, które wracają, czy Dixon-Coles podnosi trafność.

## 9. Poza zakresem (następne kroki po A)

- Refactor/izolacja `backtest_engine.py` (prod-pollution fix) — osobny spec.
- Strojenie wag ensemble per liga na bazie wyników A.
- Tor 2 werdykt (po ~15 System settled).
