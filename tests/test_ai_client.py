"""test_ai_client.py — klient LLM: kolejność źródeł, circuit breaker, limity.

PO CO: na tej warstwie stoi całe AI w projekcie. Ma dwa źródła (Groq w chmurze,
Ollama lokalnie) i musi:

  * PRZEŁĄCZAĆ się na drugie, gdy pierwsze padnie — inaczej jedna awaria Groq
    zatrzymuje typowanie na cały dzień;
  * NIE UDAWAĆ sukcesu, gdy padną oba. Zwrócenie pustego stringa zamiast błędu
    byłoby najgorszym wyjściem: analiza poleciałaby dalej z pustką w miejscu,
    gdzie miały być typy;
  * SZANOWAĆ CIRCUIT BREAKER. Po serii awarii dobijanie się do martwego API
    tylko przedłuża blokadę i pali limity.

`effective_max_tokens` skaluje limit pod model rozumujący (gpt-oss/qwen3/r1),
bo taki zjada tokeny na „myślenie", zanim zacznie odpowiadać. Sufit 75% limitu
tok/min pilnuje, żeby jedno zapytanie nie zjadło całego budżetu minuty.
"""
from __future__ import annotations

import pytest
import requests

import footstats.ai.client as ac


# ── effective_max_tokens ────────────────────────────────────────────────────

@pytest.mark.parametrize("model", [
    "gpt-oss-120b", "deepseek-r1", "qwen3-32b", "o1-preview", "o3-mini",
    "compound-beta", "some-reasoning-model", "thinking-model",
])
def test_model_rozumujacy_dostaje_wiecej_tokenow(model):
    """Model rozumujący zjada tokeny na myślenie, zanim zacznie odpowiadać."""
    assert ac.effective_max_tokens(600, model) > 600


@pytest.mark.parametrize("model", ["llama-3.1-8b-instant", "mixtral-8x7b", "gemma2-9b"])
def test_model_zwykly_bez_zmian(model):
    assert ac.effective_max_tokens(600, model) == 600


def test_rozpoznanie_niewrazliwe_na_wielkosc_liter():
    assert ac.effective_max_tokens(600, "DeepSeek-R1") > 600


def test_sufit_nie_pozwala_zjesc_calej_minuty(monkeypatch):
    """Jedno zapytanie nie może wyczerpać limitu tokenów na minutę."""
    monkeypatch.setattr(ac, "AI_TPM_LIMIT", 8000)

    wynik = ac.effective_max_tokens(5000, "deepseek-r1")

    assert wynik <= int(8000 * 0.75)


def test_baza_nigdy_nie_maleje(monkeypatch):
    """Sufit nie może zejść PONIŻEJ tego, o co poproszono — obcięty prompt
    to gorsze niż przekroczony limit."""
    monkeypatch.setattr(ac, "AI_TPM_LIMIT", 100)

    assert ac.effective_max_tokens(600, "deepseek-r1") == 600


def test_brak_modelu_bierze_domyslny(monkeypatch):
    monkeypatch.setattr(ac, "GROQ_MODEL", "deepseek-r1")

    assert ac.effective_max_tokens(600) > 600


@pytest.mark.parametrize("model", ["", None])
def test_pusty_model_nie_wywala(model):
    assert ac._is_reasoning_model(model) is False


# ── _ollama_available ───────────────────────────────────────────────────────

class _Resp:
    def __init__(self, dane, ok=True):
        self.ok = ok
        self._dane = dane

    def json(self):
        return self._dane

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError("500")


@pytest.fixture
def siec(monkeypatch):
    stan = {"get": _Resp({"models": []}), "post": _Resp({"response": "ok"})}

    def fake_get(url, **kw):
        o = stan["get"]
        if isinstance(o, Exception):
            raise o
        return o

    def fake_post(url, **kw):
        o = stan["post"]
        if isinstance(o, Exception):
            raise o
        return o

    monkeypatch.setattr(ac.requests, "get", fake_get)
    monkeypatch.setattr(ac.requests, "post", fake_post)
    return stan


