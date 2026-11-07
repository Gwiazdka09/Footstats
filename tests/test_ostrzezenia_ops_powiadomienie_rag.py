"""Szum w logach kontenera Linux: brak powershella i swiadomie wylaczone embeddingi."""
from __future__ import annotations

import builtins
import logging

import pytest

from footstats import daily_agent_output as dao
from footstats.ai import rag_embeddings


def test_powiadomienie_windows_pomijane_poza_windows(monkeypatch):
    monkeypatch.setattr(dao, "_jest_windows", lambda: False)
    wywolania: list = []
    monkeypatch.setattr(dao.subprocess, "Popen", lambda *a, **k: wywolania.append(a))

    dao._powiadomienie_windows("Tytul", "Tekst")

    assert wywolania == [], "poza Windows nie wolno wolac powershella"


def test_brak_sentence_transformers_to_info_a_nie_error(monkeypatch, caplog):
    monkeypatch.setattr(rag_embeddings, "_EMBEDDING_MODEL", None)
    oryginalny_import = builtins.__import__

    def _import(nazwa, *a, **k):
        if nazwa == "sentence_transformers":
            raise ImportError("brak")
        return oryginalny_import(nazwa, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _import)
    caplog.set_level(logging.INFO, logger=rag_embeddings.logger.name)

    with pytest.raises(ImportError):
        rag_embeddings._get_embedding_model()

    zapisy = [r for r in caplog.records if "sentence-transformers" in r.getMessage()]
    assert zapisy and all(r.levelno == logging.INFO for r in zapisy)
