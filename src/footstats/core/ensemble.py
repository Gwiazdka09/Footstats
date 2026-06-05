_DEFAULT_WEIGHTS = {"poisson": 0.45, "bzzoiro": 0.55}


def get_weights_for_league(liga: str | None = None) -> dict:
    """Return optimized per-league weights, fall back to default."""
    try:
        from footstats.core.ensemble_optimizer import load_weights
        return load_weights(liga)
    except (ImportError, ValueError, KeyError):
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
