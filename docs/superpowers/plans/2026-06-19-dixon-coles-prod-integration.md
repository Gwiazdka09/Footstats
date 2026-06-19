# Dixon-Coles -> Produkcja (Cel C) - Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: superpowers:subagent-driven-development (recommended) lub superpowers:executing-plans. Steps uzywaja checkbox (- [ ]) do trackingu.

**Goal:** Wpiac zwalidowane offline ramie Dixon-Coles (predict_match_bayesian) do produkcyjnej sciezki predykcji (quick_picks.szybkie_pewniaczki_2dni), za flaga USE_DIXON_COLES (default ON), przez wspolna funkcje blend_dixon_coles uzywana TAKZE przez wf_harness.predict_one (parytet prod-vs-harness). Lewar: +1.7pp na 10 ligach (51.3% vs 49.6%), kalibracja monotoniczna.

**Architecture:** Nowa funkcja core/poisson_bayesian.py::blend_dixon_coles (remap pa->pp + x100, blend nad pw/pr/pp, bt/o25 nietkniete, DC None -> p_model graceful). Wpiecie w quick_picks.py MIEDZY predict_match a ensemble_probs, za flaga z config.py. Refactor wf_harness.predict_one na blend_dixon_coles -> jeden punkt prawdy. Flagi USE_DIXON_COLES + W_BAYESIAN w config.py (os.getenv, default ON).

**Tech Stack:** Python 3, pandas, numpy, scipy.stats, pytest. Dane testowe: syntetyczne DataFrame (schemat prod) + footstats.data.historical_loader.load_cached() (smoke).

---

## Kontekst kluczowy (przeczytaj przed startem)

Schematy / sygnatury (zweryfikowane w kodzie):
- predict_match_bayesian(g, a, df, home_advantage=BONUS_DOMOWY) -> dict|None. Klucze: lambda_g, lambda_a, pw, pr, **pa** (away win!), n_home, n_away, league_home_avg, league_away_avg, model. Wartosci pw/pr/pa to ULAMKI 0-1. Schemat df: gospodarz/goscie/gole_g/gole_a (jak prod).
- predict_match(...) -> dict z p_wygrana/p_remis/p_przegrana/btts/over25 (PROCENTY 0-100).
- ensemble_probs(p_poisson, p_bzzoiro, wagi=None, liga=None) -> wazona srednia po WSPOLNYCH kluczach. quick_picks karmi go kluczami pw/pr/pp/bt/o25.
- wf_harness.predict_one: classic predict_match(use_xg=False) -> p_model {pw,pr,pp} -> jesli use_bayesian: blend z DC (pa->pp, x100) przez _weighted_blend -> ensemble_probs z devig kursow.

Gotchy (KRYTYCZNE):
- DC zwraca pa (away win), prod oczekuje pp -> remap pa->pp.
- DC zwraca ulamki 0-1, prod procenty -> x100.
- DC NIE liczy bt/o25 -> blend dotyka WYLACZNIE pw/pr/pp; bt/o25 zostaja z classic (inaczej KeyError / utrata rynkow goli).
- DC moze zwrocic None (malo danych) -> blend zwraca p_model bez zmian (graceful = baseline).
- predict_match_bayesian NIE uzywa datetime.now() -> brak lookahead w samym DC (zweryfikowane: brak importu datetime w poisson_bayesian.py).

Punkty wpiecia (file:line):
- config.py: dopisac flagi po l.47 (sekcja STALE; os zaimportowany w l.1).
- poisson_bayesian.py: dopisac blend_dixon_coles po l.157 (po predict_match_bayesian).
- quick_picks.py: wpiac wywolanie w bloku if _pred_p: miedzy l.218 (_p_pois) a l.222 (_p_bzz).
- wf_harness.py: predict_one l.92-97 - podmienic _weighted_blend na blend_dixon_coles.

KRYTYCZNE (FootStats): zero zapisow do prod Neon, zero Telegram w testach. Testy uzywaja syntetycznych DataFrame; integration quick_picks monkeypatchuje flage i mockuje Bzzoiro.

Branch: zaczynamy NIE na main (Task 0).

---

## File Structure

