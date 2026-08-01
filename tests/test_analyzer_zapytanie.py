"""test_analyzer_zapytanie.py — warstwa zapytań do Groq w `ai/analyzer.py`.

PO CO: to jest miejsce, w którym model zamienia dane meczu na TYPY. Trzy rzeczy
psują się tu po cichu, bez żadnego wyjątku:

  * ODPOWIEDŹ UCIĘTA na limicie tokenów — `finish_reason == "length"`. JSON bez
    domknięcia nie sparsuje się i cała analiza przepada. Stąd dopytywanie
    o dalszy ciąg; gdyby zawiodło, trzeba ZACHOWAĆ część już otrzymaną, a nie
    wyrzucić ją razem z błędem.
  * KALIBRACJA I STATYSTYKI LIG doklejane do promptu systemowego. Gdyby przestały
    się doklejać, model dalej odpowiada — tylko gorzej, i nikt tego nie zauważy.
  * BRAK KLUCZA. Ma być głośny błąd, nie cicha degradacja do słabszej ścieżki.

`_pobierz_podobne_mecze` (RAG) jest odwrotnie: ma być CICHY. To kontekst
opcjonalny, jego awaria nie może zabić predykcji.
"""
from __future__ import annotations

import pytest

import footstats.ai.analyzer as an


class _Wiadomosc:
    def __init__(self, tresc):
        self.content = tresc


class _Wybor:
    def __init__(self, tresc, finish_reason="stop"):
        self.message = _Wiadomosc(tresc)
        self.finish_reason = finish_reason


class _Odpowiedz:
    def __init__(self, tresc, finish_reason="stop"):
        self.choices = [_Wybor(tresc, finish_reason)]


class _Completions:
    def __init__(self, odpowiedzi):
        self._odpowiedzi = list(odpowiedzi)
        self.wywolania: list[dict] = []

    def create(self, **kw):
        self.wywolania.append(kw)
        o = self._odpowiedzi.pop(0)
        if isinstance(o, Exception):
            raise o
        return o


class _Klient:
    def __init__(self, *odpowiedzi):
        self.chat = type("_Chat", (), {})()
        self.chat.completions = _Completions(odpowiedzi)


@pytest.fixture
def groq(monkeypatch):
    """Podstawia bibliotekę groq; zwraca uchwyt do podłożenia odpowiedzi."""
    stan: dict = {"klient": None}

    class _FakeGroqLib:
        @staticmethod
        def Groq(api_key: str):
            stan["klucz"] = api_key
            return stan["klient"]

    monkeypatch.setitem(__import__("sys").modules, "groq", _FakeGroqLib)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_testowy")
    monkeypatch.setattr(an, "_get_kalibracja_blok", lambda: "")
    monkeypatch.setattr(an, "_get_liga_statystyki_blok", lambda: "")
    return stan


# ── brak klucza ─────────────────────────────────────────────────────────────

def test_brak_klucza_to_glosny_blad(monkeypatch):
    """Cicha degradacja znaczyłaby gorsze typy bez śladu w logach."""
    monkeypatch.setenv("GROQ_API_KEY", "")

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        an._zapytaj_typera("prompt")


def test_sam_bialy_znak_to_tez_brak_klucza(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "   ")

    with pytest.raises(RuntimeError):
        an._zapytaj_typera("prompt")


# ── ścieżka podstawowa ──────────────────────────────────────────────────────

def test_zwraca_odpowiedz_modelu(groq):
    groq["klient"] = _Klient(_Odpowiedz('{"top3": []}'))

    assert an._zapytaj_typera("prompt") == '{"top3": []}'


def test_prompt_uzytkownika_trafia_do_zapytania(groq):
    groq["klient"] = _Klient(_Odpowiedz("ok"))

    an._zapytaj_typera("Legia vs Lech")

    wiadomosci = groq["klient"].chat.completions.wywolania[0]["messages"]
    assert wiadomosci[-1] == {"role": "user", "content": "Legia vs Lech"}


def test_limit_tokenow_przekazany(groq):
    groq["klient"] = _Klient(_Odpowiedz("ok"))

    an._zapytaj_typera("prompt", max_tokens=1234)

    assert groq["klient"].chat.completions.wywolania[0]["max_tokens"] == 1234


# ── kalibracja i statystyki lig w prompcie systemowym ───────────────────────

def test_kalibracja_doklejona_do_systemu(groq, monkeypatch):
    monkeypatch.setattr(an, "_get_kalibracja_blok", lambda: "trafnosc 55% przy conf>80")
    groq["klient"] = _Klient(_Odpowiedz("ok"))

    an._zapytaj_typera("prompt")

    system = groq["klient"].chat.completions.wywolania[0]["messages"][0]["content"]
    assert "trafnosc 55% przy conf>80" in system
    assert "KALIBRACJA" in system


def test_statystyki_lig_doklejone_do_systemu(groq, monkeypatch):
    monkeypatch.setattr(an, "_get_liga_statystyki_blok", lambda: "Ekstraklasa: over 2.5 w 48%")
    groq["klient"] = _Klient(_Odpowiedz("ok"))

    an._zapytaj_typera("prompt")

    system = groq["klient"].chat.completions.wywolania[0]["messages"][0]["content"]
    assert "Ekstraklasa: over 2.5 w 48%" in system


def test_puste_bloki_nie_smieca_systemu(groq):
    groq["klient"] = _Klient(_Odpowiedz("ok"))

    an._zapytaj_typera("prompt")

    system = groq["klient"].chat.completions.wywolania[0]["messages"][0]["content"]
    assert "KALIBRACJA" not in system


# ── ucięta odpowiedź ────────────────────────────────────────────────────────

