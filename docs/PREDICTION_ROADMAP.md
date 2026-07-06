# FootStats — Roadmap Predykcji do Doskonałości

**Cel:** najlepsza możliwa predykcja meczów. **Poza zakresem:** monetyzacja/użytkownicy/płatności (P3 zarchiwizowane 2026-07-06).

---

## Teza strategiczna

**Rynek bukmacherski jest nieprzekraczalny w 1X2 top-lig** (własna analiza: LightGBM 51.6% < rynek 53.1% < baseline; potwierdza literatura). Walka z rynkiem jego bronią = sufit ~51%.

→ **Nie graj tam gdzie rynek jest silny. Graj tam gdzie jest słaby albo gdzie masz dane których rynek nie wycenił szybko.**

Dowód (WC 2026, λ-kadr): Over 2.5 (Brazil-Norway) trafione, 1X2 (Mexico host-boost) 2× pudło. Model sam pokazuje gdzie ma edge = **gole, nie 1X2**.

---

## 4 przesunięcia kąta (rdzeń)

| # | Z → Na | Dlaczego | Status |
|---|--------|----------|--------|
| ① **Metryka** | win-rate → **CLV** (Closing Line Value) | Jedyny udowodniony predyktor zysku. `clv_tracker.py` gotowy | forward-only (brak historycznych kursów zamknięcia) |
| ② **Cel** | 1X2 → **gole/xG** (O/U, team totals, BTTS) | Mniej efektywne niż 1X2, więcej struktury; nasz λ+xG mocny | **buildable NOW** (parquet ma odds_over25) |
| ③ **Gra** | wynik meczu → **nieefektywność rynku** | Late team-news, nisze, fade publiczności | player-DB gotowy pod late-news |
| ④ **Filozofia** | generalista → **specjalista value** | Stawiaj TYLKO gdy fair-value ≠ rynek o próg | do zbudowania |

---

## Bank pomysłów (do doskonałości)

### A. Buildable TERAZ (dane w parquet: odds_h/d/a, odds_over25/under25, hg/ag, hs/as_ strzały, hst/ast celne, hc/ac rożne, ht_* połowa, btts)

1. **Silnik goli-value + ROI backtest** ⭐ — P(Over 2.5) z λ Poissona → value gdy P×kurs > próg → ROI na historii. Operacjonalizuje ②+④. *[PIERWSZY BUILD]*
2. **Shot-based xG proxy** — rolling strzały/celne per drużyna → oczekiwane xG → P(Over). Rynek może niedoceniać jakości strzałów. Backtestowalne (mamy hs/hst/hc).
3. **Dixon-Coles tuning** — optymalizacja time-decay + rho (korelacja niskobramkowych) pod O/U, nie 1X2.
4. **Bayesian hierarchical ratings** — atak/obrona jako latentne, update in-season; czystsze niż punktowe λ.
5. **Anomaly detector** — flaguj mecze gdzie model ≫ rynek (największy rozjazd) do przeglądu.
6. **Per-liga edge** — ROI/CLV per liga; podwój tam gdzie edge, omijaj efektywne rynki.
7. **Korelowane kupony (same-game)** — bivariate Poisson już liczy korelację; wyceniaj combo lepiej niż book.

### B. Wymaga nowych danych (mamy pipeline, trzeba wpiąć)

8. **Player-availability delta** ⭐ — potwierdzona absencja gwiazdy 1h przed → korekta λ → value vs wolny rynek. **Baza graczy zbudowana** (goal_share, team_stats).
9. **Market-movement / steam** — dryf kursów (opening→current); sharp money zdradza wartość. Śledź sharps.
10. **Referee/venue/weather** — `referee_db` jest; pogoda (deszcz→mniej goli) pod O/U.
11. **Momentum + rest-days** — gęstość terminarza, zmęczenie → gole. Infra schedule-adjusted istnieje (odrzucona solo, może działać z player-data).
12. **xG per gracz** (Understat playersData) — realny xG składu, nie tylko gole.

### C. Research / dłuższe

13. **In-play/live model** — kursy live opóźnione za stanem gry; live-xG łapie value mid-mecz.
14. **Meta-model / stacking** — kalibrowany meta-learner łączy wszystkie sygnały → prawdopodobieństwo → stawiaj tylko na calibrated-confident value.
15. **Alt-data** — sentyment news/social o składach, przecieki lineupów, warunki murawy.
16. **Ensemble markets** — spójność międzyrynkowa: jak Over mispriced, BTTS/team-totals często też.

---

## ⚠️ WYNIKI EMPIRYCZNE (2026-07-06) — static value betting OBALONE

Backtest `scripts/backtest_goals_value.py` na 25 661 meczach (kursy O/U z parquet):

| Strategia | Zakłady | ROI |
|-----------|---------|-----|
| Over (baza, zawsze) | 25 661 | **−4.5%** (marża booka) |
| Over value (λ gole) | 8 334 | −5.5% |
| Under value (λ gole) | 5 783 | −8.4% |
| Over/Under value (strzały-xG proxy) | 11 724 | −6.3% |
| Value margin 0.25 (duże rozjazdy) | 3 257 | **−9.9%** |

