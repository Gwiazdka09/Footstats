import pandas as pd
import pytest

from footstats.core.wf_harness import adapt_to_prod_schema


def test_adapt_to_prod_schema_maps_columns():
    df = pd.DataFrame([
        {"date": "2020-01-01", "league": "NED-Eredivisie", "home": "Ajax",
         "away": "PSV", "hg": 2, "ag": 1, "result": "H"},
    ])
    out = adapt_to_prod_schema(df)
    assert {"gospodarz", "goscie", "gole_g", "gole_a", "data"}.issubset(out.columns)
    assert out["gospodarz"].iloc[0] == "Ajax"
    assert out["goscie"].iloc[0] == "PSV"
    assert out["gole_g"].iloc[0] == 2
    assert out["gole_a"].iloc[0] == 1


def test_adapt_to_prod_schema_does_not_mutate_input():
    df = pd.DataFrame([{"date": "2020-01-01", "league": "X", "home": "A",
                        "away": "B", "hg": 1, "ag": 0, "result": "H"}])
    cols_before = list(df.columns)
    adapt_to_prod_schema(df)
    assert list(df.columns) == cols_before


def test_adapt_to_prod_schema_missing_column_raises():
    df = pd.DataFrame([{"home": "A", "away": "B"}])
    with pytest.raises(ValueError, match="brak"):
        adapt_to_prod_schema(df)


from footstats.core.wf_harness import devig_1x2


def test_devig_1x2_sums_to_100():
    p = devig_1x2(odds_h=1.57, odds_d=3.9, odds_a=7.5)
    assert p is not None
    total = p["pw"] + p["pr"] + p["pp"]
    assert abs(total - 100.0) < 0.01


def test_devig_1x2_favorite_has_highest_prob():
    p = devig_1x2(odds_h=1.57, odds_d=3.9, odds_a=7.5)
    assert p["pw"] > p["pr"] > p["pp"]


def test_devig_1x2_none_on_missing_odds():
    assert devig_1x2(odds_h=None, odds_d=3.9, odds_a=7.5) is None
    assert devig_1x2(odds_h=float("nan"), odds_d=3.9, odds_a=7.5) is None


from footstats.core.wf_harness import predict_one, ModelFlags


def _hist_prod():
    """Historia w schemacie prod: dwie drużyny, dużo meczów (>OSTATNIE_N)."""
    rows = []
    for i in range(15):
        rows.append({"gospodarz": "Alfa", "goscie": "Beta", "gole_g": 2, "gole_a": 0,
                     "data": f"2019-{(i % 12) + 1:02d}-01", "league": "TEST"})
        rows.append({"gospodarz": "Beta", "goscie": "Alfa", "gole_g": 1, "gole_a": 1,
                     "data": f"2019-{(i % 12) + 1:02d}-15", "league": "TEST"})
    import pandas as pd
    return pd.DataFrame(rows)


def test_predict_one_baseline_returns_tip_and_conf():
    flags = ModelFlags(use_bayesian=False, use_ensemble=True, use_calibration=False)
    res = predict_one("Alfa", "Beta", _hist_prod(), league="TEST",
                      odds_h=1.8, odds_d=3.5, odds_a=4.2, flags=flags)
    assert res is not None
    assert res["tip"] in ("1", "X", "2")
    assert 0.0 <= res["conf"] <= 1.0
    assert abs(res["pw"] + res["pr"] + res["pp"] - 100.0) < 0.5


def test_predict_one_bayesian_arm_runs():
    flags = ModelFlags(use_bayesian=True, use_ensemble=True, use_calibration=False)
    res = predict_one("Alfa", "Beta", _hist_prod(), league="TEST",
                      odds_h=1.8, odds_d=3.5, odds_a=4.2, flags=flags)
    assert res is not None
    assert res["tip"] in ("1", "X", "2")


def test_predict_one_no_odds_falls_back_to_poisson_only():
    flags = ModelFlags(use_bayesian=False, use_ensemble=True, use_calibration=False)
    res = predict_one("Alfa", "Beta", _hist_prod(), league="TEST",
                      odds_h=None, odds_d=None, odds_a=None, flags=flags)
    assert res is not None


def test_predict_one_uses_shared_blend_dixon_coles(monkeypatch):
    """predict_one z use_bayesian musi delegowac do poisson_bayesian.blend_dixon_coles."""
    import footstats.core.poisson_bayesian as pb

    called = {"n": 0}
    real = pb.blend_dixon_coles

    def _spy(p_model, g, a, df, w_bayesian=0.5):
        called["n"] += 1
        return real(p_model, g, a, df, w_bayesian=w_bayesian)

    monkeypatch.setattr(pb, "blend_dixon_coles", _spy)

    flags = ModelFlags(use_bayesian=True, use_ensemble=True, use_calibration=False)
    res = predict_one("Alfa", "Beta", _hist_prod(), league="TEST",
                      odds_h=1.8, odds_d=3.5, odds_a=4.2, flags=flags)
    assert res is not None
    assert called["n"] == 1  # delegacja do wspolnej funkcji


