# Design: Wpiecie korekty Dixon-Coles do produkcyjnej sciezki predykcji (Cel C)

**Data:** 2026-06-19
**Wersja projektu:** v3.4-stable
**Autor:** brainstorming (Jakub + Claude / footstats-planner)
**Cel nadrzedny:** M1 = 55% win rate. Cel C - wpiecie zwalidowanego offline ramienia Dixon-Coles do PRODUKCJI, za flaga, A/B-owalne, bez lookahead.

---

## 1. Problem

Walk-forward (Cel A, wf_harness.py) potwierdzil lewar Dixon-Coles:
- +1.7pp out-of-sample na 10 ligach: 51.3% (ramie dixoncoles) vs 49.6% baseline.
- +1.9pp na NED-Eredivisie.
- Kalibracja monotoniczna na wszystkich 10 ligach (trafnosc rosnie z pasmem pewnosci).

Ramie DC (poisson_bayesian.py::predict_match_bayesian) NIE jest wpiete w produkcje. Potwierdzone grepem: predict_match_bayesian/poisson_bayesian wystepuje tylko w wf_harness.py + testach. Sciezka prod (quick_picks.py::szybkie_pewniaczki_2dni) jej nie wola - uzywa classic predict_match + ensemble_probs z Bzzoiro.

TODO 06-18 (zamrozenie lambda) blokuje NIEZWALIDOWANE zmiany lambda. DC jest zwalidowany offline -> wpiecie dozwolone, ale: (a) za flaga, (b) wstecznie kompatybilnie, (c) z testem parytetu prod-vs-harness.

## 2. Stan obecny (audyt - zweryfikowany w kodzie)

Ramie DC - src/footstats/core/poisson_bayesian.py:
- predict_match_bayesian(g, a, df, home_advantage=BONUS_DOMOWY) (l. 78-157).
- Polski schemat: gospodarz/goscie/gole_g/gole_a (l. 33-37) - IDENTYCZNY jak prod df_mecze. Brak adaptera w prodzie.
- Recency weighting (last5=3x, l.16-18) + prior bayesowski (_PRIOR_WEIGHT=3.0, l.22).
- Zwraca klucz pa (away win), NIE pp (l.144,151): {lambda_g,lambda_a,pw,pr,pa,n_home,n_away,...,model}.
- Prawdopodobienstwa to ULAMKI 0-1 (l.149-151) - prod uzywa procentow 0-100 -> wymaga x100.
- DC NIE liczy btts/over25 - tylko 1X2. Blend DC dotyka wylacznie pw/pr/pp.
- None gdy df.empty / brak gole_g / home_home[att] None / away_away[att] None (l.94-95,110-111).

Referencja zwalidowanej integracji - wf_harness.py::predict_one (l.72-116):

    pred = predict_match(g, a, hist_prod, use_xg=False, use_calibration=flags.use_calibration)
    p_model = {pw: pred[p_wygrana], pr: pred[p_remis], pp: pred[p_przegrana]}
    if flags.use_bayesian:
        bay = predict_match_bayesian(g, a, hist_prod)
        if bay:
            p_bay = {pw: bay[pw]*100, pr: bay[pr]*100, pp: bay[pa]*100}   # pa->pp + x100
            p_model = _weighted_blend(p_model, p_bay, 1.0-flags.w_bayesian, flags.w_bayesian)
    p_bzz = devig_1x2(...)
    p_final = ensemble_probs(p_model, p_bzz, liga=league) if (use_ensemble and p_bzz) else p_model

_weighted_blend (l.64-69): wazona srednia po (pw,pr,pp) + renorm do 100. TO JEST zwycieska konfiguracja (w_bayesian=0.5, use_ensemble=True).

Sciezka prod - quick_picks.py::szybkie_pewniaczki_2dni (l.201-232):

    _pred_p = predict_match(g, a, df_mecze, heurystyka_g=..., h2h_g=..., fortress_g=..., klasyfikacja=...)
    if _pred_p:
        _p_pois = {pw: _pred_p[p_wygrana], pr: _pred_p[p_remis], pp: _pred_p[p_przegrana],
                   bt: _pred_p[btts], o25: _pred_p[over25]}
        _p_bzz  = {pw: pw, pr: pr, pp: pp, bt: bt, o25: o25}
        _bl = ensemble_probs(_p_pois, _p_bzz, liga=liga)

