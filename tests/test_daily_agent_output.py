"""test_daily_agent_output.py — zapis kuponu do .txt i render wynikow.

PO CO: modul mial 14% pokrycia, a to on produkuje plik, ktory user faktycznie
czyta rano. Blad formatowania nie wywala pipeline'u — po prostu daje zly kupon
na papierze, cicho.

Sprawdzamy zwlaszcza mnoznik 0.88 (podatek PL 12%). Ta sama konwencja co
`kelly.ev_netto` = p * kurs * (1 - podatek): podatek liczony od WYPLATY brutto,
bo w Polsce schodzi ze stawki przy zawarciu zakladu. Rozjazd miedzy tymi dwoma
miejscami dawalby inne liczby w pliku niz w EV.
"""
from __future__ import annotations

import subprocess

import pytest

import footstats.daily_agent_output as dao


@pytest.fixture(autouse=True)
def logi_w_tmp(tmp_path, monkeypatch):
    """LOGS_DIR na tmp — test nie ma smiecic w logs/ projektu."""
    monkeypatch.setattr(dao, "LOGS_DIR", tmp_path)
    return tmp_path


def _kupon(*zdarzenia, kurs_laczny: float = 2.0, **extra) -> dict:
    return {"zdarzenia": list(zdarzenia), "kurs_laczny": kurs_laczny, **extra}


def _zdarzenie(nr=1, mecz="Legia – Lech", typ="1", kurs=1.85, **extra) -> dict:
    return {"nr": nr, "mecz": mecz, "typ": typ, "kurs": kurs, **extra}


# ── _zapisz_txt ─────────────────────────────────────────────────────────────

def test_zapisuje_plik_z_data_w_nazwie(logi_w_tmp):
    sciezka = dao._zapisz_txt({"kupon_a": _kupon(_zdarzenie())}, 10.0, 5.0)
    assert sciezka.exists()
    assert sciezka.name.startswith("kupon_") and sciezka.suffix == ".txt"


def test_wygrana_netto_uwzglednia_podatek_12(logi_w_tmp):
    """10 PLN * kurs 3.00 * 0.88 = 26.40 — ta sama konwencja co kelly.ev_netto."""
    sciezka = dao._zapisz_txt({"kupon_a": _kupon(_zdarzenie(), kurs_laczny=3.0)}, 10.0, 5.0)
    tekst = sciezka.read_text(encoding="utf-8")
    assert "Kurs łączny: 3.00" in tekst
    assert "26.40 PLN" in tekst


def test_podatek_zgodny_z_kelly_ev_netto(logi_w_tmp):
    """Regresja na rozjazd konwencji podatkowej miedzy modulami."""
    from footstats.core.kelly import ev_netto

    stawka, kurs, p = 10.0, 3.0, 1.0          # p=1 → czysty mnoznik wyplaty
    z_pliku = stawka * kurs * 0.88
    z_kelly = stawka * (1 + ev_netto(p, kurs, podatek=0.12))
    assert round(z_pliku, 2) == round(z_kelly, 2)


def test_pomija_puste_kupony(logi_w_tmp):
    dane = {"kupon_a": _kupon(_zdarzenie()), "kupon_b": {"zdarzenia": []}, "kupon_c": {}}
    tekst = dao._zapisz_txt(dane, 10.0, 5.0).read_text(encoding="utf-8")
    assert "KUPON A" in tekst
    assert "KUPON B" not in tekst
    assert "KUPON C" not in tekst


def test_wszystkie_cztery_kupony_trafiaja_do_pliku(logi_w_tmp):
    dane = {k: _kupon(_zdarzenie()) for k in ("kupon_a", "kupon_b", "kupon_c", "kupon_d")}
    tekst = dao._zapisz_txt(dane, 10.0, 5.0).read_text(encoding="utf-8")
    for label in ("KUPON A", "KUPON B", "KUPON C", "KUPON D"):
        assert label in tekst


def test_znacznik_weryfikacji_bzzoiro(logi_w_tmp):
    dane = {"kupon_a": _kupon(
        _zdarzenie(nr=1, mecz="Zweryfikowany", _verified=True),
        _zdarzenie(nr=2, mecz="Niezweryfikowany"),
    )}
    tekst = dao._zapisz_txt(dane, 10.0, 5.0).read_text(encoding="utf-8")
    assert "[✓] Zweryfikowany" in tekst
    assert "[ ] Niezweryfikowany" in tekst


