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
# KOREKTA 22.08 wieczorem: pierwotnie ustawiono `gpt-oss-20b`, ale zmierzone na
# REALNYM prompcie okazal sie NIESTABILNY — w trzech probach zwrocil top3 o dlugosci
# 1, 1 i 0, a przy `reasoning_effort=medium` spalil caly budzet na rozumowanie
# i skonczyl na `finish_reason: length` bez tresci. Pusty `top3` to dokladnie ta
# awaria, ktora naprawiamy (przebieg konczy sie zerem predykcji).
#
# `openai/gpt-oss-120b` w tych samych warunkach: top3=3, po polsku, `stop`,
# ~1550 tokenow wyjscia. Limity konta (konsola Groq): 30 req/min, 1000 req/dzien,
# 8K tok/min, 200K tok/dzien — przy naszych 10-20 wywolaniach dziennie z zapasem.
GROQ_MODEL   = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_TAGS_URL = OLLAMA_URL.rsplit("/api/", 1)[0] + "/api/tags"
AI_PREFER_LOCAL = os.getenv("AI_PREFER_LOCAL", "0").strip() in ("1", "true", "True", "yes")

# ── Limity Groq free tier (2026-07, z nagłówków x-ratelimit-*) ──────────────────
#   Model                       req/dzień   tok/min   tok/dzień   typ
#   openai/gpt-oss-120b            1000       8000      200K       REASONING — WYBRANY
#   openai/gpt-oss-20b             1000       8000      200K       REASONING, gubi top3
#   groq/compound-mini              250      70000    bez limitu   dziala, ale zerze 2x tokenow
#   groq/compound                   250      70000    bez limitu   agentowy
#   qwen/qwen3.6-27b               1000       8000      200K       wycieka <think> do tresci
#   allam-2-7b                     7000       6000      500K       arabski
# (odczytane z console.groq.com/settings/limits, 22.08.2026 — plan darmowy)
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


# Zapas na narzut wiadomości po stronie dostawcy (role, separatory) — TPM liczy
# je razem z treścią, a nasze oszacowanie ich nie widzi.
_MARGINES_TPM = 200
# Poniżej tego odpowiedź jest bezużyteczna nawet z `_kontynuuj_uciety_json`.
_MIN_WYJSCIA = 400


def effective_max_tokens(base: int, model: str | None = None,
                         prompt_tokens: int | None = None) -> int:
    """
    Auto-skaluje max_tokens do wybranego modelu. Reasoning (gpt-oss/qwen3/r1...) →
    base × AI_REASONING_FACTOR (miejsce na myślenie + treść). Sufit ~75% tok/min
    (jeden call nie zjada całego limitu). Non-reasoning → base bez zmian.

    `prompt_tokens` — rozmiar WEJŚCIA (system + użytkownik). Bez niego sufit
    liczy się wyłącznie z wyjścia, a TPM obejmuje jedno i drugie. Zmierzone
    31.08 na produkcji: prompt systemowy typera waży 3045 tok, rezerwa wyjścia
    3750 tok, czyli 6795 z limitu 8000 znikało, ZANIM doszedł choć jeden mecz.
    Skutkiem było 413 przy trzech kandydatach i kupon zbudowany z modelu
    zamiast z LLM-a.

    Przycinanie promptu użytkownika tego nie naprawiało: wycinało opisy meczów,
    czyli jedyną rzecz, której model potrzebuje, i zostawiało balast.
    """
    m = model or GROQ_MODEL
    val = int(base * AI_REASONING_FACTOR) if _is_reasoning_model(m) else base
    ceiling = int(AI_TPM_LIMIT * 0.75)   # ~75% limitu tok/min = bezpieczny sufit

    if prompt_tokens is None:
        return max(base, min(val, ceiling))

    dostepne = AI_TPM_LIMIT - prompt_tokens - _MARGINES_TPM
    wynik = max(_MIN_WYJSCIA, min(val, ceiling, dostepne))
    if wynik < min(val, ceiling):
        logger.warning(
            "[AI] Budzet TPM: wejscie %d tok zjada limit %d — wyjscie sciete "
            "do %d (bez tego %d). Skroc prompt systemowy albo podnies tier.",
            prompt_tokens, AI_TPM_LIMIT, wynik, min(val, ceiling))
    return wynik


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
def parametry_modelu() -> dict:
    """
    Parametry wywołania Groqa zależne od WYBRANEGO modelu, w jednym miejscu.

    Zwraca `{"model": ...}` plus `reasoning_effort` dla rodziny `gpt-oss`.

    Po co osobna funkcja zamiast samej stałej `GROQ_MODEL`: nazwa modelu i jego
    wymagania to jedna decyzja, a rozdzielone rozjeżdżają się po cichu. Tak
    powstała awaria 16-22.08 (nazwa jako default w kodzie, potok stał 6 dni przy
    `exit=0`) i jej nawrót 31.08 — `ai/analyzer.py` miał własne, zaszyte
    `llama-3.1-8b-instant` i codziennie dostawał 404, a fallback to pochłaniał.

    Pilnuje tego `tests/test_model_groq_jedno_zrodlo.py`: nazwa modelu poza tym
    plikiem = czerwony test.
    """
    parametry: dict = {"model": GROQ_MODEL}
    # `gpt-oss` rozumuje przed odpowiedzia i placi za to z TEGO SAMEGO budzetu
    # wyjscia. Zmierzone 22.08: przy domyslnym wysilku 330 z 400 tokenow poszlo
    # na rozumowanie i odpowiedz urwala sie w polowie (`finish_reason: length`).
    # Przy `low` — 85 tokenow i pelny JSON. Parametr podajemy tylko modelom,
    # ktore go znaja: reszta odrzucilaby zadanie jako nieznane pole.
    if "gpt-oss" in GROQ_MODEL:
        parametry["reasoning_effort"] = "low"
    return parametry