- _p_pois ma klucze bt/o25 ktorych DC NIE ma -> DC blenduje TYLKO pw/pr/pp; bt/o25 zostaja z classic.
- predict_match w prodzie: use_xg=True (default) - mecze przyszle, datetime.now()=biezacy sezon, brak lookahead.

Roznica prod vs harness (swiadoma): harness use_xg=False (replay), prod use_xg=True (przyszle). Harness devig -> p_bzz; prod p_bzz z Bzzoiro ML. Oba karmia to samo ensemble_probs. Wspolny rdzen 1:1: blend classic pw/pr/pp + DC pa->pp x100 -> wydzielamy do JEDNEJ funkcji i testujemy parytet.

## 3. Decyzja architektoniczna - wspolna funkcja blend_dixon_coles

Dla parytetu prod-vs-harness wydzielamy blend DC do JEDNEJ funkcji w poisson_bayesian.py, uzywanej przez wf_harness.predict_one i quick_picks:

    def blend_dixon_coles(p_model: dict, g: str, a: str, df: pd.DataFrame, w_bayesian: float = 0.5) -> dict:
        # p_model: {pw,pr,pp,...} procenty 0-100 (z classic). DC: pa (away) ulamki -> remap pa->pp + x100.
        # DC None -> p_model bez zmian (graceful). Klucze spoza {pw,pr,pp} (bt/o25) NIE modyfikowane.
        bay = predict_match_bayesian(g, a, df)
        if not bay:
            return p_model
        p_bay = {pw: bay[pw]*100, pr: bay[pr]*100, pp: bay[pa]*100}
        w_c = 1.0 - w_bayesian
        blended = {k: p_model[k]*w_c + p_bay[k]*w_bayesian for k in (pw,pr,pp)}
        s = blended[pw] + blended[pr] + blended[pp] or 1.0
        out = dict(p_model)
        out[pw] = round(blended[pw]/s*100, 4)
        out[pr] = round(blended[pr]/s*100, 4)
        out[pp] = round(blended[pp]/s*100, 4)
        return out

wf_harness._weighted_blend zostaje (legacy); predict_one przelaczamy na blend_dixon_coles -> parytet po jednej funkcji. Test: dla tego samego (g,a,df,w_bayesian) prod i harness daja identyczne pw/pr/pp.

## 4. Punkt wpiecia w prod + flaga

Wpiecie: quick_picks.py, w bloku if _pred_p: (l.218-230), MIEDZY predict_match a ensemble_probs:

    if _pred_p:
        _p_pois = {pw:..., pr:..., pp:..., bt:..., o25:...}
        if USE_DIXON_COLES:
            from footstats.core.poisson_bayesian import blend_dixon_coles
            _p_pois = blend_dixon_coles(_p_pois, g, a, df_mecze, w_bayesian=W_BAYESIAN)
        _p_bzz = {pw:pw, pr:pr, pp:pp, bt:bt, o25:o25}
        _bl = ensemble_probs(_p_pois, _p_bzz, liga=liga)

DC wchodzi PRZED ensemble_probs - jak w harness (blend modelu -> ensemble z kursami).

Flaga + default - config.py (os juz zaimportowany, l.1):

    USE_DIXON_COLES = os.getenv("USE_DIXON_COLES", "1").strip() not in ("0","false","False","")
    W_BAYESIAN      = float(os.getenv("W_BAYESIAN", "0.5"))   # waga ramienia DC (0=classic,1=pelny DC)

Uzasadnienie default=ON:
- Lewar zwalidowany out-of-sample na 10 ligach z kalibracja monotoniczna - zmierzony +1.7pp.
- Blend graceful: DC None -> p_model bez zmian = baseline. Najgorszy przypadek = baseline.
- DC dotyka tylko pw/pr/pp; bt/o25 nietkniete -> zero ryzyka regresji rynkow goli.
- os.getenv: wylaczenie w sekunde bez redeploya. W_BAYESIAN env-overridable do strojenia.
- (Alternatywa: default "0" jesli zespol woli ostroznie; reszta planu bez zmian. Rekomendacja: ON.)

