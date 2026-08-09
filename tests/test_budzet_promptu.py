"""Prompt nie może przekroczyć limitu modelu, a awaria LLM nie może zabić przebiegu.

PO CO — obie wady wywróciły produkcyjny job `footstats-final` 09.08.2026:

1. Groq odrzucił zapytanie:
       413 - Request too large for model `llama-3.1-8b-instant`
       Limit 6000 TPM, Requested 8957
   Nikt nie pilnował rozmiaru promptu. `AI_TPM_LIMIT` miał domyślnie 8000, choć
   domyślny model ma 6000 — a limit dotyczy SUMY wejścia i wyjścia.
   Prompt urósł, bo naprawiony filtr value-bet zaczął przepuszczać kandydatów
   (32 → 15 zamiast 0), więc opisów meczów w prompcie zrobiło się realnie więcej.

2. Po odmowie Groqa kod schodzi do Ollamy na `localhost:11434`, której
   w kontenerze nigdy nie będzie. `_ollama` łapało `(RequestException, ValueError)`,
   ale tenacity opakowuje porażkę w `RetryError` — typ spoza tej listy. Wyjątek
   przeleciał przez `zapytaj_ai` i wywalił CAŁY dzienny przebieg:
       tenacity.RetryError[<Future ... raised ConnectionError>]
   Zamiast degradacji dostaliśmy `exit(1)` i zero predykcji tego dnia.
"""
from __future__ import annotations

import pytest
from tenacity import RetryError

from footstats.ai import client


class TestBudzetTokenow:
    def test_limit_zgadza_sie_z_modelem(self):
        """Domyślny model ma 6000 TPM — limit nie może być wzięty z sufitu."""
        assert client.tpm_dla_modelu("llama-3.1-8b-instant") == 6000
        assert client.tpm_dla_modelu("llama-3.3-70b-versatile") == 12000

    def test_nieznany_model_dostaje_ostrozny_limit(self):
        """Lepiej wysłać za mało niż dostać 413 i stracić przebieg."""
        assert client.tpm_dla_modelu("cos-nowego-v9") <= 6000

    def test_szacunek_tokenow_rosnie_z_dlugoscia(self):
        assert client.szacuj_tokeny("a" * 400) > client.szacuj_tokeny("a" * 100)

    def test_krotki_prompt_przechodzi_bez_zmian(self):
        prompt = "Przeanalizuj mecz Legia vs Lech."
        assert client.dopasuj_do_budzetu(prompt, budzet_tokenow=1000) == prompt

    def test_dlugi_prompt_jest_przycinany_do_budzetu(self):
        prompt = "X" * 40_000

        wynik = client.dopasuj_do_budzetu(prompt, budzet_tokenow=1000)

        assert client.szacuj_tokeny(wynik) <= 1000
        assert len(wynik) < len(prompt)

    def test_przyciecie_zostawia_poczatek_i_koniec(self):
        """Instrukcja zadania jest na początku, format odpowiedzi na końcu —
        ucięcie któregokolwiek zamienia odpowiedź w śmieci."""
        prompt = "POCZATEK-INSTRUKCJA\n" + ("wypelniacz " * 5000) + "\nKONIEC-FORMAT-JSON"

        wynik = client.dopasuj_do_budzetu(prompt, budzet_tokenow=500)

        assert "POCZATEK-INSTRUKCJA" in wynik
        assert "KONIEC-FORMAT-JSON" in wynik

    def test_przyciecie_jest_oznaczone(self):
        """Model musi wiedzieć, że czegoś nie dostał — inaczej zmyśli brakujące."""
        wynik = client.dopasuj_do_budzetu("X" * 40_000, budzet_tokenow=500)
        assert "…" in wynik or "[" in wynik


class TestAwariaNieZabijaPrzebiegu:
    def test_retryerror_z_ollamy_nie_wylatuje(self, monkeypatch):
        """SEDNO awarii 09.08: RetryError nie byl lapany i konczyl caly job."""
        def _wybuch(prompt):
            raise RetryError(last_attempt=None)

        monkeypatch.setattr(client, "_ollama_call_impl", _wybuch)

        assert client._ollama("cokolwiek") is None

    def test_brak_obu_zrodel_daje_czytelny_blad(self, monkeypatch):
        """RuntimeError z instrukcja jest OK; RetryError z wnetrznosci tenacity nie."""
        monkeypatch.setattr(client, "_groq", lambda p, t=600: None)
        monkeypatch.setattr(client, "_ollama", lambda p: None)

        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            client.zapytaj_ai("prompt")

    def test_413_z_groqa_nie_przechodzi_do_wolajacego(self, monkeypatch):
        """Odmowa rozmiaru ma dac None (i fallback), nie wyjatek."""
        class _Blad(Exception):
            pass

        def _wybuch(klucz, prompt, max_tokens):
            raise _Blad("Error code: 413 - Request too large")

        monkeypatch.setenv("GROQ_API_KEY", "klucz")
        monkeypatch.setattr(client, "_groq_call_impl", _wybuch)

        assert client._groq("prompt") is None


class TestIntegracja:
    def test_zapytaj_ai_przycina_zanim_wysle(self, monkeypatch):
        """Guard ma zadzialac PRZED zapytaniem, nie po odmowie."""
        wyslane: list[str] = []

        def _lap(prompt, max_tokens=600):
            wyslane.append(prompt)
            return "ok"

        monkeypatch.setattr(client, "_groq", _lap)
        monkeypatch.setattr(client, "AI_PREFER_LOCAL", False)
        monkeypatch.setattr(client, "GROQ_MODEL", "llama-3.1-8b-instant")

        client.zapytaj_ai("Z" * 60_000, max_tokens=1500)

        assert wyslane, "nie doszlo do zapytania"
        assert client.szacuj_tokeny(wyslane[0]) + 1500 <= 6000, "wyslano ponad limit modelu"