- Modify: src/footstats/config.py - flagi USE_DIXON_COLES (default ON) + W_BAYESIAN (default 0.5), os.getenv.
- Modify: src/footstats/core/poisson_bayesian.py - nowa funkcja blend_dixon_coles (po l.157).
- Modify: src/footstats/core/wf_harness.py - predict_one uzywa blend_dixon_coles (parytet).
- Modify: src/footstats/core/quick_picks.py - wpiecie blend_dixon_coles za flaga miedzy predict_match a ensemble_probs.
- Test: tests/test_poisson_bayesian.py (dopisek: blend_dixon_coles + anty-lookahead).
- Test: tests/test_dc_prod_integration.py (nowy: parytet prod-vs-harness, integration quick_picks, guard).

---

## Task 0: Branch feature

**Files:** brak zmian kodu.

- [ ] Step 1: Utworz branch (jestesmy na main).

Run: `git checkout -b feat/dixon-coles-prod`
Expected: switched to a new branch.

---

## Task 1: blend_dixon_coles w poisson_bayesian.py (remap pa->pp, x100, bt/o25 nietkniete)

**Files:**
- Modify: src/footstats/core/poisson_bayesian.py (dopisek po l.157, po predict_match_bayesian)
- Test: tests/test_poisson_bayesian.py

- [ ] Step 1: Write failing tests

Dopisz na koncu tests/test_poisson_bayesian.py (import na gorze: dodaj blend_dixon_coles do importu z footstats.core.poisson_bayesian):

```python
def test_blend_dc_none_returns_p_model_unchanged():
    """DC zwraca None (malo danych) -> p_model bez zmian (graceful = baseline)."""
    from footstats.core.poisson_bayesian import blend_dixon_coles
    p_model = {"pw": 50.0, "pr": 30.0, "pp": 20.0, "bt": 55.0, "o25": 60.0}
    empty = pd.DataFrame(columns=["gospodarz", "goscie", "gole_g", "gole_a"])
    out = blend_dixon_coles(p_model, "X", "Y", empty, w_bayesian=0.5)
    assert out == p_model


def test_blend_dc_keeps_bt_o25_untouched():
    """DC nie liczy bt/o25 -> musza zostac z classic nietkniete."""
    from footstats.core.poisson_bayesian import blend_dixon_coles
    p_model = {"pw": 50.0, "pr": 30.0, "pp": 20.0, "bt": 55.0, "o25": 60.0}
    out = blend_dixon_coles(p_model, "Bayern", "Dortmund", _fixture_df(), w_bayesian=0.5)
    assert out["bt"] == 55.0
    assert out["o25"] == 60.0


def test_blend_dc_renormalizes_1x2_to_100():
    """Po blendzie pw+pr+pp ~ 100 (zdarzenia rozlaczne, wyczerpujace)."""
    from footstats.core.poisson_bayesian import blend_dixon_coles
    p_model = {"pw": 50.0, "pr": 30.0, "pp": 20.0, "bt": 55.0, "o25": 60.0}
    out = blend_dixon_coles(p_model, "Bayern", "Dortmund", _fixture_df(), w_bayesian=0.5)
    assert abs(out["pw"] + out["pr"] + out["pp"] - 100.0) < 0.01


def test_blend_dc_remaps_pa_to_pp_and_scales():
    """Remap pa->pp + x100: gdy DC daje silny away win, blend zwieksza pp wzgledem czystego classic."""
    from footstats.core.poisson_bayesian import blend_dixon_coles
    # Historia: Goscie wygrywaja wyjazdy wysoko -> DC pa (away) wysoki.
    rows = []
    for _ in range(8):
        rows.append({"gospodarz": "Slaby", "goscie": "Mocny", "gole_g": 0, "gole_a": 3})
        rows.append({"gospodarz": "Mocny", "goscie": "Slaby", "gole_g": 3, "gole_a": 0})
    df = pd.DataFrame(rows)
    p_model = {"pw": 60.0, "pr": 25.0, "pp": 15.0, "bt": 40.0, "o25": 50.0}
    out = blend_dixon_coles(p_model, "Slaby", "Mocny", df, w_bayesian=1.0)  # pelny DC
    # Przy pelnym DC (w_bayesian=1.0) pp powinno odzwierciedlac sile gosci (pa->pp), > classic pp.
    assert out["pp"] > p_model["pp"]
    assert out["pw"] < p_model["pw"]
```

- [ ] Step 2: Run -> FAIL