def test_top3_z_ev_i_uzasadnieniem(logi_w_tmp):
    dane = {"top3": [
        {"mecz": "A – B", "typ": "1", "kurs": 2.1, "ev_netto": 7.5,
         "uzasadnienie": "forma domowa"},
    ]}
    tekst = dao._zapisz_txt(dane, 10.0, 5.0).read_text(encoding="utf-8")
    assert "TOP 3 MECZÓW" in tekst
    assert "EV=+7.5%" in tekst
    assert "forma domowa" in tekst


def test_ostrzezenia_trafiaja_do_pliku(logi_w_tmp):
    tekst = dao._zapisz_txt({"ostrzezenia": "bankroll blisko stop-loss"},
                            10.0, 5.0).read_text(encoding="utf-8")
    assert "OSTRZEŻENIA" in tekst
    assert "bankroll blisko stop-loss" in tekst


def test_brakujace_pola_nie_wywalaja_zapisu(logi_w_tmp):
    """Groq potrafi oddac niekompletny JSON — plik ma powstac mimo to."""
    dane = {"kupon_a": {"zdarzenia": [{}], "kurs_laczny": None}}
    tekst = dao._zapisz_txt(dane, 10.0, 5.0).read_text(encoding="utf-8")
    assert "?" in tekst          # placeholdery zamiast crashu
    assert "Kurs łączny: 0.00" in tekst


def test_pusty_slownik_daje_sam_naglowek(logi_w_tmp):
    tekst = dao._zapisz_txt({}, 10.0, 5.0).read_text(encoding="utf-8")
    assert "FootStats Daily Agent" in tekst
    assert "KUPON" not in tekst


# ── _powiadomienie_windows ──────────────────────────────────────────────────

def test_powiadomienie_odpala_powershell(monkeypatch):
    zebrane = {}
    monkeypatch.setattr(subprocess, "Popen",
                        lambda cmd, **k: zebrane.update(cmd=cmd))
    dao._powiadomienie_windows("Tytul", "Tresc")
    assert zebrane["cmd"][0] == "powershell"
    assert "Tytul" in zebrane["cmd"][-1]


def test_powiadomienie_escapuje_apostrof(monkeypatch):
    """Apostrof w nazwie druzyny nie moze rozwalic skryptu PowerShell."""
    zebrane = {}
    monkeypatch.setattr(subprocess, "Popen",
                        lambda cmd, **k: zebrane.update(cmd=cmd))
    dao._powiadomienie_windows("Nott'm Forest", "kupon")
    assert "Nott''m Forest" in zebrane["cmd"][-1]


def test_brak_powershell_nie_przerywa_pipeline(monkeypatch):
    """Linux/Cloud Run nie ma powershell — to nie moze wywalic agenta."""
    def _brak(*a, **k):
        raise OSError("powershell not found")

    monkeypatch.setattr(subprocess, "Popen", _brak)
    dao._powiadomienie_windows("T", "T")   # nie rzuca


# ── _wyswietl ───────────────────────────────────────────────────────────────

def test_wyswietl_bez_top3_pokazuje_surowa_odpowiedz(capsys):
    dao._wyswietl({"_raw": "niepoprawny JSON od Groqa"}, 10.0, 5.0)
    assert "niepoprawny JSON" in capsys.readouterr().out


def test_wyswietl_renderuje_kupony(capsys):
    dane = {
        "top3": [{"mecz": "A – B", "typ": "1", "kurs": 2.0, "ev_netto": 9.0}],
        "kupon_a": _kupon(
            _zdarzenie(pewnosc_pct=70, kelly_stake=8, _verified=True),
            kurs_laczny=2.5, szansa_wygranej_pct=55,
        ),
    }
    dao._wyswietl(dane, 10.0, 5.0)
    out = capsys.readouterr().out
    assert "TOP 3" in out
    assert "KUPON A" in out
    assert "22.00" in out          # 10 * 2.5 * 0.88
