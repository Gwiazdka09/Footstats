"""test_operator_runner_review.py — uruchamianie capability + review kuponow.

PO CO: `operator/runner.py` mial 84%, ale bez pokrycia zostaly wlasnie sciezki
BLEDOW — timeout, brak cmd, wyjatek systemowy. To one decyduja, czy operator
zglosi awarie, czy ja przemilczy.

`_komenda` i `_env_z_pythonpath` maja w kodzie dlugie komentarze o realnych
awariach ("No module named 'rich'", "No module named 'footstats'") — obie
naprawy byly dotad NIEPRZETESTOWANE, wiec nic nie chronilo przed regresja.

`operator/review.py` mial 16%: parsowanie nog kuponu przyjmuje trzy rozne
ksztalty danych (JSON-string, lista, brak) i dwa nazewnictwa pol
(home/away vs gospodarz/goscie). Kazdy nieobsluzony = pusty przeglad kuponu.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from footstats.operator.manifest import Capability
from footstats.operator.runner import (
    PROJECT_ROOT,
    RunResult,
    _env_z_pythonpath,
    _komenda,
    _tail,
    run_capability,
)
from footstats.operator.review import (
    _legs_from_coupon,
    _picks_text,
    append_review_to_coupon,
    review_coupons,
)


def _cap(**kw) -> Capability:
    baza = {"id": "test.cap", "label": "test", "category": "scripts",
            "cmd": ["python", "-c", "pass"], "timeout_s": 30}
    baza.update(kw)
    return Capability(**baza)


# ── _komenda ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("golе", ["python", "python3"])
def test_gole_python_podmienione_na_interpreter_venva(golе):
    """Regresja: systemowy python nie ma zaleznosci projektu ('No module named rich')."""
    assert _komenda([golе, "-m", "footstats.x"]) == [sys.executable, "-m", "footstats.x"]


def test_inne_komendy_bez_zmian():
    assert _komenda(["pytest", "-q"]) == ["pytest", "-q"]


def test_pusta_komenda_nie_wywala():
    assert _komenda([]) == []


def test_komenda_zwraca_kopie():
    oryginal = ["pytest"]
    assert _komenda(oryginal) is not oryginal


# ── _env_z_pythonpath ───────────────────────────────────────────────────────

def test_dodaje_src_do_pythonpath():
    """Regresja: bez tego podproces dostawal 'No module named footstats'."""
    env = _env_z_pythonpath({"INNE": "x"})
    assert str(PROJECT_ROOT / "src") in env["PYTHONPATH"].split(os.pathsep)
    assert env["INNE"] == "x"


def test_zachowuje_istniejacy_pythonpath():
    env = _env_z_pythonpath({"PYTHONPATH": "/juz/tu/bylo"})
    czesci = env["PYTHONPATH"].split(os.pathsep)
    assert "/juz/tu/bylo" in czesci
    assert str(PROJECT_ROOT / "src") in czesci


def test_nie_duplikuje_src_gdy_juz_jest():
    src = str(PROJECT_ROOT / "src")
    env = _env_z_pythonpath({"PYTHONPATH": src})
    assert env["PYTHONPATH"].split(os.pathsep).count(src) == 1


def test_brak_env_bierze_os_environ(monkeypatch):
    monkeypatch.setenv("ZNACZNIK_TESTU", "obecny")
    assert _env_z_pythonpath(None)["ZNACZNIK_TESTU"] == "obecny"


# ── _tail ───────────────────────────────────────────────────────────────────

def test_krotki_tekst_bez_zmian():
    assert _tail("krotko") == "krotko"


def test_dlugi_tekst_przyciety_z_prefiksem():
    wynik = _tail("x" * 1000, max_chars=100)
    assert wynik.startswith("...")
    assert len(wynik) == 103


def test_tail_obcina_biale_znaki():
    assert _tail("  tekst  \n") == "tekst"


def test_tail_z_none():
    assert _tail(None) == ""


# ── run_capability ──────────────────────────────────────────────────────────

def test_brak_cmd_daje_blad_z_podpowiedzia():
    wynik = run_capability(_cap(cmd=None))
    assert wynik.ok is False
    assert wynik.exit_code == -1
    assert "api_check" in wynik.stderr_tail


def test_sukces_gdy_exit_zero(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        args=a, returncode=0, stdout="wszystko gra", stderr=""))
    wynik = run_capability(_cap())
    assert wynik.ok is True
    assert wynik.exit_code == 0
    assert wynik.stdout_tail == "wszystko gra"


def test_porazka_gdy_exit_niezerowy(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        args=a, returncode=3, stdout="", stderr="cos padlo"))
    wynik = run_capability(_cap())
    assert wynik.ok is False and wynik.exit_code == 3


@pytest.mark.parametrize("slowo", ["Playwright", "TIMEOUT", "captcha", "Browser"])
def test_needs_cursor_gdy_blad_wskazuje_na_przegladarke(monkeypatch, slowo):
    """Te awarie wymagaja RECZNEJ interwencji — operator ma je wyroznic."""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        args=a, returncode=1, stdout="", stderr=f"blad: {slowo} nie odpowiada"))
    assert run_capability(_cap()).needs_cursor is True


def test_needs_cursor_nieustawiony_przy_sukcesie(monkeypatch):
    """Slowo 'timeout' w logu udanego przebiegu to nie awaria."""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        args=a, returncode=0, stdout="", stderr="ustawiono timeout=30"))
    assert run_capability(_cap()).needs_cursor is False


def test_timeout_oznaczany_jako_wymagajacy_uwagi(monkeypatch):
    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=30, output=b"czesciowe")

    monkeypatch.setattr(subprocess, "run", _timeout)
    wynik = run_capability(_cap())
    assert wynik.ok is False
    assert wynik.exit_code == -9
    assert "Timeout after 30s" in wynik.stderr_tail
    assert wynik.needs_cursor is True
    assert "czesciowe" in wynik.stdout_tail


def test_blad_systemowy_nie_wywala_operatora(monkeypatch):
    def _wybuch(*a, **k):
        raise OSError("brak pliku wykonywalnego")

    monkeypatch.setattr(subprocess, "run", _wybuch)
    wynik = run_capability(_cap())
    assert wynik.ok is False
    assert "brak pliku" in wynik.stderr_tail


def test_to_dict_zaokragla_czas():
    wynik = RunResult("x", True, 0, 1.23456, "o", "e")
    assert wynik.to_dict()["duration_s"] == 1.23
    assert set(wynik.to_dict()) == {"capability_id", "ok", "exit_code", "duration_s",
                                    "stdout_tail", "stderr_tail", "needs_cursor"}


# ── _legs_from_coupon ───────────────────────────────────────────────────────

def test_nogi_z_json_stringa():
    assert _legs_from_coupon({"legs_json": '[{"home": "A"}]'}) == [{"home": "A"}]


def test_nogi_z_gotowej_listy():
    assert _legs_from_coupon({"legs": [{"home": "B"}]}) == [{"home": "B"}]


def test_uszkodzony_json_daje_pusta_liste():
    assert _legs_from_coupon({"legs_json": "{zepsute"}) == []


def test_brak_nog_daje_pusta_liste():
    assert _legs_from_coupon({}) == []


def test_niepoprawny_typ_nog_daje_pusta_liste():
    assert _legs_from_coupon({"legs": 42}) == []


# ── _picks_text ─────────────────────────────────────────────────────────────

def test_picks_z_nazewnictwem_angielskim():
    tekst = _picks_text([{"home": "Legia", "away": "Lech", "tip": "1", "odds": 1.85}], 10.0)
    assert "Legia vs Lech - 1 @ 1.85" in tekst
    assert "Stake: 10.0 PLN" in tekst


def test_picks_z_nazewnictwem_polskim():
    """Nogi z quick_picks maja gospodarz/goscie/typ/kurs."""
    tekst = _picks_text(
        [{"gospodarz": "Wisła", "goscie": "Raków", "typ": "X", "kurs": 3.4}], 5.0)
    assert "Wisła vs Raków - X @ 3.4" in tekst


def test_picks_pusta_lista_ma_sama_stawke():
    assert _picks_text([], 7.5).strip().startswith("Stake: 7.5")


# ── review_coupons ──────────────────────────────────────────────────────────

@pytest.fixture
def review_mocks(monkeypatch):
    """Podstawia scraper kontekstu i Groqa; zwraca stan do sterowania."""
    stan = {"ctx": {"xg": 1.4}, "ai": "Kupon rozsadny", "picks": []}

    import footstats.data.context_scraper as cs
    import footstats.ai.analyzer as an

    def _ctx(home, away, liga):
        if isinstance(stan["ctx"], Exception):
            raise stan["ctx"]
        return stan["ctx"]

    def _ai(picks, stawka=10.0, **kw):
        stan["picks"].append(picks)
        if isinstance(stan["ai"], Exception):
            raise stan["ai"]
        return stan["ai"]

    monkeypatch.setattr(cs, "get_match_context", _ctx)
    monkeypatch.setattr(an, "ai_sprawdz_kupon", _ai)
    return stan


def test_review_zwraca_wpis_na_kupon(review_mocks):
    wynik = review_coupons([{"id": 7, "legs_json": '[{"home": "A", "away": "B"}]',
                             "stake_pln": 12}])
    assert len(wynik) == 1
    assert wynik[0]["coupon_id"] == 7
    assert wynik[0]["legs_count"] == 1
    assert wynik[0]["ai_review"] == "Kupon rozsadny"


def test_review_przycina_do_max_legs(review_mocks):
    nogi = [{"home": f"D{i}", "away": "X"} for i in range(12)]
    wynik = review_coupons([{"id": 1, "legs": nogi}], max_legs=3)
    assert wynik[0]["legs_count"] == 3
    assert len(wynik[0]["contexts"]) == 3


def test_blad_kontekstu_nie_przerywa_review(review_mocks):
    review_mocks["ctx"] = OSError("scraper padl")
    wynik = review_coupons([{"id": 1, "legs": [{"home": "A", "away": "B"}]}])
    assert "error" in wynik[0]["contexts"][0]
    assert wynik[0]["ai_review"] == "Kupon rozsadny", "review przerwane przez scraper"


def test_blad_groqa_ladnie_zapisany(review_mocks):
    review_mocks["ai"] = RuntimeError("503")
    wynik = review_coupons([{"id": 1, "legs": [{"home": "A", "away": "B"}]}])
    assert wynik[0]["ai_review"].startswith("Groq error:")


def test_domyslna_stawka_gdy_brak(review_mocks):
    review_coupons([{"id": 1, "legs": [{"home": "A", "away": "B"}]}])
    assert "Stake: 10.0 PLN" in review_mocks["picks"][0]


def test_pusta_lista_kuponow(review_mocks):
    assert review_coupons([]) == []


# ── append_review_to_coupon ─────────────────────────────────────────────────

class _FakeConn:
    def __init__(self, row):
        self._row = row
        self.zapytania: list[tuple] = []

    def execute(self, sql, params=()):
        self.zapytania.append((sql, params))
        if sql.strip().upper().startswith("SELECT"):
            return _Kursor(self._row)
        return _Kursor(None)

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Kursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


def test_dopisuje_review_do_istniejacego_uzasadnienia(monkeypatch):
    conn = _FakeConn({"groq_reasoning": "pierwotna analiza"})
    monkeypatch.setattr("footstats.utils.db.connect", lambda *a, **k: conn)

    append_review_to_coupon(5, "nowa opinia operatora", user_id=1)

    update = [z for z in conn.zapytania if z[0].strip().upper().startswith("UPDATE")]
    assert len(update) == 1
    nowy_tekst = update[0][1][0]
    assert "pierwotna analiza" in nowy_tekst
    assert "operator_review" in nowy_tekst
    assert "nowa opinia operatora" in nowy_tekst


def test_brak_kuponu_nie_robi_update(monkeypatch):
    conn = _FakeConn(None)
    monkeypatch.setattr("footstats.utils.db.connect", lambda *a, **k: conn)

    append_review_to_coupon(999, "opinia", user_id=1)

    assert not [z for z in conn.zapytania if z[0].strip().upper().startswith("UPDATE")]


def test_review_przycinany_do_4000_znakow(monkeypatch):
    conn = _FakeConn({"groq_reasoning": ""})
    monkeypatch.setattr("footstats.utils.db.connect", lambda *a, **k: conn)

    append_review_to_coupon(1, "x" * 9000, user_id=1)

    update = [z for z in conn.zapytania if z[0].strip().upper().startswith("UPDATE")][0]
    assert update[1][0].count("x") == 4000
