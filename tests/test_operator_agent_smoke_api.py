"""test_operator_agent_smoke_api.py — CLI operatora + smoke API.

PO CO:
  * `operator_agent.main()` mial 0% — to on tlumaczy `--faza/--only` na wywolania
    workflow i zwraca KOD WYJSCIA. Zly kod = cron/Cloud Scheduler uzna padniety
    przebieg za udany i nikt sie nie dowie.
  * `operator/smoke_api.py` mial 16% — kazdy `check` to osobna galaz, a od nich
    zalezy werdykt "czy API zyje". Nierozpoznany check MUSI dawac porazke,
    nie ciche OK.

Cala warstwa HTTP jest podstawiona — smoke NIE ma prawa uderzyc w prawdziwe API
ani w baze (`coupon_place_validate` kiedys realnie tworzyl kupon na produkcji).
"""
from __future__ import annotations

import pytest

import footstats.operator.smoke_api as sa
import footstats.operator_agent as oa
from footstats.operator.runner import RunResult


def _wynik(cap_id="x", ok=True) -> RunResult:
    return RunResult(cap_id, ok, 0 if ok else 1, 0.5, "out", "err")


# ══════════════════════════════════════════════════════════════════════════
#  operator_agent.main
# ══════════════════════════════════════════════════════════════════════════

class _FakeWorkflow:
    """Atrapa OperatorWorkflow — notuje, co zostalo wywolane.

    Konfiguracja siedzi na KLASIE, nie na instancji: `main()` tworzy obiekt sam,
    wiec test nie ma go w reku przed wywolaniem. Dzieki temu wystarczy
    `monkeypatch.setattr(_FakeWorkflow, "preflight_ok", False)`.
    """
    ostatnia: "_FakeWorkflow | None" = None
    preflight_ok: bool = True
    smoke_wyniki: list = []
    pipeline_ok: bool = True
    review_wynik: list = []
    full_raport: tuple | None = None

    def __init__(self, user_id=None):
        self.user_id = user_id
        self.wywolania: list[str] = []
        _FakeWorkflow.ostatnia = self

    def run_preflight(self):
        self.wywolania.append("preflight")
        return _wynik("preflight", self.preflight_ok)

    def run_smoke(self):
        self.wywolania.append("smoke")
        return self.smoke_wyniki

    def run_pipeline(self, dry_run=False):
        self.wywolania.append(f"pipeline(dry={dry_run})")
        return _wynik("pipeline", self.pipeline_ok)

    def run_review(self, max_legs=8):
        self.wywolania.append(f"review(max_legs={max_legs})")
        return self.review_wynik

    def run_full(self, skip_smoke=False, dry_run_pipeline=False):
        self.wywolania.append(f"full(skip_smoke={skip_smoke}, dry={dry_run_pipeline})")
        return self.full_raport


@pytest.fixture
def cli(monkeypatch, tmp_path):
    """Podstawia OperatorWorkflow i argv; zwraca funkcje uruchamiajaca main()."""
    import footstats.operator.workflow as wfmod
    monkeypatch.setattr(wfmod, "OperatorWorkflow", _FakeWorkflow)
    monkeypatch.setattr(oa, "load_dotenv", lambda: None)

    raport = tmp_path / "raport.json"
    raport.write_text('{"summary": {"fail": 0}}', encoding="utf-8")
    _FakeWorkflow.ostatnia = None

    def _uruchom(*argv, raport_json=raport):
        monkeypatch.setattr("sys.argv", ["operator_agent", *argv])
        monkeypatch.setattr(_FakeWorkflow, "full_raport",
                            (raport_json, tmp_path / "raport.md"))
        return oa.main()

    return _uruchom


def test_preflight_zwraca_zero_przy_sukcesie(cli, capsys):
    assert cli("--only", "preflight") == 0
    assert "PASS" in capsys.readouterr().out


def test_preflight_zwraca_jeden_przy_porazce(cli, monkeypatch, capsys):
    monkeypatch.setattr(_FakeWorkflow, "preflight_ok", False)
    assert cli("--only", "preflight") == 1
    assert "FAIL" in capsys.readouterr().out


def test_smoke_zwraca_zero_gdy_wszystko_ok(cli, monkeypatch, capsys):
    monkeypatch.setattr(_FakeWorkflow, "smoke_wyniki",
                        [_wynik("a", True), _wynik("b", True)])
    assert cli("--only", "smoke") == 0
    out = capsys.readouterr().out
    assert "[OK] a" in out and "[OK] b" in out


