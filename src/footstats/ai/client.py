"""
ai_client.py – Klient AI dla FootStats
Priorytet: Groq (online, darmowy, 70B) → Ollama (lokalny, offline, 2B)
"""

import logging
import os
import requests
from dotenv import load_dotenv
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential
from footstats.core.circuit_breaker import groq_circuit, ollama_circuit
from footstats.core.exceptions import FootStatsCircuitOpenError

load_dotenv()

logger = logging.getLogger(__name__)

# 22.08.2026: Groq WYCOFAL `llama-3.1-8b-instant` — API zwracalo 404 (NotFoundError),
# wiec KROK 3 nie dostawal odpowiedzi i caly dzienny przebieg konczyl sie zerem
# predykcji. Nie bylo o tym zadnego ostrzezenia poza naszym wlasnym alertem.
# `openai/gpt-oss-20b` zweryfikowany na realnym promptcie: pelny JSON (top3 +
# kupon_a..d + ostrzezenia), `finish_reason: stop`, odpowiedz po polsku.
GROQ_MODEL   = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
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
        # `gpt-oss` rozumuje przed odpowiedzia i placi za to z TEGO SAMEGO budzetu
        # wyjscia. Zmierzone: przy domyslnym wysilku 330 z 400 tokenow poszlo na
        # rozumowanie i odpowiedz urwala sie w polowie (`finish_reason: length`).
        # Przy `low` — 85 tokenow i pelny JSON. Parametr podajemy tylko modelom,
        # ktore go znaja: reszta odrzucilaby zadanie jako nieznane pole.
        **({"reasoning_effort": "low"} if "gpt-oss" in GROQ_MODEL else {}),
    )
    return resp.choices[0].message.content


# ── Budżet tokenów: limit TPM dotyczy SUMY wejścia i wyjścia ──────────────────
# 09.08.2026 job `footstats-final` padł na:
#   413 - Request too large for model `llama-3.1-8b-instant`, Limit 6000, Requested 8957
# Nikt nie pilnował rozmiaru promptu, a `AI_TPM_LIMIT` miał domyślnie 8000 —
# wartość niezgodną z domyślnym modelem. Prompt urósł, bo naprawiony filtr
# value-bet zaczął przepuszczać kandydatów (32 → 15 zamiast 0), więc opisów
# meczów zrobiło się realnie więcej. Limit trzeba znać PER MODEL i sprawdzać
# PRZED wysłaniem — odmowa kosztuje cały dzienny przebieg.
_TPM_MODELI = {
    "openai/gpt-oss-20b":      8000,
    "llama-3.1-8b-instant":    6000,   # wycofany przez Groqa 08.2026, zostawiony dla historii
    "llama-3.3-70b-versatile": 12000,
    "openai/gpt-oss-120b":     8000,
}
# Model spoza tabeli dostaje najostrożniejszy limit: lepiej wysłać za mało,
# niż zebrać 413 i stracić przebieg.
_TPM_DOMYSLNY = 6000

# Zapas na niedoszacowanie licznika tokenów po stronie dostawcy.
_MARGINES_TOKENOW = 200

# ZMIERZONE na realnym promptcie produkcyjnym (09.08.2026): Groq naliczył 8957
# tokenów przy prompcie, który mieścił się w budżecie 4300 liczonym po 3 znaki
# na token — czyli realny stosunek to ~1.4 znaku na token, nie 3. Powód: polskie
# diakrytyki, gęste liczby i emoji (🏅⚔️😫🔄) w opisach meczów; emoji potrafi
# zająć 3-4 tokeny przy jednym-dwóch znakach. Przy 3 guard przepuścił prompt
# nietknięty i job padł drugi raz na tym samym 413.
_ZNAKOW_NA_TOKEN = float(os.getenv("AI_ZNAKOW_NA_TOKEN", "1.4"))


def tpm_dla_modelu(model: str) -> int:
    """Limit tokenów na minutę dla modelu (wejście + wyjście łącznie)."""
    return _TPM_MODELI.get(model, _TPM_DOMYSLNY)


def szacuj_tokeny(tekst: str) -> int:
    """Zgrubna liczba tokenów. Celowo zawyża — pomyłka w drugą stronę to 413."""
    return int(len(tekst) / _ZNAKOW_NA_TOKEN) + 1


