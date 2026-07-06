"""
test_effective_max_tokens.py — auto-skala max_tokens pod wybrany model. Reasoning
(gpt-oss/qwen3/r1) zużywa tokeny na myślenie → potrzebuje więcej, inaczej pusto.
Działa niezależnie od GROQ_MODEL. Sufit ~75% tok/min.
"""
from footstats.ai.client import effective_max_tokens, _is_reasoning_model


def test_non_reasoning_bez_zmian():
    assert effective_max_tokens(500, model="llama-3.1-8b-instant") == 500
    assert effective_max_tokens(300, model="llama-3.3-70b-versatile") == 300


def test_reasoning_skaluje_w_gore():
    # gpt-oss reasoning → ×2.5
    assert effective_max_tokens(500, model="openai/gpt-oss-120b") == 1250
    assert effective_max_tokens(300, model="openai/gpt-oss-120b") == 750


def test_reasoning_niski_base_podbity():
    # base 100 (health-check) → 250, nie zostaje 100 (reasoning by się urwał)
    assert effective_max_tokens(100, model="openai/gpt-oss-120b") == 250


def test_sufit_75pct_tpm():
    # base 3000 reasoning → 7500 ale cap = 75% * 8000 = 6000
    assert effective_max_tokens(3000, model="openai/gpt-oss-120b") == 6000


def test_detekcja_reasoning():
    for m in ("openai/gpt-oss-120b", "qwen/qwen3-32b", "deepseek-r1-distill-llama-70b"):
        assert _is_reasoning_model(m) is True
    for m in ("llama-3.1-8b-instant", "llama-3.3-70b-versatile", "qwen2.5:7b"):
        assert _is_reasoning_model(m) is False


def test_nigdy_ponizej_base():
    # non-reasoning nie schodzi poniżej base
    assert effective_max_tokens(1500, model="llama-3.3-70b-versatile") == 1500
