"""Draft nie tworzy kuponow na mecze juz rozpoczete (incydent 29.10: 32 kupony na 28.10)."""
import logging
from datetime import datetime, timedelta

from footstats.core.daily_filters import filtruj_rozpoczete

TERAZ = datetime(2026, 10, 29, 5, 32)


def _m(data: str, godz: str = "", g: str = "A", a: str = "B") -> dict:
    return {"data": data, "godzina": godz, "gospodarz": g, "goscie": a}


def test_godzina_w_przeszlosci_odrzucona() -> None:
    assert filtruj_rozpoczete([_m("2026-10-29", "04:00")], teraz=TERAZ) == []


def test_zapas_10_minut_odrzuca_mecz_za_5_min() -> None:
    assert filtruj_rozpoczete([_m("2026-10-29", "05:37")], teraz=TERAZ) == []


def test_mecz_za_2h_przyjety() -> None:
    m = _m("2026-10-29", "07:32")
    assert filtruj_rozpoczete([m], teraz=TERAZ) == [m]


def test_sama_data_wczorajsza_odrzucona_dzisiejsza_przyjeta() -> None:
    dzis = _m("2026-10-29")
    assert filtruj_rozpoczete([_m("2026-10-28"), dzis], teraz=TERAZ) == [dzis]


def test_przypadek_29_10_zero_i_ostrzezenie(caplog) -> None:
    pula = [_m("2026-10-28", "20:00", "Heart of Midlothian", "Rangers"),
            _m("2026-10-28", "", "X", "Y")]
    with caplog.at_level(logging.WARNING):
        assert filtruj_rozpoczete(pula, teraz=TERAZ) == []
    assert "odrzucono 2" in caplog.text and "Heart of Midlothian" in caplog.text


def test_budowa_kuponow_system_uzywa_filtra(monkeypatch) -> None:
    from footstats.core import system_paper
    monkeypatch.setattr(system_paper, "_resolve_system_user_id", lambda: 1)
    monkeypatch.setattr("footstats.core.coupon_tracker.init_coupon_tables", lambda: None)
    stary = _m("2026-10-28", "20:00")
    stary["dt"] = datetime(2026, 10, 28, 20)
    wczoraj = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert system_paper.build_single_leg_coupons([_m(wczoraj, "20:00")]) == 0