def test_ucieta_odpowiedz_jest_dokanczana(groq):
    """JSON bez domknięcia nie sparsuje się — cała analiza by przepadła."""
    groq["klient"] = _Klient(
        _Odpowiedz('{"top3": [{"mecz":', finish_reason="length"),
        _Odpowiedz(' "Legia vs Lech"}]}'),
    )

    wynik = an._zapytaj_typera("prompt")

    assert wynik == '{"top3": [{"mecz": "Legia vs Lech"}]}'
    assert len(groq["klient"].chat.completions.wywolania) == 2


def test_pelna_odpowiedz_nie_jest_dokanczana(groq):
    """Zbędne dopytanie to podwójny koszt zapytania."""
    groq["klient"] = _Klient(_Odpowiedz('{"top3": []}'))

    an._zapytaj_typera("prompt")

    assert len(groq["klient"].chat.completions.wywolania) == 1


def test_dokanczanie_widzi_wczesniejsza_rozmowe(groq):
    """Bez oryginalnego promptu model nie wie, co ma dokończyć."""
    groq["klient"] = _Klient(
        _Odpowiedz("czesc pierwsza", finish_reason="length"),
        _Odpowiedz(" i druga"),
    )

    an._zapytaj_typera("oryginalny prompt")

    wiadomosci = groq["klient"].chat.completions.wywolania[1]["messages"]
    role = [w["role"] for w in wiadomosci]
    assert role == ["system", "user", "assistant", "user"]
    assert wiadomosci[2]["content"] == "czesc pierwsza"


def test_nieudane_dokanczanie_zachowuje_czesc_otrzymana():
    """Odrzucenie części już opłaconej byłoby stratą bez powodu."""
    klient = _Klient(AttributeError("padlo"))

    wynik = an._kontynuuj_uciety_json(klient, [{"role": "user", "content": "x"}], "czesc")

    assert wynik == "czesc"


def test_dokanczanie_skleja_bez_separatora():
    klient = _Klient(_Odpowiedz("DRUGA"))

    wynik = an._kontynuuj_uciety_json(klient, [], "PIERWSZA")

    assert wynik == "PIERWSZADRUGA"


# ── awaria Groq ─────────────────────────────────────────────────────────────

def test_awaria_groq_schodzi_na_zapasowy_klient(groq, monkeypatch):
    """Typy z gorszego modelu są lepsze niż brak typów."""
    groq["klient"] = _Klient(RuntimeError("503 service unavailable"))
    monkeypatch.setattr(an, "zapytaj_ai", lambda p, mt: f"zapasowy:{p}")

    assert an._zapytaj_typera("prompt") == "zapasowy:prompt"


def test_brak_biblioteki_groq_schodzi_na_zapasowy(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_testowy")
    monkeypatch.setattr(an, "_get_kalibracja_blok", lambda: "")
    monkeypatch.setattr(an, "_get_liga_statystyki_blok", lambda: "")
    monkeypatch.setitem(__import__("sys").modules, "groq", None)
    monkeypatch.setattr(an, "zapytaj_ai", lambda p, mt: "zapasowy")

    assert an._zapytaj_typera("prompt") == "zapasowy"


# ── RAG: kontekst opcjonalny, ma być CICHY ──────────────────────────────────

@pytest.fixture
def wnioski(monkeypatch):
    stan = {"lista": []}
    import footstats.ai.post_match_analyzer as pma
    monkeypatch.setattr(pma, "pobierz_ostatnie_wnioski", lambda n: stan["lista"])
    return stan


def test_podobne_mecze_po_gospodarzu(wnioski):
    wnioski["lista"] = ["Legia przegrala mimo wysokiej pewnosci", "Arka: over trafiony"]

    wynik = an._pobierz_podobne_mecze("Legia", "Lech")

    assert "Legia przegrala" in wynik
    assert "Arka" not in wynik


def test_podobne_mecze_po_gosciach(wnioski):
    wnioski["lista"] = ["Lech: forma wyjazdowa slabsza"]

    assert "Lech" in an._pobierz_podobne_mecze("Legia", "Lech")


def test_dopasowanie_niewrazliwe_na_wielkosc_liter(wnioski):
    wnioski["lista"] = ["LEGIA warszawa - wniosek"]

    assert an._pobierz_podobne_mecze("legia", "Lech") != ""


def test_limit_liczby_wnioskow(wnioski):
    wnioski["lista"] = [f"Legia wniosek {i}" for i in range(5)]

    wynik = an._pobierz_podobne_mecze("Legia", "Lech", n=2)

    assert wynik.count("Legia wniosek") == 2


def test_brak_dopasowan_to_pusty_string(wnioski):
    """Pusty nagłówek w prompcie to szum, nie kontekst."""
    wnioski["lista"] = ["Arka: cos tam"]

    assert an._pobierz_podobne_mecze("Legia", "Lech") == ""


def test_brak_wnioskow_to_pusty_string(wnioski):
    assert an._pobierz_podobne_mecze("Legia", "Lech") == ""


def test_wnioski_przyciete_do_stu_znakow(wnioski):
    wnioski["lista"] = ["Legia " + "x" * 300]

    wynik = an._pobierz_podobne_mecze("Legia", "Lech")

    assert "x" * 300 not in wynik
    assert "…" in wynik


def test_awaria_rag_nie_zabija_predykcji(monkeypatch):
    """RAG jest opcjonalny — jego błąd nie może zatrzymać typowania."""
    import footstats.ai.post_match_analyzer as pma

    def wybucha(n):
        raise AttributeError("brak tabeli ai_feedback")

    monkeypatch.setattr(pma, "pobierz_ostatnie_wnioski", wybucha)

    assert an._pobierz_podobne_mecze("Legia", "Lech") == ""