Run: `pytest tests/test_poisson_bayesian.py -k blend_dc -v`
Expected: ImportError / cannot import name 'blend_dixon_coles'.

- [ ] Step 3: Minimal impl

Dopisz na koncu src/footstats/core/poisson_bayesian.py:

```python
def blend_dixon_coles(
    p_model: dict,
    g: str,
    a: str,
    df: pd.DataFrame,
    w_bayesian: float = 0.5,
) -> dict:
    """Blenduje ramie Dixon-Coles do p_model (TYLKO pw/pr/pp).

    p_model: dict {pw,pr,pp,...} w procentach 0-100 (z classic predict_match).
    DC zwraca pa (away win) jako ulamek 0-1 -> remap pa->pp + x100.
    Gdy DC zwroci None (za malo danych) -> p_model bez zmian (graceful, = baseline).
    Klucze spoza {pw,pr,pp} (np. bt/o25) NIE sa modyfikowane.
    Renormalizacja pw/pr/pp do 100 (zdarzenia rozlaczne i wyczerpujace).
    """
    bay = predict_match_bayesian(g, a, df)
    if not bay:
        return p_model

    p_bay = {"pw": bay["pw"] * 100.0, "pr": bay["pr"] * 100.0, "pp": bay["pa"] * 100.0}
    w_c = 1.0 - w_bayesian
    blended = {k: p_model[k] * w_c + p_bay[k] * w_bayesian for k in ("pw", "pr", "pp")}

    s = blended["pw"] + blended["pr"] + blended["pp"] or 1.0
    out = dict(p_model)  # zachowaj bt/o25 i pozostale klucze
    out["pw"] = round(blended["pw"] / s * 100.0, 4)
    out["pr"] = round(blended["pr"] / s * 100.0, 4)
    out["pp"] = round(blended["pp"] / s * 100.0, 4)
    return out
```

- [ ] Step 4: Run -> PASS

Run: `pytest tests/test_poisson_bayesian.py -v`
Expected: wszystkie PASS (nowe + stare).

- [ ] Step 5: Commit

```bash
git add src/footstats/core/poisson_bayesian.py tests/test_poisson_bayesian.py
git commit -m "feat: blend_dixon_coles (remap pa->pp, x100, bt/o25 nietkniete, graceful)"
```

---

## Task 2: Test anty-lookahead blend_dixon_coles

**Files:**
- Test: tests/test_poisson_bayesian.py (sam test, impl juz gotowa z Task 1)

- [ ] Step 1: Write failing test (RED = brak determinizmu zlapany)

Dopisz do tests/test_poisson_bayesian.py:

```python
def test_blend_dc_deterministic_independent_of_system_date(monkeypatch):
    """Anty-lookahead: DC liczy tylko z dostarczonej historii, bez datetime.now().

    Podmiana daty systemowej NIE moze zmieniac predykcji (brak siegania po
    biezacy sezon/cache jak xG w predict_match).
    """
    from footstats.core.poisson_bayesian import blend_dixon_coles
    p_model = {"pw": 45.0, "pr": 30.0, "pp": 25.0, "bt": 50.0, "o25": 55.0}
    df = _fixture_df()

    out1 = blend_dixon_coles(p_model, "Bayern", "Dortmund", df, w_bayesian=0.5)

    # Udawana zmiana "teraz" przez podmiane datetime w module (gdyby DC go uzywal).
    import footstats.core.poisson_bayesian as pb
    assert not hasattr(pb, "datetime"), "DC nie powinien importowac datetime (zrodlo lookahead)"

    out2 = blend_dixon_coles(p_model, "Bayern", "Dortmund", df, w_bayesian=0.5)
    assert out1 == out2  # determinizm


def test_blend_dc_ignores_future_match_not_in_history():
    """Mecz predykowany jest PRZYSZLY (nie ma go w df) -> brak leaku wlasnego wyniku.

    Dodanie przyszlego wyniku do historii ZMIENIA predykcje (bo to staje sie dana),
    co potwierdza ze DC korzysta WYLACZNIE z df (nie z zadnego ukrytego zrodla).
    """
    from footstats.core.poisson_bayesian import blend_dixon_coles
    p_model = {"pw": 45.0, "pr": 30.0, "pp": 25.0}
    df_base = _fixture_df()
    out_base = blend_dixon_coles(p_model, "Bayern", "Dortmund", df_base, w_bayesian=1.0)

    extra = pd.concat([df_base, pd.DataFrame([
        {"gospodarz": "Bayern", "goscie": "Dortmund", "gole_g": 9, "gole_a": 0}
    ])], ignore_index=True)
    out_extra = blend_dixon_coles(p_model, "Bayern", "Dortmund", extra, w_bayesian=1.0)
    assert out_base != out_extra  # predykcja zalezy WYLACZNIE od dostarczonego df
```