def test_smoke_zwraca_jeden_gdy_cokolwiek_padlo(cli, monkeypatch, capsys):
    """Cron musi zobaczyc niezerowy kod, inaczej awaria przejdzie niezauwazona."""
    monkeypatch.setattr(_FakeWorkflow, "smoke_wyniki",
                        [_wynik("a", True), _wynik("b", False)])
    assert cli("--only", "smoke") == 1
    assert "[FAIL] b" in capsys.readouterr().out


def test_pipeline_przekazuje_dry_run(cli):
    cli("--only", "pipeline", "--dry-run")
    assert "pipeline(dry=True)" in _FakeWorkflow.ostatnia.wywolania


def test_pipeline_bez_dry_run_domyslnie(cli):
    cli("--only", "pipeline")
    assert "pipeline(dry=False)" in _FakeWorkflow.ostatnia.wywolania


def test_pipeline_kod_wyjscia_odzwierciedla_porazke(cli, monkeypatch):
    monkeypatch.setattr(_FakeWorkflow, "pipeline_ok", False)
    assert cli("--only", "pipeline") == 1


def test_review_przekazuje_max_legs(cli, capsys):
    assert cli("--only", "review", "--max-legs", "3") == 0
    assert "review(max_legs=3)" in _FakeWorkflow.ostatnia.wywolania


def test_only_ma_pierwszenstwo_nad_faza(cli):
    cli("--faza", "full", "--only", "preflight")
    assert _FakeWorkflow.ostatnia.wywolania == ["preflight"]


def test_user_id_przekazywany_do_workflow(cli):
    cli("--only", "preflight", "--user-id", "77")
    assert _FakeWorkflow.ostatnia.user_id == 77


def test_full_domyslna_faza(cli, capsys):
    assert cli() == 0
    assert "full(skip_smoke=False, dry=False)" in _FakeWorkflow.ostatnia.wywolania
    assert "Report:" in capsys.readouterr().out


def test_full_ze_skip_smoke(cli):
    cli("--skip-smoke")
    assert "skip_smoke=True" in _FakeWorkflow.ostatnia.wywolania[0]


def test_full_zwraca_jeden_gdy_raport_ma_porazki(cli, tmp_path):
    raport = tmp_path / "zly.json"
    raport.write_text('{"summary": {"fail": 2}}', encoding="utf-8")
    assert cli(raport_json=raport) == 1


def test_uszkodzony_raport_nie_wywala_operatora(cli, tmp_path):
    """Brak/zepsuty raport to nie powod, zeby zglaszac awarie calego przebiegu."""
    raport = tmp_path / "zepsuty.json"
    raport.write_text("{niepoprawny", encoding="utf-8")
    assert cli(raport_json=raport) == 0


def test_brak_pliku_raportu_zwraca_zero(cli, tmp_path):
    assert cli(raport_json=tmp_path / "nie_ma.json") == 0


# ══════════════════════════════════════════════════════════════════════════
#  smoke_api.run_api_check
# ══════════════════════════════════════════════════════════════════════════

class _FakeResponse:
    def __init__(self, status=200, dane=None, tekst=""):
        self.status_code = status
        self._dane = dane if dane is not None else {}
        self.text = tekst

    def json(self):
        return self._dane


class _FakeClient:
    """Atrapa TestClient — mapuje sciezke na przygotowana odpowiedz."""

    def __init__(self, odpowiedzi: dict):
        self.odpowiedzi = odpowiedzi
        self.zapytania: list[tuple[str, str]] = []

    def get(self, path, headers=None):
        self.zapytania.append(("GET", path))
        return self.odpowiedzi.get(path, _FakeResponse(404))

    def post(self, path, headers=None, json=None):
        self.zapytania.append(("POST", path))
        return self.odpowiedzi.get(path, _FakeResponse(404))


@pytest.fixture
def smoke(monkeypatch):
    """Podstawia klienta i logowanie — zero ruchu sieciowego i zero DB."""
    stan = {"odpowiedzi": {}}

    def _client():
        return _FakeClient(stan["odpowiedzi"])

    monkeypatch.setattr(sa, "_client", _client)
    monkeypatch.setattr(sa, "_headers", lambda c: {"Authorization": "Bearer test"})
    monkeypatch.setattr(sa, "_login", lambda c: "token123")
    monkeypatch.setattr(sa, "_token_cache", "token123")
    return stan


def test_health_ok(smoke):
    smoke["odpowiedzi"]["/health"] = _FakeResponse(200, {"status": "ok"})
    assert sa.run_api_check("health", "api.health").ok is True