def test_predict_one_returns_none_when_no_history():
    import pandas as pd
    empty = pd.DataFrame(columns=["gospodarz", "goscie", "gole_g", "gole_a", "data", "league"])
    flags = ModelFlags()
    assert predict_one("X", "Y", empty, league="TEST",
                       odds_h=2.0, odds_d=3.0, odds_a=3.5, flags=flags) is None


from footstats.core.wf_harness import run_walkforward, report


def _hist_df_english(n_pairs=60):
    """DataFrame w schemacie historical_loader (English) z kursami."""
    import pandas as pd
    rows = []
    teams = ["Alfa", "Beta", "Gama", "Delta"]
    for i in range(n_pairs):
        h = teams[i % 4]
        a = teams[(i + 1) % 4]
        rows.append({
            "date": pd.Timestamp("2019-01-01") + pd.Timedelta(days=i * 3),
            "league": "TEST", "home": h, "away": a,
            "hg": (i % 3), "ag": (i % 2), "result": "H" if (i % 3) > (i % 2) else "A",
            "odds_h": 1.9, "odds_d": 3.4, "odds_a": 4.0,
        })
    return pd.DataFrame(rows)


def test_run_walkforward_produces_records():
    df = _hist_df_english()
    flags = ModelFlags(use_bayesian=False, use_ensemble=True, use_calibration=False)
    out = run_walkforward(df, league="TEST", flags=flags, run_tag="t", verbose=False)
    assert len(out) > 0
    assert set(["tip", "correct", "pred_conf", "match_date"]).issubset(out.columns)
    assert out["match_date"].min() > str(df["date"].min())[:10]


def test_report_has_accuracy_and_calibration():
    df = _hist_df_english()
    flags = ModelFlags(use_calibration=False)
    out = run_walkforward(df, league="TEST", flags=flags, run_tag="t", verbose=False)
    txt = report(out)
    assert "Accuracy 1X2" in txt
    assert "pasmo pewno" in txt.lower()


from footstats.core.wf_harness import run_ab


def test_run_ab_compares_arms(tmp_path):
    df = _hist_df_english()
    db = tmp_path / "ab.db"
    arms = {
        "baseline": ModelFlags(use_bayesian=False, use_ensemble=True, use_calibration=False),
        "dixoncoles": ModelFlags(use_bayesian=True, use_ensemble=True, use_calibration=False),
    }
    summary = run_ab(df, arms, league="TEST", db_path=db, verbose=False)
    assert set(summary.keys()) == {"baseline", "dixoncoles"}
    for tag, stat in summary.items():
        assert "accuracy" in stat and "n" in stat
        assert stat["n"] > 0
    from footstats.core.wf_db import load_run
    assert len(load_run(db, "baseline")) > 0


