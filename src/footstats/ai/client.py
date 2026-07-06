"""
ai_client.py – Klient AI dla FootStats
Priorytet: Groq (online, darmowy, 70B) → Ollama (lokalny, offline, 2B)
"""

import logging
import os
import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
from footstats.core.circuit_breaker import groq_circuit, ollama_circuit
from footstats.core.exceptions import FootStatsCircuitOpenError

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_TAGS_URL = OLLAMA_URL.rsplit("/api/", 1)[0] + "/api/tags"
AI_PREFER_LOCAL = os.getenv("AI_PREFER_LOCAL", "0").strip() in ("1", "true", "True", "yes")

# ── Limity Groq free tier (2026-07, z nagłówków x-ratelimit-*) ──────────────────
#   Model                       req/dzień   tok/min   typ
#   llama-3.1-8b-instant          14400      6000     szybki
#   llama-3.3-70b-versatile        1000     12000     mocny, non-reasoning
#   openai/gpt-oss-120b            1000      8000     REASONING (myśli→tokeny)
#   qwen/qwen3-32b                 1000      ~         REASONING (wycieka <think>)
# Pipeline: ~10-20 callów/dzień → req/dzień z ogromnym zapasem. tok/min ciasny ale
# calle rozłożone + retry/circuit-breaker obsługują 429.
#
# Modele REASONING zużywają tokeny na "myślenie" PRZED treścią → przy niskim
# max_tokens zwracają pusto/urwane. effective_max_tokens() auto-skaluje: reasoning
# model → base × AI_REASONING_FACTOR, cap na ~75% tok/min (bezpieczny sufit per call).
# Działa niezależnie od wybranego GROQ_MODEL.
_REASONING_HINTS = ("gpt-oss", "deepseek-r1", "-r1", "qwen3", "o1", "o3",
                    "reasoning", "think", "compound")
AI_TPM_LIMIT     = int(os.getenv("AI_TPM_LIMIT", "8000"))
AI_REASONING_FACTOR = float(os.getenv("AI_REASONING_FACTOR", "2.5"))


def _is_reasoning_model(model: str) -> bool:
    m = (model or "").lower()
    return any(h in m for h in _REASONING_HINTS)


def effective_max_tokens(base: int, model: str | None = None) -> int:
    """
    Auto-skaluje max_tokens do wybranego modelu. Reasoning (gpt-oss/qwen3/r1...) →
    base × AI_REASONING_FACTOR (miejsce na myślenie + treść). Sufit ~75% tok/min
    (jeden call nie zjada całego limitu). Non-reasoning → base bez zmian.
    """
    m = model or GROQ_MODEL
    val = int(base * AI_REASONING_FACTOR) if _is_reasoning_model(m) else base
    ceiling = int(AI_TPM_LIMIT * 0.75)   # ~75% limitu tok/min = bezpieczny sufit
    return max(base, min(val, ceiling))


def _ollama_available() -> bool:
    """Sprawdza czy Ollama running + model OLLAMA_MODEL dostępny."""
    try:
        r = requests.get(OLLAMA_TAGS_URL, timeout=2)
        if not r.ok:
            return False
        names = {m.get("name", "") for m in r.json().get("models", [])}
        return OLLAMA_MODEL in names
    except requests.RequestException:
        return False


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _groq_call_impl(klucz: str, prompt: str, max_tokens: int) -> str:
    """Inner Groq call with exponential backoff retry. Raises on failure."""
    import groq as groq_lib

    client = groq_lib.Groq(api_key=klucz)
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Jesteś ekspertem analitykiem piłkarskim. "
                    "Odpowiadasz zawsze po polsku. "
                    "Jeśli prosisz o JSON – zwracasz TYLKO JSON, bez żadnego tekstu przed ani po."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return resp.choices[0].message.content


def _groq(prompt: str, max_tokens: int = 600) -> str | None:
    """
    Odpytuje Groq API z exponential backoff. Zwraca tekst lub None.
    Obsługuje RateLimitError gracefully i circuit breaker.
    """
    klucz = os.getenv("GROQ_API_KEY", "").strip()
    if not klucz:
        return None

    if groq_circuit.is_open:
        logger.warning("[AI] Groq circuit OPEN — pomijam, przełączam na fallback")
        return None

    try:
        with groq_circuit:
            return _groq_call_impl(klucz, prompt, max_tokens)
    except FootStatsCircuitOpenError as e:
        logger.warning("[AI] %s", e)
        return None
    except Exception as e:  # noqa: broad-except — Groq SDK raises varied types incl. APIStatusError
        err_str = str(e).lower()
        if "429" in err_str or "rate_limit" in err_str or "too many requests" in err_str:
            logger.warning("[AI] Groq RateLimitError (429) — zwracam None")
        else:
            logger.error("[AI] Groq błąd po 3 retry: %s", e)
        return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _ollama_call_impl(prompt: str) -> str:
    """Inner Ollama call with exponential backoff retry. Raises on failure."""
    r = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("response", "")


def _ollama(prompt: str) -> str | None:
    """Odpytuje lokalną Ollamę z exponential backoff. Zwraca tekst lub None."""
    if ollama_circuit.is_open:
        logger.warning("[AI] Ollama circuit OPEN — pomijam")
        return None

    try:
        with ollama_circuit:
            return _ollama_call_impl(prompt)
    except FootStatsCircuitOpenError as e:
        logger.warning("[AI] %s", e)
        return None
    except (requests.RequestException, ValueError) as e:
        logger.error("[AI] Ollama błąd po 3 retry: %s", e)
        return None


def zapytaj_ai(prompt: str, max_tokens: int = 600) -> str:
    """
    Główna funkcja. Kolejność źródeł:
      AI_PREFER_LOCAL=1 → Ollama → Groq fallback
      domyślnie         → Groq → Ollama fallback
    Rzuca RuntimeError jeśli oba zawodzą.
    """
    groq_tokens = effective_max_tokens(max_tokens)  # auto-skala pod wybrany model
    if AI_PREFER_LOCAL and _ollama_available():
        odpowiedz = _ollama(prompt)
        if odpowiedz:
            logger.info("[AI] Źródło: Ollama (%s) [PREFER_LOCAL]", OLLAMA_MODEL)
            return odpowiedz
        # Fallback Groq jeśli Ollama padło
        odpowiedz = _groq(prompt, groq_tokens)
        if odpowiedz:
            logger.info("[AI] Źródło: Groq fallback (%s)", GROQ_MODEL)
            return odpowiedz
    else:
        odpowiedz = _groq(prompt, groq_tokens)
        if odpowiedz:
            logger.info("[AI] Źródło: Groq (%s)", GROQ_MODEL)
            return odpowiedz
        odpowiedz = _ollama(prompt)
        if odpowiedz:
            logger.info("[AI] Źródło: Ollama fallback (%s)", OLLAMA_MODEL)
            return odpowiedz

    raise RuntimeError(
        "Brak dostępnego AI. Sprawdź:\n"
        "  1. Klucz GROQ_API_KEY w pliku .env\n"
        "  2. Czy Ollama działa: ollama serve\n"
        f"  3. Czy model pobrany: ollama pull {OLLAMA_MODEL}\n"
        "  4. AI_PREFER_LOCAL=1 w .env aby preferować Ollama"
    )


# ── Szybki test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Test AI client...")
    try:
        odp = zapytaj_ai("Napisz jedno zdanie po polsku o piłce nożnej.", max_tokens=100)
        print(f"Odpowiedź: {odp}")
    except RuntimeError as e:
        print(f"BŁĄD: {e}")