## 5. Anty-lookahead (KRYTYCZNE)

- predict_match_bayesian NIE uzywa datetime.now() - ratingi tylko z przekazanego df (brak importu datetime w poisson_bayesian.py).
- W prodzie df_mecze=load_cached() to historia; DC dostaje ten sam df co classic. Mecz predykowany jest PRZYSZLY (nie ma go w df) -> brak leaku wlasnego wyniku.
- Wzorzec flag jak use_xg/use_calibration (poisson.py l.69-70,190,205) - USE_DIXON_COLES analogiczna bramka.
- Test: DC liczy tylko z dostarczonej historii, deterministycznie, bez now()/cache.

## 6. Remap i spojnosc schematu

| Aspekt | DC | Prod | Dzialanie |
|---|---|---|---|
| Schemat kolumn | gospodarz/goscie/gole_g/gole_a | gospodarz/goscie/gole_g/gole_a | identyczny - brak adaptera |
| Wynik goscia | pa | pp | remap pa->pp |
| Skala | ulamki 0-1 | procenty 0-100 | x100 |
| Rynki goli | brak | bt/o25 | DC NIE dotyka bt/o25 |
| home_advantage | BONUS_DOMOWY | BONUS_DOMOWY | spojne |

## 7. Pomiar efektu w live

Vehicle: scripts/calibration_monitor.py (read-only na Neon, l.167):
- raport_system_paper() (l.78) - paper-trade Systemu na settled.
- raport_system_vs_groq() (l.111) - System vs Groq.
- raport_kalibracji() (l.33) - kalibracja per pasmo na live.

Protokol:
1. Przed wpieciem: baseline raport_system_paper (accuracy, n).
2. Po wpieciu (USE_DIXON_COLES=1): zbieraj ~15-20 swiezych settled (Task Scheduler 08:00 + settle 23:00).
3. Porownaj trafnosc Systemu vs baseline; kalibracja per pasmo monotoniczna jak offline.
4. Sanity parytet: dla nadchodzacego meczu predict_one(use_bayesian=True, w_bayesian=W_BAYESIAN) na tej samej historii = pw/pr/pp prod przed ensemble_probs.
5. Guard: monitor read-only; pomiar NIE pisze do prod ani nie wysyla Telegrama.

## 8. Obsluga bledow

- DC None -> blend_dixon_coles zwraca p_model bez zmian (graceful = baseline).
- df_mecze is None w quick_picks -> blok Poisson/DC pominiety (guard l.201) -> zostaje Bzzoiro ML.
- blend_dixon_coles nie rzuca do petli prod - blad lapany blokiem except w quick_picks l.231.
- Renorm pw/pr/pp do 100 po blendzie (zdarzenia rozlaczne, jak A3 l.183-189).

## 9. Testy

- Unit blend_dixon_coles: remap pa->pp; x100; bt/o25 nietkniete; DC None -> identyczny; suma ~100.
- Unit anty-lookahead: deterministyczny, bez datetime.now().
- Parytet prod-vs-harness: identyczne pw/pr/pp do 4dp.
- Integration quick_picks: ON wykonuje sie; OFF = obecne zachowanie (regresja).
- Guard: brak utils.db/Neon i Telegram (mock + assert_not_called).
- Coverage >= 80% nowego kodu. Arrange-Act-Assert.

## 10. Kryteria sukcesu

1. blend_dixon_coles w poisson_bayesian.py, uzywana przez prod i harness.
2. USE_DIXON_COLES + W_BAYESIAN w config; default ON; env-overridable.
3. Test parytetu zielony.
4. Remap pa->pp + x100 + bt/o25 nietkniete - pokryte.
5. Anty-lookahead udowodniony testem.
6. Pelna suita zielona (OFF == obecna produkcja).
7. Protokol pomiaru live udokumentowany; zero zapisow do prod/Telegram.

## 11. Poza zakresem

- Strojenie W_BAYESIAN per liga (po live).
- DC w innych sciezkach (weekly_picks, daily_agent) - osobny spec.
- Refactor _weighted_blend (zostaje).
