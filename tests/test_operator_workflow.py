"""test_operator_workflow.py — orkiestracja operatora (preflight → smoke → pipeline → review).

PO CO: modul mial 31%. To on decyduje, CZY W OGOLE odpalic produkcyjny
`daily_agent draft`. Dwie bramki sa krytyczne:
  * `skip_if_draft` — bez niej operator generuje drugi kupon tego samego dnia,
  * `critical_fail` — bez niej pipeline rusza mimo padnietego API/logowania.
Zadna nie byla przetestowana.

Wszystkie efekty uboczne (subprocess, Telegram, DB, zapis raportu) sa
podstawione — test NIE ma prawa odpalic prawdziwego pipeline'u ani wyslac
wiadomosci. Blokuje to tez `guard_live_ops`, ale nie polegamy na hooku.
"""
from __future__ import annotations

import json
import subprocess

import pytest

import footstats.operator.workflow as wf
from footstats.operator.manifest import Capability
from footstats.operator.runner import RunResult


def _wynik(cap_id="x", ok=True, **kw) -> RunResult:
    return RunResult(cap_id, ok, 0 if ok else 1, 0.1, kw.get("out", ""), kw.get("err", ""))


@pytest.fixture
def operator(tmp_path, monkeypatch):
    """OperatorWorkflow z ODCIETYMI efektami ubocznymi + podglad na notyfikacje."""
    monkeypatch.setattr(wf, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(wf, "STATE_FILE", tmp_path / "state" / "latest.json")
    monkeypatch.setattr(wf, "LOG_FILE", tmp_path / "logs" / "operator.log")
    monkeypatch.setattr(wf, "resolve_admin_user_id", lambda: 42)

    op = wf.OperatorWorkflow()
    op._wyslane = []                                    # type: ignore[attr-defined]
    monkeypatch.setattr(op, "_notify", op._wyslane.append)
    return op


def _stan(operator) -> dict:
    return json.loads(wf.STATE_FILE.read_text(encoding="utf-8"))


# ── konstrukcja i stan ──────────────────────────────────────────────────────

def test_uzywa_admina_gdy_brak_user_id(operator):
    assert operator.user_id == 42


def test_jawny_user_id_ma_pierwszenstwo(tmp_path, monkeypatch):
    monkeypatch.setattr(wf, "STATE_DIR", tmp_path / "s")
    monkeypatch.setattr(wf, "LOG_FILE", tmp_path / "l" / "x.log")
    monkeypatch.setattr(wf, "resolve_admin_user_id", lambda: 42)
    assert wf.OperatorWorkflow(user_id=7).user_id == 7


def test_zapis_stanu_ma_faze_czas_i_usera(operator):
    operator._save_state("smoke", {"smoke_ok": 3})
    stan = _stan(operator)
    assert stan["phase"] == "smoke"
    assert stan["user_id"] == 42
    assert stan["smoke_ok"] == 3
    assert "updated_at" in stan


def test_awaria_telegrama_nie_przerywa_operatora(tmp_path, monkeypatch):
    """_notify ma polykac bledy — inaczej padniety bot zatrzymuje caly pipeline."""
    monkeypatch.setattr(wf, "STATE_DIR", tmp_path / "s")
    monkeypatch.setattr(wf, "LOG_FILE", tmp_path / "l" / "x.log")
    monkeypatch.setattr(wf, "resolve_admin_user_id", lambda: 1)

    import footstats.utils.telegram_notify as tg
    monkeypatch.setattr(tg, "telegram_dostepny", lambda: True)

    def _padnij(text):
        raise OSError("bot niedostepny")

    monkeypatch.setattr(tg, "send_message", _padnij)
    wf.OperatorWorkflow()._notify("cokolwiek")          # nie rzuca


def test_notify_pomijany_gdy_telegram_wylaczony(tmp_path, monkeypatch):
    monkeypatch.setattr(wf, "STATE_DIR", tmp_path / "s")
    monkeypatch.setattr(wf, "LOG_FILE", tmp_path / "l" / "x.log")
    monkeypatch.setattr(wf, "resolve_admin_user_id", lambda: 1)

    import footstats.utils.telegram_notify as tg
    wyslane = []
    monkeypatch.setattr(tg, "telegram_dostepny", lambda: False)
    monkeypatch.setattr(tg, "send_message", wyslane.append)

    wf.OperatorWorkflow()._notify("cisza")
    assert wyslane == []


# ── preflight ───────────────────────────────────────────────────────────────

def test_preflight_odpala_wlasciwy_skrypt(operator, monkeypatch):
    przechwycone = {}

    def _run(cap, **kw):
        przechwycone["cap"] = cap
        return _wynik("preflight")

    monkeypatch.setattr(wf, "run_capability", _run)
    operator.run_preflight()

    cap = przechwycone["cap"]
    assert cap.id == "preflight"
    assert cap.critical is True
    assert "scripts/preflight_footstats.py" in cap.cmd


# ── smoke ───────────────────────────────────────────────────────────────────

def test_smoke_rozdziela_api_check_od_komendy(operator, monkeypatch):
    monkeypatch.setattr(wf, "iter_runnable", lambda: [
        Capability(id="api.health", label="h", category="api", api_check="health"),
        Capability(id="skrypt", label="s", category="scripts", cmd=["python", "-c", "pass"]),
    ])
    monkeypatch.setattr(wf, "run_api_check",
                        lambda check, cid, t: _wynik(cid, out=f"api:{check}"))
    monkeypatch.setattr(wf, "run_capability", lambda cap, **kw: _wynik(cap.id, out="cmd"))

    wyniki = operator.run_smoke()

    assert [r.capability_id for r in wyniki] == ["api.health", "skrypt"]
    assert wyniki[0].stdout_tail == "api:health"
    assert wyniki[1].stdout_tail == "cmd"


def test_capability_bez_cmd_i_api_oznaczona_jako_skip(operator, monkeypatch):
    monkeypatch.setattr(wf, "iter_runnable", lambda: [
        Capability(id="pominieta", label="p", category="x",
                   skip_reason="wymaga przegladarki"),
    ])
    wyniki = operator.run_smoke()

    assert wyniki[0].ok is False
    assert wyniki[0].stderr_tail == "wymaga przegladarki"


def test_smoke_zapisuje_bilans_do_stanu(operator, monkeypatch):
    monkeypatch.setattr(wf, "iter_runnable", lambda: [
        Capability(id="a", label="a", category="x", cmd=["python"]),
        Capability(id="b", label="b", category="x", cmd=["python"]),
    ])
    wyniki = iter([_wynik("a", ok=True), _wynik("b", ok=False)])
    monkeypatch.setattr(wf, "run_capability", lambda cap, **kw: next(wyniki))

    operator.run_smoke()
    stan = _stan(operator)
    assert stan["smoke_ok"] == 1 and stan["smoke_fail"] == 1
    assert len(stan["results"]) == 2


# ── pipeline ────────────────────────────────────────────────────────────────

def test_pipeline_pomijany_gdy_draft_juz_istnieje(operator, monkeypatch):
    """Bramka anty-duplikat: drugi kupon tego samego dnia to realna szkoda."""
    import footstats.core.coupon_tracker as ct
    monkeypatch.setattr(ct, "get_draft_today", lambda user_id=None: {"id": 1})

    odpalone = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: odpalone.append(a))

    wynik = operator.run_pipeline()

    assert wynik.ok is True
    assert "skipped" in wynik.stdout_tail
    assert odpalone == [], "odpalono pipeline mimo istniejacego draftu"