**Wniosek:** model Poissona/xG-proxy z publicznych box-score **NIE bije rynku O/U** — im większy rozjazd model↔rynek, tym bardziej MODEL się myli (margin 0.25 najgorszy). To samo co w 1X2. **Nie da się pobić rynku modelem na tych samych publicznych danych których używa rynek.**

### Przeramowanie "doskonałości" — 2 uczciwe ścieżki

**Ścieżka A (realistyczna) — najlepszy PREDYKTOR, nie market-beater.**
Skoro ROI-vs-rynek jest niedostępne publicznymi danymi, celem = **kalibracja i trafność** (Brier/log-loss min, kalibracja prawdopodobieństw, accuracy per liga). Apka doskonała w PRZEWIDYWANIU, uczciwa że rynku nie bije. Metryka: log-loss/Brier, nie ROI.

**Ścieżka B (edge-hunting, trudniejsza) — jedyne realne przewagi:**
- **Player-availability delta** — stawiaj ZANIM rynek wchłonie team-news (baza graczy gotowa). Wymaga forward + szybkiej reakcji, nie backtestu.
- **Live/in-play** — kursy opóźnione za stanem gry.
- **Market-movement** — śledź dryf (opening→close), idź za sharp money.
- **Prawdziwe xG** (lokalizacja/jakość strzału, nie liczba SoT) — jedyna "lepsza dana" backtestowalna, jak zdobędziemy historyczne xG.

Static fair-value value-betting (#1, #4) = **ślepa uliczka** (empirycznie). Harness `goals_value`+backtest zostaje jako **infra do testowania czy NOWY sygnał bije rynek** (dołóż xG/player-delta → uruchom ten sam backtest).

## 📊 ŚCIEŻKA A — kalibracja (2026-07-06, backtest historyczny)

`scripts/backtest_calibration.py` (25 660 meczów, model rolling-λ vs rynek devig):

| Metryka (niżej=lepiej) | MODEL | RYNEK | luka |
|------------------------|-------|-------|------|
| log-loss 1X2 | 1.014 | 0.962 | +5.4% |
| log-loss O/U | 0.704 | 0.671 | +4.9% |
| Brier O/U | 0.253 | 0.239 | +5.9% |

**Model ~5% gorszy od rynku, ale systematycznie OVERCONFIDENT** (krzywa kalibracji O/U): predykcja 90-100% → realnie 74%; predykcja 0-10% → realnie 41%. Prawdopodobieństwa za skrajne.

**Fix = shrinkage ku środkowi** (`shrink_prob`, `core/calibration_metrics.py`). **Walidacja OUT-OF-SAMPLE** (`scripts/validate_calibration_oos.py`, k fitnięte na train 60% → test 40%):

| TEST (OOS, ostatnie 40%) | log-loss O/U |
|--------------------------|--------------|
| model bez kalibracji | 0.7066 |
| model + shrink k=0.45 | **0.6840** (+3.2%) |
| rynek (benchmark) | 0.6692 |

**Luka do rynku ścięta 61% OOS** — lever REALNY, nie in-sample overfit. Model stabilnie overconfident.

⚠️ **Uwaga do wpięcia:** backtest = czysty rolling-Poisson. Live pipeline już blenduje ku rynkowi (`ENSEMBLE_MARKET_WEIGHT=0.70`) → częściowo tłumi overconfidence. Wpięcie: **shrink Poissona PRZED ensemble** (kalibrowany Poisson + blend rynku > overconfident Poisson + blend), nie na wyjściu ensemble (ryzyko double-shrink). Wymaga zmierzenia kalibracji samego ensemble (brak historycznych prob Bzzoiro → osobno).

## 📡 ŚCIEŻKA B — edge z absencji (primitive gotowy, forward-only)

`core/availability_edge.py`: `over_edge_from_absences(λh,λa,out_home,out_away,market_p)`
→ skorygowane λ (goal_share nieobecnych) → P(Over) → **edge vs rynek zanim wchłonie news**.
Reuse `injury_lambda_factors`/bazy graczy. **Nie backtestowalne** (brak historycznych składów) → walidacja logiki (unit), ROI dopiero forward + CLV.

## Rekomendowana kolejność (po wynikach)

1. ~~Silnik goli-value + ROI backtest~~ ✅ ZROBIONE → OBALIŁO static value betting (patrz wyżej). Harness zostaje jako infra.
2. **Ścieżka A — kalibracja** (rekomendowane, realistyczne): mierz log-loss/Brier + kalibrację per liga; dostrój Dixon-Coles (time-decay, rho) pod trafność; cel = najlepszy predyktor, nie ROI.
3. **Ścieżka B — player-availability delta** (#8): jedyny realny edge z naszą infrą — forward test (stawiaj przed ruchem rynku na team-news). Nie backtest.
4. **CLV live** (①): zbieraj kursy zamknięcia (Betexplorer) → jedyny sposób zmierzyć realny edge forward.
5. **Prawdziwe xG historyczne** — jak zdobędziemy, uruchom istniejący backtest: czy xG (nie SoT) bije rynek?

**North-star (przeramowany):** log-loss/Brier + kalibracja (ścieżka A). ROI-vs-rynek = tylko forward, tylko z edge'm informacyjnym (ścieżka B). Static modeling na publicznych danych = udowodniony ślepy zaułek.