def test_health_fail_gdy_zly_status_w_body(smoke):
    """HTTP 200 z body {'status': 'degraded'} to NIE jest zdrowe API."""
    smoke["odpowiedzi"]["/health"] = _FakeResponse(200, {"status": "degraded"})
    assert sa.run_api_check("health", "api.health").ok is False


def test_status_endpoint(smoke):
    smoke["odpowiedzi"]["/api/status"] = _FakeResponse(200, {})
    assert sa.run_api_check("status", "api.status").ok is True


def test_coupons_active_wymaga_listy(smoke):
    smoke["odpowiedzi"]["/api/coupons/active"] = _FakeResponse(200, [])
    assert sa.run_api_check("coupons_active", "c").ok is True

    smoke["odpowiedzi"]["/api/coupons/active"] = _FakeResponse(200, {"nie": "lista"})
    assert sa.run_api_check("coupons_active", "c").ok is False


def test_matches_today(smoke):
    smoke["odpowiedzi"]["/api/matches/today"] = _FakeResponse(200, [{"id": 1}])
    assert sa.run_api_check("matches_today", "m").ok is True


def test_matches_analyze_bez_meczow_jest_ok(smoke):
    """Brak meczow dzisiaj to normalny stan, nie awaria API."""
    smoke["odpowiedzi"]["/api/matches/today"] = _FakeResponse(200, [])
    assert sa.run_api_check("matches_analyze", "m").ok is True


def test_matches_analyze_z_meczami(smoke):
    smoke["odpowiedzi"]["/api/matches/today"] = _FakeResponse(200, [{"id": 1}, {"id": 2}])
    smoke["odpowiedzi"]["/api/matches/analyze"] = _FakeResponse(200, [{"wynik": 1}])
    assert sa.run_api_check("matches_analyze", "m").ok is True


def test_matches_analyze_fail_gdy_today_padlo(smoke):
    smoke["odpowiedzi"]["/api/matches/today"] = _FakeResponse(500)
    assert sa.run_api_check("matches_analyze", "m").ok is False


def test_coupon_kelly_wymaga_stawki_w_odpowiedzi(smoke):
    smoke["odpowiedzi"]["/api/coupon/kelly"] = _FakeResponse(200, {"stake_pln": 10})
    assert sa.run_api_check("coupon_kelly", "k").ok is True

    smoke["odpowiedzi"]["/api/coupon/kelly"] = _FakeResponse(200, {"brak": "pola"})
    assert sa.run_api_check("coupon_kelly", "k").ok is False


def test_coupon_place_validate_ok_przy_walidacji(smoke):
    smoke["odpowiedzi"]["/api/coupon/place"] = _FakeResponse(200, {"validated": True})
    assert sa.run_api_check("coupon_place_validate", "p").ok is True


def test_coupon_place_validate_ok_takze_przy_400(smoke):
    """400 = walidacja odrzucila, ale NIC nie zapisano — to tez sukces smoke'a."""
    smoke["odpowiedzi"]["/api/coupon/place"] = _FakeResponse(400, {})
    assert sa.run_api_check("coupon_place_validate", "p").ok is True


def test_coupon_place_200_bez_validated_to_porazka(smoke):
    """200 bez `validated` znaczy, ze endpoint mogl ZAPISAC kupon — alarm."""
    smoke["odpowiedzi"]["/api/coupon/place"] = _FakeResponse(200, {"id": 99})
    assert sa.run_api_check("coupon_place_validate", "p").ok is False


def test_nieznany_check_to_porazka(smoke):
    """Literowka w manifescie nie moze dawac cichego OK."""
    wynik = sa.run_api_check("czegos_takiego_nie_ma", "x")
    assert wynik.ok is False
    assert "failed" in wynik.stderr_tail


def test_wyjatek_zamieniany_na_wynik_a_nie_wysypke(smoke, monkeypatch):
    def _wybuch():
        raise RuntimeError("API nie wstalo")

    monkeypatch.setattr(sa, "_client", _wybuch)
    wynik = sa.run_api_check("health", "api.health")
    assert wynik.ok is False
    assert "API nie wstalo" in wynik.stderr_tail


def test_wynik_ma_ustawione_pola_diagnostyczne(smoke):
    smoke["odpowiedzi"]["/health"] = _FakeResponse(200, {"status": "ok"})
    wynik = sa.run_api_check("health", "api.health")
    assert wynik.capability_id == "api.health"
    assert wynik.exit_code == 0
    assert wynik.stdout_tail == "health"
    assert wynik.duration_s >= 0