def test_ollama_dostepna_gdy_model_pobrany(siec, monkeypatch):
    monkeypatch.setattr(ac, "OLLAMA_MODEL", "qwen2.5:7b")
    siec["get"] = _Resp({"models": [{"name": "qwen2.5:7b"}]})

    assert ac._ollama_available() is True


def test_ollama_niedostepna_bez_modelu(siec, monkeypatch):
    """Serwer działa, ale bez naszego modelu — to nie jest dostępne źródło."""
    monkeypatch.setattr(ac, "OLLAMA_MODEL", "qwen2.5:7b")
    siec["get"] = _Resp({"models": [{"name": "llama3:8b"}]})

    assert ac._ollama_available() is False


def test_ollama_niedostepna_gdy_serwer_odmawia(siec):
    siec["get"] = _Resp({}, ok=False)

    assert ac._ollama_available() is False


def test_ollama_niedostepna_bez_sieci(siec):
    siec["get"] = requests.ConnectionError("refused")

    assert ac._ollama_available() is False


# ── _groq: brak klucza, circuit, rate limit ────────────────────────────────

@pytest.fixture
def obwody(monkeypatch):
    """Zamyka/otwiera circuit breakery bez czekania na realne awarie."""
    class _Obwod:
        def __init__(self):
            self.is_open = False

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    g, o = _Obwod(), _Obwod()
    monkeypatch.setattr(ac, "groq_circuit", g)
    monkeypatch.setattr(ac, "ollama_circuit", o)
    return {"groq": g, "ollama": o}


def test_brak_klucza_to_brak_groq(monkeypatch, obwody):
    monkeypatch.setenv("GROQ_API_KEY", "")

    assert ac._groq("prompt") is None


def test_otwarty_obwod_nie_probuje_groq(monkeypatch, obwody):
    """Dobijanie się do martwego API przedłuża blokadę i pali limity."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x")
    obwody["groq"].is_open = True
    monkeypatch.setattr(ac, "_groq_call_impl",
                        lambda *a: pytest.fail("wywołano API mimo otwartego obwodu"))

    assert ac._groq("prompt") is None


def test_groq_zwraca_odpowiedz(monkeypatch, obwody):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x")
    monkeypatch.setattr(ac, "_groq_call_impl", lambda k, p, m: "odpowiedz")

    assert ac._groq("prompt") == "odpowiedz"


@pytest.mark.parametrize("blad", [
    "Error code: 429 rate_limit_exceeded",
    "Too Many Requests",
    "RATE_LIMIT reached",
])
def test_limit_zapytan_to_none_nie_wyjatek(monkeypatch, obwody, blad):
    """Limit Groq ma zejść na fallback, nie wywalić całej analizy."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x")

    def wybucha(*a):
        raise RuntimeError(blad)

    monkeypatch.setattr(ac, "_groq_call_impl", wybucha)

    assert ac._groq("prompt") is None


def test_dowolny_blad_groq_to_none(monkeypatch, obwody):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x")

    def wybucha(*a):
        raise ValueError("cos zupelnie innego")

    monkeypatch.setattr(ac, "_groq_call_impl", wybucha)

    assert ac._groq("prompt") is None


# ── _ollama ────────────────────────────────────────────────────────────────

def test_otwarty_obwod_nie_probuje_ollamy(monkeypatch, obwody):
    obwody["ollama"].is_open = True
    monkeypatch.setattr(ac, "_ollama_call_impl",
                        lambda p: pytest.fail("wywołano API mimo otwartego obwodu"))

    assert ac._ollama("prompt") is None


def test_ollama_zwraca_odpowiedz(monkeypatch, obwody):
    monkeypatch.setattr(ac, "_ollama_call_impl", lambda p: "lokalna odpowiedz")

    assert ac._ollama("prompt") == "lokalna odpowiedz"