def test_skip_if_draft_wylaczalny(operator, monkeypatch):
    import footstats.core.coupon_tracker as ct
    monkeypatch.setattr(ct, "get_draft_today", lambda user_id=None: {"id": 1})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        args=a, returncode=0, stdout="ok", stderr=""))

    assert operator.run_pipeline(skip_if_draft=False).stdout_tail == "ok"


def test_pipeline_buduje_komende_z_faza_draft(operator, monkeypatch):
    import footstats.core.coupon_tracker as ct
    monkeypatch.setattr(ct, "get_draft_today", lambda user_id=None: None)
    przechwycone = {}

    def _run(cmd, **kw):
        przechwycone["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    operator.run_pipeline()

    cmd = przechwycone["cmd"]
    assert "footstats.daily_agent" in cmd
    assert "--faza" in cmd and "draft" in cmd
    assert "--waliduj" in cmd
    assert "--dry-run" not in cmd


def test_dry_run_dokłada_flage(operator, monkeypatch):
    import footstats.core.coupon_tracker as ct
    monkeypatch.setattr(ct, "get_draft_today", lambda user_id=None: None)
    przechwycone = {}
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: przechwycone.update(cmd=cmd)
                        or subprocess.CompletedProcess(cmd, 0, "", ""))

    operator.run_pipeline(dry_run=True)
    assert "--dry-run" in przechwycone["cmd"]


def test_pipeline_loguje_wyjscie_do_pliku(operator, monkeypatch):
    import footstats.core.coupon_tracker as ct
    monkeypatch.setattr(ct, "get_draft_today", lambda user_id=None: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        args=a, returncode=0, stdout="linia stdout", stderr="linia stderr"))

    operator.run_pipeline()
    log = wf.LOG_FILE.read_text(encoding="utf-8")
    assert "linia stdout" in log and "linia stderr" in log


def test_porazka_pipeline_zglaszana_notyfikacja(operator, monkeypatch):
    import footstats.core.coupon_tracker as ct
    monkeypatch.setattr(ct, "get_draft_today", lambda user_id=None: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        args=a, returncode=2, stdout="", stderr="wybuch"))

    wynik = operator.run_pipeline()
    assert wynik.ok is False
    assert any("FAIL" in m for m in operator._wyslane)


