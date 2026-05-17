"""
ai_client.py – Klient AI dla FootStats
Priorytet: Groq (online, darmowy, 70B) → Ollama (lokalny, offline, 2B)
"""

import logging
import os
import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
from footstats.utils.console import console
from footstats.core.circuit_breaker import groq_circuit, ollama_circuit
from footstats.core.exceptions import FootStatsCircuitOpenError

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_MODEL   = "llama-3.1-8b-instant"
OLLAMA_MODEL = "gemma2:2b"
OLLAMA_URL   = "http://localhost:11434/api/generate"


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
    except Exception as e:
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
        timeout=120,
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
    except Exception as e:
        logger.error("[AI] Ollama błąd po 3 retry: %s", e)
        return None


def zapytaj_ai(prompt: str, max_tokens: int = 600) -> str:
    """
    Główna funkcja. Najpierw próbuje Groq, potem Ollama.
    Rzuca RuntimeError jeśli oba zawodzą.
    """
    odpowiedz = _groq(prompt, max_tokens)
    if odpowiedz:
        logger.info("[AI] Źródło: Groq (%s)", GROQ_MODEL)
        return odpowiedz

    odpowiedz = _ollama(prompt)
    if odpowiedz:
        logger.info("[AI] Źródło: Ollama (%s)", OLLAMA_MODEL)
        return odpowiedz

    raise RuntimeError(
        "Brak dostępnego AI. Sprawdź:\n"
        "  1. Klucz GROQ_API_KEY w pliku .env\n"
        "  2. Czy Ollama działa: ollama serve\n"
        "  3. Czy model pobrany: ollama pull gemma2:2b"
    )


# ── Szybki test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Test AI client...")
    try:
        odp = zapytaj_ai("Napisz jedno zdanie po polsku o piłce nożnej.", max_tokens=100)
        print(f"Odpowiedź: {odp}")
    except RuntimeError as e:
        print(f"BŁĄD: {e}")
