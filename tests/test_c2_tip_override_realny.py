"""C2 / Cel B bug 2 — override REALNEGO tipu (_nadpisz_tip_modelem) + backtest=live.

Wcześniej koryguj_tip_wg_modelu działał TYLKO w _auto_zapisz_backtest (shadow):
realny kupon dostawał słaby tip Groq, a backtest zapisywał override którego nigdy
nie postawiono (optymistyczne kłamstwo + kalibracja na fikcji). Teraz override
działa na realnym dane (gated flagą GROQ_TIP_OVERRIDE), a _auto_zapisz_backtest
zapisuje tip z dane verbatim → zgodność shadow↔live.
"""
from footstats.ai.analyzer_helpers import _nadpisz_tip_modelem, _auto_zapisz_backtest


def _wyniki():
    # Bayern faworytem: model dom 70 / remis 22 / wyjazd 8.
    return [{"gospodarz": "Bayern", "goscie": "Bochum",
             "pw": 70.0, "pr": 22.0, "pp": 8.0, "data": "2026-06-27",
             "liga": "Bundesliga", "pred": {}}]


def test_override_realnego_tipu_w_top3():
    # Groq tip=2 (wyjazd, prob modelu 8% < 15) → override na argmax "1".
    dane = {"top3": [{"mecz": "Bayern vs Bochum", "typ": "2", "pewnosc_pct": 65}]}
    _nadpisz_tip_modelem(dane, _wyniki())
    assert dane["top3"][0]["typ"] == "1"


def test_override_w_kuponie():
    # tip=2 (wyjazd 8% < 15) → override "1"; X=22% byłby akceptowalny (no-op).
    dane = {"kupon_a": {"zdarzenia": [{"mecz": "Bayern vs Bochum", "typ": "2"}]}}
    _nadpisz_tip_modelem(dane, _wyniki())
    assert dane["kupon_a"]["zdarzenia"][0]["typ"] == "1"


def test_brak_override_gdy_brak_prob():
    # Mecz spoza coverage (brak pw/pr/pp) → tip nietknięty.
    w = [{"gospodarz": "X", "goscie": "Y"}]
    dane = {"top3": [{"mecz": "X vs Y", "typ": "2"}]}
    _nadpisz_tip_modelem(dane, w)
    assert dane["top3"][0]["typ"] == "2"


def test_brak_override_gdy_tip_zgodny():
    # Wyjazd 40% = akceptowalne (>=15) → bez zmian.
    w = [{"gospodarz": "A", "goscie": "B", "pw": 30.0, "pr": 30.0, "pp": 40.0}]
    dane = {"top3": [{"mecz": "A vs B", "typ": "2"}]}
    _nadpisz_tip_modelem(dane, w)
    assert dane["top3"][0]["typ"] == "2"


def test_backtest_zapisuje_tip_z_dane_bez_wewnetrznego_override(monkeypatch):
    # _auto_zapisz_backtest NIE robi już własnego override — zapisuje tip z dane.
    zapisane = []
    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "save_prediction",
                        lambda **kw: zapisane.append(kw["ai_tip"]))

    # tip="2" NIE nadpisany; gdyby shadow robił override → zapisałby "1".
    dane = {"top3": [{"mecz": "Bayern vs Bochum", "typ": "2", "kurs": 3.5}]}
    _auto_zapisz_backtest(dane, _wyniki())
    assert zapisane == ["2"]