def test_blad_ollamy_to_none(monkeypatch, obwody):
    def wybucha(p):
        raise requests.ConnectionError("brak serwera")

    monkeypatch.setattr(ac, "_ollama_call_impl", wybucha)

    assert ac._ollama("prompt") is None


# ── zapytaj_ai: kolejność źródeł i twarda odmowa ───────────────────────────

@pytest.fixture
def zrodla(monkeypatch):
    """Podstawia oba źródła; zwraca uchwyt do sterowania i log wywołań."""
    stan = {"groq": "z groq", "ollama": "z ollama", "kolejnosc": [],
            "ollama_dostepna": True}

    def fake_groq(prompt, max_tokens=600):
        stan["kolejnosc"].append("groq")
        return stan["groq"]

    def fake_ollama(prompt):
        stan["kolejnosc"].append("ollama")
        return stan["ollama"]

    monkeypatch.setattr(ac, "_groq", fake_groq)
    monkeypatch.setattr(ac, "_ollama", fake_ollama)
    monkeypatch.setattr(ac, "_ollama_available", lambda: stan["ollama_dostepna"])
    monkeypatch.setattr(ac, "AI_PREFER_LOCAL", False)
    return stan


def test_domyslnie_najpierw_groq(zrodla):
    assert ac.zapytaj_ai("prompt") == "z groq"
    assert zrodla["kolejnosc"] == ["groq"]


def test_ollama_jako_zapas_gdy_groq_padnie(zrodla):
    """Jedna awaria Groq nie może zatrzymać typowania na cały dzień."""
    zrodla["groq"] = None

    assert ac.zapytaj_ai("prompt") == "z ollama"
    assert zrodla["kolejnosc"] == ["groq", "ollama"]


def test_prefer_local_odwraca_kolejnosc(zrodla, monkeypatch):
    monkeypatch.setattr(ac, "AI_PREFER_LOCAL", True)

    assert ac.zapytaj_ai("prompt") == "z ollama"
    assert zrodla["kolejnosc"] == ["ollama"]


def test_prefer_local_z_zapasem_groq(zrodla, monkeypatch):
    monkeypatch.setattr(ac, "AI_PREFER_LOCAL", True)
    zrodla["ollama"] = None

    assert ac.zapytaj_ai("prompt") == "z groq"
    assert zrodla["kolejnosc"] == ["ollama", "groq"]


def test_prefer_local_pomija_ollame_gdy_niedostepna(zrodla, monkeypatch):
    """Bez sprawdzenia dostępności każdy prompt czekałby na timeout lokalny."""
    monkeypatch.setattr(ac, "AI_PREFER_LOCAL", True)
    zrodla["ollama_dostepna"] = False

    assert ac.zapytaj_ai("prompt") == "z groq"
    assert zrodla["kolejnosc"] == ["groq"]


def test_oba_zrodla_padly_to_glosny_blad(zrodla):
    """NAJWAŻNIEJSZE: pusty string zamiast wyjątku puściłby analizę dalej
    z pustką w miejscu, gdzie miały być typy."""
    zrodla["groq"] = None
    zrodla["ollama"] = None

    with pytest.raises(RuntimeError, match="Brak dostępnego AI"):
        ac.zapytaj_ai("prompt")


def test_komunikat_bledu_mowi_co_sprawdzic(zrodla):
    zrodla["groq"] = None
    zrodla["ollama"] = None

    with pytest.raises(RuntimeError) as e:
        ac.zapytaj_ai("prompt")

    assert "GROQ_API_KEY" in str(e.value)
    assert "ollama serve" in str(e.value)


def test_limit_tokenow_skalowany_przed_wyslaniem(zrodla, monkeypatch):
    """Groq dostaje limit przeskalowany pod model, nie surową wartość."""
    przekazane = []
    monkeypatch.setattr(ac, "_groq",
                        lambda p, max_tokens=600: przekazane.append(max_tokens) or "ok")
    monkeypatch.setattr(ac, "GROQ_MODEL", "deepseek-r1")

    ac.zapytaj_ai("prompt", max_tokens=600)

    assert przekazane[0] > 600