def _groq_call_impl(klucz: str, prompt: str, max_tokens: int) -> str:
    """Inner Groq call with exponential backoff retry. Raises on failure."""
    import groq as groq_lib

    client = groq_lib.Groq(api_key=klucz)
    _p = parametry_modelu()
    resp = client.chat.completions.create(
        model=_p["model"],
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
        # Decyzja o `reasoning_effort` mieszka w `parametry_modelu()` — tutaj
        # tylko przekazana, żeby nie istniała w dwóch miejscach.
        **{k: v for k, v in _p.items() if k != "model"},
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
    "groq/compound-mini":     70000,
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

# I2 (28.08.2026): stala 1.4 zostaje WYLACZNIE jako awaryjny fallback, bo zadna
# stala nie obsluzy obu skrajnosci naraz. Zmierzone tokenizerem modelu:
#     szkielet PL     2.56 zn/tok   -> przy 1.4 przeszacowanie o 84%
#     diakrytyki      2.16 zn/tok
#     emoji + liczby  1.47 zn/tok   <- to dla NIEGO dobrano 1.4 po awarii 413
# Skutkiem przeszacowania nie jest 413, tylko przycinanie promptu bez potrzeby —
# czyli cicha utrata opisow meczow, ktorej nikt nie zglasza.
#
# `openai/gpt-oss-120b` (domyslny GROQ_MODEL) uzywa rodziny o200k, ktora tiktoken
# zna. Dla innych modeli licznik jest przyblizeniem — dlatego zostaje margines.
ENCODING_TOKENIZERA = os.getenv("AI_TOKENIZER_ENCODING", "o200k_base")

# Dostawca liczy tez narzut wiadomosci (role, separatory), ktorego w samym
# tekscie nie ma. Pomylka w DOL to 413 i padniety przebieg, pomylka w GORE to
# tylko wczesniejsze przyciecie — wiec zawyzamy swiadomie.
_MARGINES_TOKENIZERA = 1.05

# Enkoder laduje sie ~3.8 s przy pierwszym uzyciu (tiktoken ciagnie plik BPE
# z sieci). Cache jest OBOWIAZKOWY: bez niego kazde zapytanie do LLM-a w przebiegu
# placiloby te sekundy jeszcze raz. `False` znaczy "probowalismy i sie nie udalo" —
# rozne od `None` ("jeszcze nie probowalismy"), zeby nie ponawiac w kolko.
_enkoder: object | None | bool = None


def zeruj_enkoder() -> None:
    """Kasuje cache enkodera. Dla testow — stan modulowy przecieka miedzy nimi."""
    global _enkoder
    _enkoder = None


def _pobierz_enkoder():
    """Enkoder tiktokena albo None, gdy niedostepny. NIGDY nie rzuca.

    Licznik tokenow jest funkcja pomocnicza — jego awaria nie ma prawa wywrocic
    przebiegu ani go spowolnic. Brak paczki w obrazie i brak wyjscia na siec
    to dwa realne stany produkcyjne, oba konczace sie tu samo: heurystyka.
    """
    global _enkoder
    if _enkoder is not None:
        return _enkoder or None

    try:
        import tiktoken
        _enkoder = tiktoken.get_encoding(ENCODING_TOKENIZERA)
        return _enkoder
    except ImportError as e:
        logger.warning("[AI] tiktoken niedostepny (%s) — licznik tokenow spada na"
                       " heurystyke %.1f znaku/token, prompt moze byc przycinany"
                       " wczesniej niz trzeba", e, _ZNAKOW_NA_TOKEN)
    except Exception as e:                                   # noqa: BLE001
        # get_encoding potrafi paść na sieci, dysku i nieznanej nazwie encodingu.
        # Lista typow zalezy od wersji paczki, wiec lapiemy szeroko — ale GLOSNO.
        logger.warning("[AI] Nie udalo sie zaladowac tokenizera '%s' (%s: %s) —"
                       " licznik tokenow spada na heurystyke",
                       ENCODING_TOKENIZERA, type(e).__name__, e)
    _enkoder = False
    return None


def tpm_dla_modelu(model: str) -> int:
    """Limit tokenów na minutę dla modelu (wejście + wyjście łącznie)."""
    return _TPM_MODELI.get(model, _TPM_DOMYSLNY)


def szacuj_tokeny(tekst: str) -> int:
    """Liczba tokenów tekstu. Celowo zawyża — pomyłka w drugą stronę to 413.

    Liczy prawdziwym tokenizerem modelu, gdy `tiktoken` jest dostępny; w razie
    czego spada na starą heurystykę znak/token i mówi o tym w logu. Obie ścieżki
    zawyżają: pierwsza o `_MARGINES_TOKENIZERA` (narzut wiadomości po stronie
    dostawcy), druga z natury.
    """
    enkoder = _pobierz_enkoder()
    if enkoder is None:
        return int(len(tekst) / _ZNAKOW_NA_TOKEN) + 1
    try:
        return int(len(enkoder.encode(tekst)) * _MARGINES_TOKENIZERA) + 1
    except Exception as e:                                   # noqa: BLE001
        # Sam `encode` tez moze paść (np. na wejsciu, ktore nie jest tekstem).
        # Cisza tutaj zamienilaby dokladny licznik w heurystyke bez sladu.
        logger.warning("[AI] Tokenizer nie policzyl tekstu (%s: %s) —"
                       " heurystyka na tym wywolaniu", type(e).__name__, e)
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
    # Ile znaków mieści się w tokenie — liczone Z TEGO promptu, nie ze stałej.
    # Stała 1.4 była tu drugim źródłem przeszacowania: dla zwykłego polskiego
    # tekstu (2.5 zn/tok) przycinała do ~55% przyznanego budżetu, czyli wyrzucała
    # połowę opisów meczów bez powodu. Skutkiem nie jest 413, tylko cicha strata.
    znakow_na_token = len(prompt) / max(1, szacuj_tokeny(prompt))
    dostepne = max(0, int((budzet_tokenow - 1) * znakow_na_token) - len(znacznik))

    def _zloz(ile_znakow: int) -> str:
        glowa = ile_znakow * 2 // 3   # opisy meczów są na początku — zostaw więcej
        ogon = ile_znakow - glowa
        return prompt[:glowa] + znacznik + (prompt[-ogon:] if ogon else "")

    przyciety = _zloz(dostepne)
    # Weryfikacja zamiast wiary w przelicznik: gęstość tokenów nie jest równomierna
    # (emoji siedzą w opisach meczów, nie w instrukcji), więc oszacowanie ze średniej
    # potrafi chybić. Pomyłka w GÓRĘ to 413, więc dociskamy, aż się zmieści.
    for _ in range(8):
        if szacuj_tokeny(przyciety) <= budzet_tokenow or dostepne <= 0:
            break
        dostepne = int(dostepne * 0.85)
        przyciety = _zloz(dostepne)
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