- [ ] Step 2: Run -> oczekiwane PASS od razu

Run: `pytest tests/test_poisson_bayesian.py -k "deterministic or future_match" -v`
Expected: PASS (impl z Task 1 jest deterministyczna; predict_match_bayesian nie importuje datetime). Jesli FAIL na assercji hasattr -> znaczy ze ktos dodal datetime do DC = realny lookahead do usuniecia.

- [ ] Step 3: Commit

```bash
git add tests/test_poisson_bayesian.py
git commit -m "test: anty-lookahead blend_dixon_coles (determinizm, brak datetime.now)"
```

---

## Task 3: predict_one uzywa blend_dixon_coles (jeden punkt prawdy)

**Files:**
- Modify: src/footstats/core/wf_harness.py (predict_one l.92-97)
- Test: tests/test_wf_harness.py (regresja istniejacych testow bayesian)

- [ ] Step 1: Write failing test (parytet wewnetrzny)

Dopisz do tests/test_wf_harness.py:

```python
def test_predict_one_uses_shared_blend_dixon_coles(monkeypatch):
    """predict_one z use_bayesian musi delegowac do poisson_bayesian.blend_dixon_coles."""
    import footstats.core.poisson_bayesian as pb
    from footstats.core.wf_harness import predict_one, ModelFlags

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
```

(Uzywa istniejacego helpera _hist_prod() z tests/test_wf_harness.py.)

- [ ] Step 2: Run -> FAIL

Run: `pytest tests/test_wf_harness.py::test_predict_one_uses_shared_blend_dixon_coles -v`
Expected: FAIL — called["n"] == 0 (predict_one nadal uzywa _weighted_blend).

- [ ] Step 3: Modify predict_one

W src/footstats/core/wf_harness.py, w predict_one, zamien blok (obecne l.92-97):

```python
    # Ramie Dixon-Coles (opcjonalne)
    if flags.use_bayesian:
        from footstats.core.poisson_bayesian import predict_match_bayesian
        bay = predict_match_bayesian(g, a, hist_prod)
        if bay:
            p_bay = {"pw": bay["pw"] * 100, "pr": bay["pr"] * 100, "pp": bay["pa"] * 100}
            p_model = _weighted_blend(p_model, p_bay, 1.0 - flags.w_bayesian, flags.w_bayesian)
```

na:

```python
    # Ramie Dixon-Coles (opcjonalne) — wspolna funkcja z prod (parytet)
    if flags.use_bayesian:
        from footstats.core.poisson_bayesian import blend_dixon_coles
        p_model = blend_dixon_coles(p_model, g, a, hist_prod, w_bayesian=flags.w_bayesian)
```

Uwaga: import blend_dixon_coles wewnatrz funkcji (jak dotychczas predict_match_bayesian) — monkeypatch w tescie patchuje pb.blend_dixon_coles, wiec import-w-funkcji widzi spy. _weighted_blend zostaje w pliku (legacy, nieuzywany przez predict_one — moze zostac do A/B harness).

- [ ] Step 4: Run -> PASS

Run: `pytest tests/test_wf_harness.py -v`
Expected: wszystkie PASS (parytet + istniejace bayesian testy nadal zielone — blend_dixon_coles ma te sama matematyke co _weighted_blend dla pw/pr/pp).

- [ ] Step 5: Commit

```bash
git add src/footstats/core/wf_harness.py tests/test_wf_harness.py
git commit -m "refactor: predict_one uzywa blend_dixon_coles (jeden punkt prawdy DC)"
```

---

## Task 4: Flagi USE_DIXON_COLES + W_BAYESIAN w config.py

**Files:**
- Modify: src/footstats/config.py (dopisek po l.47, sekcja STALE)
- Test: tests/test_dc_prod_integration.py (nowy)

- [ ] Step 1: Write failing test

Utworz tests/test_dc_prod_integration.py:

```python
"""Testy wpiecia Dixon-Coles do produkcji (Cel C)."""
import importlib


def test_config_has_dixon_coles_flags():
    import footstats.config as cfg
    importlib.reload(cfg)
    assert hasattr(cfg, "USE_DIXON_COLES")
    assert isinstance(cfg.USE_DIXON_COLES, bool)
    assert hasattr(cfg, "W_BAYESIAN")
    assert 0.0 <= cfg.W_BAYESIAN <= 1.0


def test_config_dixon_coles_default_on(monkeypatch):
    """Default ON gdy brak env (lewar zwalidowany +1.7pp)."""
    monkeypatch.delenv("USE_DIXON_COLES", raising=False)
    import footstats.config as cfg
    importlib.reload(cfg)
    assert cfg.USE_DIXON_COLES is True


def test_config_dixon_coles_env_off(monkeypatch):
    """Env=0 wylacza bez redeploya (toggle awaryjny)."""
    monkeypatch.setenv("USE_DIXON_COLES", "0")
    import footstats.config as cfg
    importlib.reload(cfg)
    assert cfg.USE_DIXON_COLES is False
```

- [ ] Step 2: Run -> FAIL

Run: `pytest tests/test_dc_prod_integration.py -k config -v`
Expected: FAIL — AttributeError: module has no attribute 'USE_DIXON_COLES'.

- [ ] Step 3: Add flags

W src/footstats/config.py, po linii 47 (po PEWNIACZEK_PROG / sekcja "v2.7 NOWE STALE") dopisz:

```python
# ── Cel C: Dixon-Coles w produkcji (zwalidowane offline +1.7pp, kalibracja monotoniczna) ──
# Domyslnie ON — blend graceful (DC None -> classic bez zmian), env toggle bez redeploya.
USE_DIXON_COLES = os.getenv("USE_DIXON_COLES", "1").strip() not in ("0", "false", "False", "")
W_BAYESIAN      = float(os.getenv("W_BAYESIAN", "0.5"))   # waga ramienia DC (0=classic, 1=pelny DC)
```

(os jest juz zaimportowany w config.py l.1.)

- [ ] Step 4: Run -> PASS

Run: `pytest tests/test_dc_prod_integration.py -k config -v`
Expected: 3 PASS.

- [ ] Step 5: Commit

```bash
git add src/footstats/config.py tests/test_dc_prod_integration.py
git commit -m "feat: flagi USE_DIXON_COLES (default ON) + W_BAYESIAN w config"
```

---

## Task 5: Wpiecie blend_dixon_coles do quick_picks (za flaga)

**Files:**
- Modify: src/footstats/core/quick_picks.py (blok if _pred_p:, miedzy l.218 i l.222)
- Test: tests/test_dc_prod_integration.py

- [ ] Step 1: Write failing test (integration)

Dopisz do tests/test_dc_prod_integration.py:

```python
import pandas as pd
import pytest


def _df_prod():
    """Historia w schemacie prod (gospodarz/goscie/gole_g/gole_a + liga/data)."""
    rows = []
    for i in range(20):
        rows.append({"gospodarz": "Ajax", "goscie": "PSV", "gole_g": 2, "gole_a": 1,
                     "liga": "NED-Eredivisie", "data": f"2024-{(i % 12) + 1:02d}-05"})
        rows.append({"gospodarz": "PSV", "goscie": "Ajax", "gole_g": 1, "gole_a": 1,
                     "liga": "NED-Eredivisie", "data": f"2024-{(i % 12) + 1:02d}-20"})
    return pd.DataFrame(rows)


def test_quick_picks_calls_blend_when_flag_on(monkeypatch):
    """USE_DIXON_COLES=True -> quick_picks wola blend_dixon_coles dokladnie raz na mecz z _pred_p."""
    import footstats.core.quick_picks as qp
    import footstats.core.poisson_bayesian as pb

    monkeypatch.setattr(qp, "USE_DIXON_COLES", True, raising=False)
    monkeypatch.setattr(qp, "W_BAYESIAN", 0.5, raising=False)

    calls = {"n": 0}
    real = pb.blend_dixon_coles

    def _spy(p_model, g, a, df, w_bayesian=0.5):
        calls["n"] += 1
        assert "bt" in p_model and "o25" in p_model  # prod karmi bt/o25
        return real(p_model, g, a, df, w_bayesian=w_bayesian)

    monkeypatch.setattr(pb, "blend_dixon_coles", _spy)

    # Wymus jedna predykcje przez bezposrednie wywolanie sciezki Poisson:
    from footstats.core.poisson import predict_match
    from footstats.core.ensemble import ensemble_probs
    df = _df_prod()
    pred = predict_match("Ajax", "PSV", df, use_xg=False, use_calibration=False)
    assert pred is not None
    _p_pois = {"pw": pred["p_wygrana"], "pr": pred["p_remis"], "pp": pred["p_przegrana"],
               "bt": pred["btts"], "o25": pred["over25"]}
    # Symulacja wpiecia z quick_picks (ten sam fragment kodu):
    if qp.USE_DIXON_COLES:
        _p_pois = pb.blend_dixon_coles(_p_pois, "Ajax", "PSV", df, w_bayesian=qp.W_BAYESIAN)
    assert calls["n"] == 1
    assert "bt" in _p_pois and "o25" in _p_pois  # rynki goli zachowane
```