def _run_walkforward_ref(df, league=None, flags=None, run_tag="run",
                         max_matches=None, min_date=None, verbose=False):
    """Referencyjna kopia STAREJ (przedoptymalizacyjnej) pętli walk-forward.

    Dokładny algorytm O(n^2): per-mecz pełny skan `df[df["date"] < row["date"]]`
    + filtr ligi + adapt_to_prod_schema per mecz. Używana wyłącznie do testu
    parytetu bit-identycznego z nową (zoptymalizowaną) implementacją.
    """
    from footstats.core.wf_harness import adapt_to_prod_schema, predict_one

    flags = flags or ModelFlags()

    work = df if league is None else df[df["league"] == league]
    work = work.sort_values("date").reset_index(drop=True)

    if min_date:
        work = work[work["date"] >= pd.Timestamp(min_date)].reset_index(drop=True)
    else:
        start = max(50, len(work) // 5)
        work = work.iloc[start:].reset_index(drop=True)
    if max_matches:
        work = work.head(max_matches)

    records = []
    for _, row in work.iterrows():
        hist = df[df["date"] < row["date"]]
        if league:
            hist = hist[hist["league"] == league]
        if len(hist) < 4:
            continue
        hist_prod = adapt_to_prod_schema(hist)

        res = predict_one(
            row["home"], row["away"], hist_prod, league=row.get("league"),
            odds_h=row.get("odds_h"), odds_d=row.get("odds_d"), odds_a=row.get("odds_a"),
            flags=flags,
        )
        if res is None:
            continue

        actual = row.get("result", "")
        if actual not in ("H", "D", "A"):
            continue
        tip_to_res = {"1": "H", "X": "D", "2": "A"}
        correct = 1 if tip_to_res[res["tip"]] == actual else 0

        records.append({
            "run_tag": run_tag,
            "league": row.get("league", ""),
            "match_date": str(row["date"])[:10],
            "home": row["home"], "away": row["away"],
            "actual_res": actual,
            "tip": res["tip"], "pred_tip": res["tip"],
            "pred_conf": res["conf"],
            # Wektor musi byc TAKZE tutaj: ta funkcja jest swiadoma druga
            # implementacja tej samej petli i test porownuje ramki wiersz po
            # wierszu. Rozjazd zlapie sie natychmiast, i o to chodzi.
            "pw": res["pw"], "pr": res["pr"], "pp": res["pp"],
            "odds_h": row.get("odds_h"),
            "odds_d": row.get("odds_d"),
            "odds_a": row.get("odds_a"),
            "correct": correct,
            "no_odds": 1 if res["no_odds"] else 0,
        })

    return pd.DataFrame(records)


@pytest.mark.parametrize("use_bayesian", [False, True])
def test_run_walkforward_matches_reference_implementation(use_bayesian):
    """Parytet bit-identyczny: zoptymalizowana petla (searchsorted) == stara O(n^2)."""
    df = _hist_df_english(n_pairs=100)
    flags = ModelFlags(use_bayesian=use_bayesian, use_ensemble=True, use_calibration=False)

    new = run_walkforward(df, league="TEST", flags=flags, run_tag="t", verbose=False)
    ref = _run_walkforward_ref(df, league="TEST", flags=flags, run_tag="t", verbose=False)

    assert len(new) > 0
    pd.testing.assert_frame_equal(
        new.reset_index(drop=True), ref.reset_index(drop=True)
    )


def test_run_walkforward_zapisuje_pelny_wektor_prawdopodobienstw():
    """Brier wieloklasowy potrzebuje pw/pr/pp, nie samego `pred_conf`.

    `pred_conf` niesie prawdopodobienstwo TYPU WYBRANEGO; z niego nie da sie
    odtworzyc dwoch pozostalych wyjsc. Bez pelnego wektora kazdy pomiar jakosci
    prawdopodobienstw wymagalby powtorzenia calego replayu.
    """
    df = _hist_df_english()
    out = run_walkforward(df, league="TEST", flags=ModelFlags(
        use_bayesian=False, use_ensemble=True, use_calibration=False), verbose=False)
    assert {"pw", "pr", "pp"}.issubset(out.columns)
    assert out["pw"].between(0, 100).all()
    # Suma trzech wyjsc to caly rozklad 1X2 — odchylenie znaczy, ze ktores
    # ramie zwrocilo prawdopodobienstwa nieznormalizowane.
    sumy = out["pw"] + out["pr"] + out["pp"]
    assert sumy.between(99.0, 101.0).all(), f"rozklad nie sumuje sie do 100: {sumy.describe()}"


def test_run_walkforward_zachowuje_dotychczasowe_kolumny():
    """Dodanie wektora jest ADDYTYWNE — `wf_db` i raporty czytaja stare nazwy."""
    df = _hist_df_english()
    out = run_walkforward(df, league="TEST", flags=ModelFlags(
        use_bayesian=False, use_ensemble=True, use_calibration=False), verbose=False)
    assert {"tip", "pred_tip", "pred_conf", "correct", "match_date",
            "no_odds", "actual_res", "league"}.issubset(out.columns)


def test_run_walkforward_niesie_kurs_uzyty_do_predykcji():
    """Porównanie z rynkiem wymaga CENY, po której rynek wycenił ten mecz.

    Bez tych kolumn kurs trzeba doklejać joinem po (liga, data, gospodarz,
    gość) już PO przebiegu. Taki join jest cichy: kilka procent wierszy, które
    się nie dopasują, wypada z pomiaru bez śladu, a wypadają nielosowo (dziwne
    pisownie nazw), więc porównanie modelu z rynkiem robi się na przekrzywionej
    podpróbce. Kurs, którego użył `predict_one`, jest jedynym, o którym wiadomo,
    że dotyczy TEGO wiersza.
    """
    df = _hist_df_english()
    out = run_walkforward(df, league="TEST", flags=ModelFlags(
        use_bayesian=False, use_ensemble=False, use_calibration=False), verbose=False)
    assert {"odds_h", "odds_d", "odds_a"}.issubset(out.columns)
    # _hist_df_english wpisuje 1.9/3.4/4.0 w kazdy wiersz — kurs ma dojechac
    # nietkniety, a nie np. jako wynik devigu albo NaN po konwersji typow.
    assert (out["odds_h"] == 1.9).all()
    assert (out["odds_d"] == 3.4).all()
    assert (out["odds_a"] == 4.0).all()


def test_kurs_w_rekordzie_odtwarza_wektor_rynku():
    """Kurs z rekordu musi dać ten sam wektor rynku co devig na wejściu.

    To jest właściwość, dla której kolumny w ogóle dodajemy: `devig_1x2`
    policzony na kursie Z REKORDU ma być tym samym rozkładem, którego użył
    `predict_one` w środku pętli.
    """
    df = _hist_df_english()
    out = run_walkforward(df, league="TEST", flags=ModelFlags(
        use_bayesian=False, use_ensemble=False, use_calibration=False), verbose=False)
    wiersz = out.iloc[0]
    rynek = devig_1x2(wiersz["odds_h"], wiersz["odds_d"], wiersz["odds_a"])
    assert rynek is not None
    assert rynek == devig_1x2(1.9, 3.4, 4.0)