def dopasuj_do_budzetu(prompt: str, budzet_tokenow: int) -> str:
    """Skraca prompt do budżetu, zachowując POCZĄTEK i KONIEC.

    Instrukcja zadania stoi na początku, a wymagany format odpowiedzi na końcu —
    ucięcie któregokolwiek zamienia odpowiedź w śmieci. Wycinamy więc środek,
    gdzie siedzą opisy kolejnych meczów, i zostawiamy jawny znacznik: model musi
    wiedzieć, że czegoś nie dostał, inaczej dopowie sobie brakujące.
    """
    if szacuj_tokeny(prompt) <= budzet_tokenow:
        return prompt

    znacznik = "\n\n[…część meczów pominięta, bo prompt przekraczał limit modelu…]\n\n"
    # `szacuj_tokeny` zaokrągla w górę (+1), więc budżet znakowy liczymy od
    # `budzet - 1`. Bez tego wynik wychodzi o jeden token ponad limit — a to
    # dokładnie ten jeden token, przez który dostaje się 413.
    dostepne = max(0, int((budzet_tokenow - 1) * _ZNAKOW_NA_TOKEN) - len(znacznik))
    glowa = dostepne * 2 // 3          # opisy meczów są na początku — zostaw więcej
    ogon = dostepne - glowa

    przyciety = prompt[:glowa] + znacznik + (prompt[-ogon:] if ogon else "")
    logger.error(
        "[AI] Prompt przekraczal budzet (%d > %d tokenow) — przyciety do %d. "
        "Zmniejsz liczbe opisywanych meczow albo dlugosc lekcji.",
        szacuj_tokeny(prompt), budzet_tokenow, szacuj_tokeny(przyciety),
    )
    return przyciety


def _groq(prompt: str, max_tokens: int = 600, _proba_ponowna: bool = False) -> str | None:
    """
    Odpytuje Groq API z exponential backoff. Zwraca tekst lub None.
    Obsługuje RateLimitError gracefully i circuit breaker.

    `_proba_ponowna` pilnuje, żeby skrócenie promptu po 413 zdarzyło się RAZ —
    inaczej seria odmów mogłaby ciąć prompt w nieskończoność.
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
    except Exception as e:  # noqa: BLE001 — Groq SDK raises varied types incl. APIStatusError
        err_str = str(e).lower()
        if "413" in err_str or "request too large" in err_str:
            # Szacunek tokenów jest zgrubny z definicji — tokenizera Groqa nie
            # mamy lokalnie. Zamiast ufać własnej arytmetyce, bierzemy odpowiedź
            # od źródła prawdy: skoro odmówił, tniemy o połowę i próbujemy raz.
            # Bez tego cały dzienny przebieg przepada przez jedno zapytanie
            # (dwie takie awarie 09.08.2026).
            if _proba_ponowna:
                logger.error("[AI] Groq 413 nawet po skroceniu promptu — poddaje sie")
                return None
            krotszy = dopasuj_do_budzetu(prompt, szacuj_tokeny(prompt) // 2)
            logger.warning("[AI] Groq 413 — ponawiam z promptem krotszym o polowe")
            return _groq(krotszy, max_tokens, _proba_ponowna=True)
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
    except (RetryError, requests.RequestException, ValueError) as e:
        # `RetryError` MUSI tu być: tenacity opakowuje porażkę w swój typ, spoza
        # listy `requests`. Bez tego 09.08.2026 wyjątek przeleciał przez
        # `zapytaj_ai` i wywalił CAŁY dzienny przebieg (`exit(1)`, zero
        # predykcji) — zamiast zdegradować się do braku odpowiedzi. Ollamy nie
        # ma w kontenerze i nigdy nie będzie, więc to ścieżka gwarantowana.
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

    # Limit TPM obejmuje wejście I wyjście, więc budżet promptu to limit modelu
    # minus zarezerwowane wyjście i margines. Sprawdzamy PRZED wysłaniem: odmowa
    # 413 kosztuje cały przebieg, a nie jedno zapytanie.
    budzet = tpm_dla_modelu(GROQ_MODEL) - groq_tokens - _MARGINES_TOKENOW
    if budzet > 0:
        prompt = dopasuj_do_budzetu(prompt, budzet)

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