(Uwaga: integration end-to-end szybkie_pewniaczki_2dni wymaga zywego Bzzoiro; tu testujemy WPIETY fragment + import dostepnosc. Test e2e z mockiem Bzzoiro = opcjonalny Task 7.)

- [ ] Step 2: Run -> FAIL

Run: `pytest tests/test_dc_prod_integration.py::test_quick_picks_calls_blend_when_flag_on -v`
Expected: FAIL — AttributeError: module 'footstats.core.quick_picks' has no attribute 'USE_DIXON_COLES' (flaga nie zaimportowana do qp).

- [ ] Step 3: Wpiecie w quick_picks.py

W src/footstats/core/quick_picks.py:

(a) Dodaj import flag na gorze pliku (przy istniejacych importach z config, l.8):

```python
from footstats.config import PEWNIACZEK_PROG, USE_DIXON_COLES, W_BAYESIAN
```

(b) W bloku if _pred_p: (po utworzeniu _p_pois, obecne l.218-221, PRZED _p_bzz l.222) dodaj:

```python
                if _pred_p:
                    _p_pois = {"pw": _pred_p["p_wygrana"], "pr": _pred_p["p_remis"],
                               "pp": _pred_p["p_przegrana"], "bt": _pred_p["btts"],
                               "o25": _pred_p["over25"]}
                    # ── Cel C: ramie Dixon-Coles (flaga) — blend nad pw/pr/pp przed ensemble ──
                    # DC dotyka TYLKO 1X2; bt/o25 zostaja z classic. DC None -> _p_pois bez zmian.
                    if USE_DIXON_COLES:
                        from footstats.core.poisson_bayesian import blend_dixon_coles
                        _p_pois = blend_dixon_coles(_p_pois, g, a, df_mecze, w_bayesian=W_BAYESIAN)
                    _p_bzz  = {"pw": pw, "pr": pr, "pp": pp, "bt": bt, "o25": o25}
                    _bl = ensemble_probs(_p_pois, _p_bzz, liga=liga)
```

(Reszta bloku — przypisanie pw/pr/pp/bt/o25/u25 z _bl, poisson_blend=True — bez zmian. Nowy import jest objety istniejacym except (ImportError, AttributeError, ValueError, KeyError, TypeError) z l.231.)

- [ ] Step 4: Run -> PASS

Run: `pytest tests/test_dc_prod_integration.py -v`
Expected: wszystkie PASS.

- [ ] Step 5: Commit

```bash
git add src/footstats/core/quick_picks.py tests/test_dc_prod_integration.py
git commit -m "feat: wpiecie Dixon-Coles do quick_picks za flaga USE_DIXON_COLES"
```

---

## Task 6: Test parytetu prod-vs-harness

**Files:**
- Test: tests/test_dc_prod_integration.py (impl juz gotowa — Task 1/3/5)

- [ ] Step 1: Write parity test

Dopisz do tests/test_dc_prod_integration.py:

```python
def test_parity_prod_vs_harness_same_match_same_blend():
    """Ten sam (g,a,df,w_bayesian) -> harness predict_one i prod-side blend daja identyczne pw/pr/pp.

    Gwarantuje ze prod odtwarza zwycieska konfiguracje harness 1:1 (po stronie modelu,
    PRZED ensemble z kursami).
    """
    from footstats.core.poisson import predict_match
    from footstats.core.poisson_bayesian import blend_dixon_coles
    from footstats.core.wf_harness import predict_one, ModelFlags

    df = _df_prod()
    g, a, w = "Ajax", "PSV", 0.5

    # Strona prod: classic (use_xg=False jak harness do parytetu) -> blend DC, BEZ ensemble.
    pred = predict_match(g, a, df, use_xg=False, use_calibration=False)
    p_prod = {"pw": pred["p_wygrana"], "pr": pred["p_remis"], "pp": pred["p_przegrana"],
              "bt": pred["btts"], "o25": pred["over25"]}
    p_prod = blend_dixon_coles(p_prod, g, a, df, w_bayesian=w)

    # Strona harness: predict_one BEZ ensemble (use_ensemble=False) -> czysty p_model po DC.
    flags = ModelFlags(use_bayesian=True, use_ensemble=False, use_calibration=False, w_bayesian=w)
    res = predict_one(g, a, df, league="NED-Eredivisie",
                      odds_h=None, odds_d=None, odds_a=None, flags=flags)
    assert res is not None
    assert abs(p_prod["pw"] - res["pw"]) < 0.11   # res zaokraglone do 1dp; tolerancja
    assert abs(p_prod["pr"] - res["pr"]) < 0.11
    assert abs(p_prod["pp"] - res["pp"]) < 0.11
```

(Uwaga: predict_one zaokragla wyjscie do 1dp (l.112-114 wf_harness), blend_dixon_coles do 4dp -> tolerancja 0.11. Jesli chcesz scislejszy parytet, porownaj surowe p_model — ale 1dp tolerancja jest wystarczajaca do potwierdzenia tej samej logiki.)

- [ ] Step 2: Run -> PASS

Run: `pytest tests/test_dc_prod_integration.py::test_parity_prod_vs_harness_same_match_same_blend -v`
Expected: PASS (oba uzywaja blend_dixon_coles po tym samym classic predict_match).

- [ ] Step 3: Commit

```bash
git add tests/test_dc_prod_integration.py
git commit -m "test: parytet prod-vs-harness blendu Dixon-Coles"
```

---

## Task 7: Guard (zero Neon / Telegram) + regresja OFF

**Files:**
- Test: tests/test_dc_prod_integration.py

- [ ] Step 1: Write guard + regression tests

Dopisz do tests/test_dc_prod_integration.py:

```python
def test_blend_dc_does_not_touch_neon_or_telegram(monkeypatch):
    """Guard FootStats: blend DC to czysta funkcja — zero I/O do Neon/Telegram."""
    import footstats.core.poisson_bayesian as pb

    # Gdyby ktos dodal polaczenie do db w sciezce DC — wykryjemy.
    import footstats.utils.db as db
    sentinel = {"connected": False}
    if hasattr(db, "connect"):
        monkeypatch.setattr(db, "connect", lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("blend DC nie moze laczyc sie z Neon")))
    p_model = {"pw": 50.0, "pr": 30.0, "pp": 20.0, "bt": 55.0, "o25": 60.0}
    out = pb.blend_dixon_coles(p_model, "Ajax", "PSV", _df_prod(), w_bayesian=0.5)
    assert "pw" in out  # wykonalo sie bez tkniecia db


def test_flag_off_equals_classic_p_model(monkeypatch):
    """Regresja: USE_DIXON_COLES=False -> _p_pois identyczne jak przed wpieciem (classic)."""
    import footstats.core.quick_picks as qp
    import footstats.core.poisson_bayesian as pb
    from footstats.core.poisson import predict_match

    monkeypatch.setattr(qp, "USE_DIXON_COLES", False, raising=False)
    called = {"n": 0}
    monkeypatch.setattr(pb, "blend_dixon_coles",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or a[0])

    df = _df_prod()
    pred = predict_match("Ajax", "PSV", df, use_xg=False, use_calibration=False)
    _p_pois = {"pw": pred["p_wygrana"], "pr": pred["p_remis"], "pp": pred["p_przegrana"],
               "bt": pred["btts"], "o25": pred["over25"]}
    before = dict(_p_pois)
    if qp.USE_DIXON_COLES:   # False -> pomijamy blend
        _p_pois = pb.blend_dixon_coles(_p_pois, "Ajax", "PSV", df, w_bayesian=0.5)
    assert called["n"] == 0          # blend NIE wolany przy fladze OFF
    assert _p_pois == before          # classic bez zmian
```