def test_timeout_pipeline_oznaczany_jako_wymagajacy_uwagi(operator, monkeypatch):
    import footstats.core.coupon_tracker as ct
    monkeypatch.setattr(ct, "get_draft_today", lambda user_id=None: None)

    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=3600)

    monkeypatch.setattr(subprocess, "run", _timeout)
    wynik = operator.run_pipeline()

    assert wynik.ok is False and wynik.exit_code == -9
    assert wynik.needs_cursor is True


# ── review ──────────────────────────────────────────────────────────────────

def test_review_bez_kuponow_zwraca_pusto(operator, monkeypatch):
    import footstats.core.coupon_tracker as ct
    monkeypatch.setattr(ct, "get_active_coupons", lambda user_id=None: [])
    assert operator.run_review() == []


def test_review_zapisuje_do_kuponow(operator, monkeypatch):
    import footstats.core.coupon_tracker as ct
    monkeypatch.setattr(ct, "get_active_coupons", lambda user_id=None: [{"id": 3}])
    monkeypatch.setattr(wf, "review_coupons",
                        lambda rows, max_legs=8: [{"coupon_id": 3, "legs_count": 2,
                                                   "ai_review": "opinia"}])
    zapisane = []
    monkeypatch.setattr(wf, "append_review_to_coupon",
                        lambda cid, txt, uid: zapisane.append((cid, txt, uid)))

    operator.run_review()
    assert zapisane == [(3, "opinia", 42)]
    assert _stan(operator)["count"] == 1


def test_persist_false_nie_pisze_do_bazy(operator, monkeypatch):
    import footstats.core.coupon_tracker as ct
    monkeypatch.setattr(ct, "get_active_coupons", lambda user_id=None: [{"id": 3}])
    monkeypatch.setattr(wf, "review_coupons",
                        lambda rows, max_legs=8: [{"coupon_id": 3, "legs_count": 1,
                                                   "ai_review": "x"}])
    zapisane = []
    monkeypatch.setattr(wf, "append_review_to_coupon",
                        lambda *a: zapisane.append(a))

    operator.run_review(persist=False)
    assert zapisane == []


# ── run_full ────────────────────────────────────────────────────────────────

@pytest.fixture
def full_mocks(monkeypatch, tmp_path):
    """Wspolne podstawienia dla run_full."""
    monkeypatch.setattr(wf, "iter_runnable", lambda: [])
    monkeypatch.setattr(wf, "write_report",
                        lambda faza, wyniki, extra: (tmp_path / "r.json", tmp_path / "r.md"))
    import footstats.core.coupon_tracker as ct
    monkeypatch.setattr(ct, "get_draft_today", lambda user_id=None: None)
    monkeypatch.setattr(ct, "get_active_coupons", lambda user_id=None: [])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        args=a, returncode=0, stdout="", stderr=""))
    return monkeypatch


def test_full_przechodzi_cala_sciezke(operator, full_mocks):
    full_mocks.setattr(wf, "run_capability", lambda cap, **kw: _wynik("preflight"))
    json_p, md_p = operator.run_full()
    assert json_p.name == "r.json" and md_p.name == "r.md"


def test_krytyczna_porazka_blokuje_pipeline(operator, full_mocks):
    """Padniety preflight = nie ruszamy produkcyjnego draftu."""
    full_mocks.setattr(wf, "run_capability", lambda cap, **kw: _wynik("preflight", ok=False))
    odpalone = []
    full_mocks.setattr(subprocess, "run", lambda *a, **k: odpalone.append(a))

    operator.run_full()

    assert odpalone == [], "pipeline ruszyl mimo krytycznej porazki smoke"
    assert any("skip pipeline" in m for m in operator._wyslane)


def test_skip_smoke_pomija_capability(operator, full_mocks):
    wolania = []
    full_mocks.setattr(wf, "iter_runnable", lambda: wolania.append("smoke") or [])
    full_mocks.setattr(wf, "run_capability", lambda cap, **kw: _wynik("preflight"))

    operator.run_full(skip_smoke=True)
    assert wolania == [], "odpalono smoke mimo skip_smoke=True"


def test_niekrytyczna_porazka_nie_blokuje_pipeline(operator, full_mocks):
    """Padniety scraper to nie powod, zeby wstrzymywac caly dzien."""
    full_mocks.setattr(wf, "iter_runnable", lambda: [
        Capability(id="scraper.jakis", label="s", category="scrapers", cmd=["python"]),
    ])
    wyniki = iter([_wynik("preflight", ok=True), _wynik("scraper.jakis", ok=False)])
    full_mocks.setattr(wf, "run_capability", lambda cap, **kw: next(wyniki))

    odpalone = []
    full_mocks.setattr(subprocess, "run", lambda *a, **k: odpalone.append(a)
                       or subprocess.CompletedProcess(a, 0, "", ""))

    operator.run_full()
    assert odpalone, "pipeline nie ruszyl mimo tylko niekrytycznej porazki"
