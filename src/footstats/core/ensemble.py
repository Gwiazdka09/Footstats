import os

_DEFAULT_WEIGHTS = {"poisson": 0.70, "bzzoiro": 0.30}  # A/B 16.4: 70/30 minimalizuje log-loss (0.961 vs 1.027 przy 45/55)


def _env_market_weight() -> dict | None:
    """Globalny override wagi rynku przez env `ENSEMBLE_MARKET_WEIGHT` (0..1).

    Walk-forward A/B 06-25 (n=7934, OOS): przeważenie ku rynkowi monotonicznie podnosi
    trafność — 70/30→51.8%, 30/70→52.8%, 0/100→53.2% (rynek sharp, model dusił sygnał).
    Rekomendowane `ENSEMBLE_MARKET_WEIGHT=0.70` (=30/70, zostawia głos modelu na value).
    DEFAULT (env nieustawiony) = zachowanie obecne (per-league / 70/30) → zero zmiany prod.
    Flip dopiero PO walidacji (~88 fresh) — zmiana warstwy predykcji.
    """
    raw = os.getenv("ENSEMBLE_MARKET_WEIGHT", "").strip()
    if not raw:
        return None
    try:
        wb = float(raw)
    except ValueError:
        return None
    if not 0.0 <= wb <= 1.0:
        return None
    return {"poisson": round(1.0 - wb, 4), "bzzoiro": round(wb, 4)}


def get_weights_for_league(liga: str | None = None) -> dict:
    """Wagi ensemble (model/rynek). Kolejność: env override → default 70/30.

    NIE ładujemy już ensemble_optimizer.load_weights (ensemble_weights.json):
    optymalizator liczył wagi na FABRYKOWANYCH probach (p_poisson=conf*0.9,
    p_bzzoiro=conf*1.1 — nie realne wyjścia modeli), a wynik trafiał do live
    predykcji. Do czasu przeliczenia na realnych probach prod używa zwalidowanego
    A/B default 70/30 (lub env override). `liga` zostaje w sygnaturze — per-league
    wróci po realnej kalibracji. Moduł ensemble_optimizer zostaje (offline).
    """
    override = _env_market_weight()
    if override is not None:
        return override
    return _DEFAULT_WEIGHTS


def ensemble_probs(
    p_poisson: dict,
    p_bzzoiro: dict,
    wagi: dict | None = None,
    liga: str | None = None,
) -> dict:
    """Ważona średnia prawdopodobieństw z dwóch modeli. Liga → per-league weights."""
    w = wagi or get_weights_for_league(liga)
    wp = w.get("poisson", 0.45)
    wb = w.get("bzzoiro", 0.55)

    if not p_poisson and not p_bzzoiro:
        return {}

    all_keys = set(p_poisson.keys()) | set(p_bzzoiro.keys())
    result = {}

    for key in all_keys:
        has_p = key in p_poisson
        has_b = key in p_bzzoiro
        if has_p and has_b:
            total_w = wp + wb
            result[key] = (p_poisson[key] * wp + p_bzzoiro[key] * wb) / total_w
        elif has_p:
            result[key] = p_poisson[key]
        else:
            result[key] = p_bzzoiro[key]

    return result


def get_roznica(p_ensemble: dict, p_poisson: dict, p_bzzoiro: dict) -> float:
    """Maksymalna różnica między Poisson a Bzzoiro dla win/draw/loss."""
    keys = ["win", "draw", "loss"]
    max_diff = 0.0
    for k in keys:
        if k in p_poisson and k in p_bzzoiro:
            max_diff = max(max_diff, abs(p_poisson[k] - p_bzzoiro[k]))
    return max_diff