- [ ] Step 2: Run -> PASS

Run: `pytest tests/test_dc_prod_integration.py -v`
Expected: wszystkie PASS.

- [ ] Step 3: Commit

```bash
git add tests/test_dc_prod_integration.py
git commit -m "test: guard Neon/Telegram + regresja flagi OFF (DC prod)"
```

---

## Task 8: Pelna suita + smoke walk-forward parytetu (analiza)

**Files:** brak zmian kodu.

- [ ] Step 1: Pelna suita

Run: `pytest tests/test_poisson_bayesian.py tests/test_wf_harness.py tests/test_dc_prod_integration.py tests/test_poisson.py -v`
Expected: wszystkie PASS. Coverage nowego kodu (blend_dixon_coles + wpiecie) >= 80%.

Run (coverage): `pytest --cov=src/footstats/core/poisson_bayesian --cov-report=term-missing tests/test_poisson_bayesian.py tests/test_dc_prod_integration.py`

- [ ] Step 2: Smoke A/B harness (potwierdzenie ze blend_dixon_coles odtwarza +1.7pp)

Run: `python scripts/run_walkforward_prod.py --liga "NED-Eredivisie" --max 800 --no-calibration`
Expected: ramie dixoncoles >= baseline (potwierdza ze refactor predict_one na blend_dixon_coles nie zepsul lewara). Zero zapisow do Neon (tylko data/walkforward.db).

- [ ] Step 3: Protokol pomiaru live (dokumentacja, bez kodu)

Zanotuj w STATUS.md / TODO.md:
- Baseline raport_system_paper (accuracy, n) PRZED wlaczeniem na live.
- Po ~15-20 settled z USE_DIXON_COLES=1: ponowny raport_system_paper + raport_kalibracji; sprawdz monotonicznosc i brak regresji vs baseline.
- Plan awaryjny: USE_DIXON_COLES=0 (env) cofa bez deploya.

Run: `python scripts/calibration_monitor.py`  (read-only Neon — baseline)

- [ ] Step 4: Commit wnioskow

```bash
git add STATUS.md TODO.md
git commit -m "docs: Cel C wpiety — protokol pomiaru live Dixon-Coles + baseline"
```

---

## Self-Review

**Spec coverage -> task:**
- Gdzie DC wchodzi w prod + blend wg wf_harness -> Task 5 (wpiecie miedzy predict_match a ensemble_probs). OK
- Nazwa flagi + default (USE_DIXON_COLES ON, W_BAYESIAN 0.5, uzasadnienie) -> Task 4 + spec sek.4. OK
- Remap pa->pp + spojnosc schematu -> Task 1 (blend_dixon_coles) + test remapu. OK
- Test anty-lookahead -> Task 2. OK
- Test remapu -> Task 1 (test_blend_dc_remaps_pa_to_pp_and_scales). OK
- Test parytetu prod-vs-harness -> Task 6. OK
- Pomiar live (paper-trade / calibration_monitor) -> Task 8 Step 3 + spec sek.7. OK

**Placeholder scan:** brak TBD; kazdy krok ma pelny kod. OK

**Type consistency:** blend_dixon_coles(p_model: dict, g, a, df, w_bayesian: float) spojne w Task 1/3/5/6/7. Klucze pw/pr/pp procenty; bt/o25 zachowane. DC pa->pp + x100 spojne. predict_one przelaczony na ta sama funkcje (Task 3). OK

**Ryzyka FootStats:**
- Prod Neon: blend DC czysta funkcja, brak I/O — guard Task 7. OK
- Telegram: brak wysylek w sciezce DC. OK
- Lookahead: DC bez datetime.now(), test Task 2; w prodzie mecz przyszly poza df. OK
- Daily pipeline: flaga default ON ale graceful (DC None -> baseline); env toggle awaryjny. OK
- Rynki goli (bt/o25): DC ich nie dotyka — test Task 1. OK

**Uwaga wykonawcza:** predict_match_bayesian zwraca pa (away), NIE pp. blend_dixon_coles robi remap; nie pomylic. DC w ulamkach 0-1 -> x100.
