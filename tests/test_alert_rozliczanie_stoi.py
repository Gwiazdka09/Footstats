"""Rozliczanie stało 8 dni i nikt się nie dowiedział.

ŚLAD Z PRODUKCJI (`cron_settle`, pełna sekwencja z logów):

    15.08 21:30   settled 20, partial 24     ← działało
    16.08 06:00   settled  0, partial 24
    17.08 … 23.08 settled  0 za każdym razem

Osiem dni zera przy 20+ kuponach czekających. Liczba PARTIAL spadała wyłącznie
przez VOID po 10 dniach, nie przez rozliczenia. Przyczyną było zawieszone konto
API-Football (`Your account is suspended`) — ale żaden warunek tego nie łapał.
Skutek zauważył dopiero `pipeline-health`, i to pośrednio, po dwóch tygodniach:
„26 predykcji bez rozliczenia".

DLACZEGO WARUNEK NIE MOŻE BRZMIEĆ „rozliczono 0 przy niepustej kolejce":
dziś to prawda i będzie prawdą codziennie, bo w kolejce siedzą kupony z 14-15.08,
których wyniku żadne darmowe źródło już nie ma (poza oknem API-Football, poza
7 dniami FlashScore). Taki alarm wyłby bez powodu — czyli powtórzyłby dokładnie
błąd naprawiany 23.08 rano, gdzie alarm o „ZERO predykcji" palił się wiecznie
i przez to przestał cokolwiek znaczyć.

WŁAŚCIWY WARUNEK: rozliczono 0, CHOĆ coś czekającego jest jeszcze w zasięgu
źródeł. Wtedy 16.08 (kupony jednodniowe, w zasięgu) alarm by się zapalił,
a dziś (wszystko 8-9 dni) milczy — bo milczenie jest poprawną odpowiedzią,
skoro nie da się już nic zrobić.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from footstats.core.coupon_settlement import HORYZONT_ZRODEL_DNI, rozliczanie_stoi


def _dni_temu(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


# ── sedno: zapalić się wtedy, kiedy trzeba ──────────────────────────────────

def test_zero_rozliczen_przy_swiezych_kuponach_to_awaria():
    """Dokładnie 16.08: kupony jednodniowe, źródła je mają, a rozliczono 0."""
    komunikat = rozliczanie_stoi(settled=0, czekajace_w_zasiegu=24)

    assert komunikat is not None
    assert "24" in komunikat


def test_zero_rozliczen_gdy_wszystko_poza_zasiegiem_to_NIE_awaria():
    """Stan z 23.08. Milczenie jest poprawne — nic się już nie da zrobić,
    a alarm palący się codziennie przestaje cokolwiek znaczyć."""
    assert rozliczanie_stoi(settled=0, czekajace_w_zasiegu=0) is None


def test_udane_rozliczenie_milczy():
    assert rozliczanie_stoi(settled=20, czekajace_w_zasiegu=24) is None


def test_pusta_kolejka_milczy():
    assert rozliczanie_stoi(settled=0, czekajace_w_zasiegu=0) is None


# ── liczenie tego, co jeszcze w zasięgu ─────────────────────────────────────

def test_horyzont_obejmuje_najdluzej_siegajace_zrodlo():
    """FlashScore sięga ~7 dni — dopóki któreś źródło może odpowiedzieć,
    brak rozliczenia jest podejrzany."""
    assert HORYZONT_ZRODEL_DNI == 7


@pytest.mark.parametrize("dni,oczekiwane", [(0, True), (1, True), (7, True), (8, False), (30, False)])
def test_czy_data_jeszcze_osiagalna(dni, oczekiwane):
    from footstats.core.coupon_settlement import data_jeszcze_osiagalna

    assert data_jeszcze_osiagalna(_dni_temu(dni)) is oczekiwane


def test_data_nie_do_sparsowania_nie_liczy_sie_jako_osiagalna():
    from footstats.core.coupon_settlement import data_jeszcze_osiagalna

    assert data_jeszcze_osiagalna("nie-data") is False


def test_kupony_z_1408_dzis_juz_poza_zasiegiem():
    """Kotwica na realnym stanie produkcji z 23.08: te kupony są nie do odzyskania,
    więc nie mają prawa generować alarmu."""
    from footstats.core.coupon_settlement import data_jeszcze_osiagalna

    assert data_jeszcze_osiagalna(_dni_temu(9)) is False


# ── alarm faktycznie wychodzi z endpointu ───────────────────────────────────

def test_endpoint_alarmuje_gdy_rozliczanie_stoi(monkeypatch):
    """Detektor bez podpięcia jest martwym kodem — sprawdzamy realną drogę."""
    import footstats.api.routes.coupons as rc
    import footstats.core.coupon_settlement as cs
    import footstats.utils.telegram_notify as tg

    monkeypatch.setenv("CRON_SECRET", "sekret")
    monkeypatch.setattr(cs, "settle_active_coupons",
                        lambda **kw: {"settled": 0, "partial": 24, "errors": 0,
                                      "voided": 0, "czekajace_w_zasiegu": 24})
    wyslane = []
    monkeypatch.setattr(tg, "send_alert", lambda tytul, tresc: wyslane.append(tresc))

    odp = rc.cron_settle(x_cron_secret="sekret")

    assert odp["czekajace_w_zasiegu"] == 24
    assert wyslane, "alarm o stojacym rozliczaniu nie wyszedl"


def test_endpoint_milczy_gdy_wszystko_poza_zasiegiem(monkeypatch):
    """Stan z 23.08 — kolejka pełna, ale nic się już nie da zdobyć."""
    import footstats.api.routes.coupons as rc
    import footstats.core.coupon_settlement as cs
    import footstats.utils.telegram_notify as tg

    monkeypatch.setenv("CRON_SECRET", "sekret")
    monkeypatch.setattr(cs, "settle_active_coupons",
                        lambda **kw: {"settled": 0, "partial": 21, "errors": 0,
                                      "voided": 0, "czekajace_w_zasiegu": 0})
    wyslane = []
    monkeypatch.setattr(tg, "send_alert", lambda tytul, tresc: wyslane.append(tresc))

    rc.cron_settle(x_cron_secret="sekret")

    assert wyslane == [], "alarm palacy sie codziennie przestaje cokolwiek znaczyc"


def test_padniety_telegram_nie_wywala_rozliczania(monkeypatch):
    """Powiadomienie to dodatek — jego awaria nie może zabić crona."""
    import footstats.api.routes.coupons as rc
    import footstats.core.coupon_settlement as cs
    import footstats.utils.telegram_notify as tg

    monkeypatch.setenv("CRON_SECRET", "sekret")
    monkeypatch.setattr(cs, "settle_active_coupons",
                        lambda **kw: {"settled": 0, "partial": 5, "errors": 0,
                                      "voided": 0, "czekajace_w_zasiegu": 5})

    def wybucha(*a, **kw):
        raise OSError("telegram padl")

    monkeypatch.setattr(tg, "send_alert", wybucha)

    odp = rc.cron_settle(x_cron_secret="sekret")

    assert odp["ok"] is True


# ── mecz z DZISIAJ jeszcze się nie odbył — alarm nie ma prawa się zapalić ───
#
# ZMIERZONE NA PRODUKCJI 24.08 o 14:35 UTC: `/cron/settle` zwrócił
# {settled: 0, partial: 33, czekajace_w_zasiegu: 14}, alarm poszedł na Telegram,
# a wszystkie 14 „czekających w zasięgu" to kupony #150-163 na mecze z TEGO DNIA,
# z których pierwszy zaczynał się dopiero o 15:30 UTC. Rozliczono zero, bo nie
# było czego rozliczać.
#
# Sekwencja gwarantuje powtórkę CODZIENNIE: draft tworzy kupony o 05:30 UTC,
# `settle-morning` rusza o 06:00 — pół godziny później, zawsze przed pierwszym
# gwizdkiem. Alarm zapalałby się każdego ranka i po tygodniu przestałby cokolwiek
# znaczyć, czyli dokładnie ten błąd, przed którym ostrzega docstring tego modułu.
#
# Dlaczego próg to CAŁA doba, a nie „dziś, ale po ostatnim meczu": kupon trzyma samą
# DATĘ (`match_date_first`), bez godziny. Mecze brazylijskie z tej puli zaczynały się
# o 22:30 i 23:00 UTC, więc nawet wieczorny przebieg o 21:30 UTC nie może zakładać,
# że dzień jest zamknięty.

def test_dzisiejszy_mecz_nie_liczy_sie_jako_zalegly():
    from footstats.core.coupon_settlement import czeka_zbyt_dlugo

    assert czeka_zbyt_dlugo(_dni_temu(0)) is False


@pytest.mark.parametrize("dni,oczekiwane", [
    (1, True), (7, True), (8, False), (30, False),
])
def test_zaleglosc_liczy_sie_od_wczoraj_do_horyzontu(dni: int, oczekiwane: bool):
    from footstats.core.coupon_settlement import czeka_zbyt_dlugo

    assert czeka_zbyt_dlugo(_dni_temu(dni)) is oczekiwane


def test_data_z_przyszlosci_nie_jest_zalegloscia():
    """Terminarz bywa przesuwany do przodu — to nie jest zaległość."""
    from footstats.core.coupon_settlement import czeka_zbyt_dlugo

    jutro = (date.today() + timedelta(days=1)).isoformat()
    assert czeka_zbyt_dlugo(jutro) is False


def test_smiec_zamiast_daty_nie_alarmuje():
    from footstats.core.coupon_settlement import czeka_zbyt_dlugo

    assert czeka_zbyt_dlugo("nie-data") is False


def test_osiagalnosc_zrodel_zostaje_szersza_niz_zaleglosc():
    """Dwa różne pytania: `data_jeszcze_osiagalna` = czy źródło ODPOWIE (0-7 dni),
    `czeka_zbyt_dlugo` = czy brak wyniku jest już PODEJRZANY (1-7 dni).
    Rozjechanie ich w jedną funkcję dało fałszywy alarm z 24.08."""
    from footstats.core.coupon_settlement import (
        czeka_zbyt_dlugo, data_jeszcze_osiagalna,
    )

    dzis = _dni_temu(0)
    assert data_jeszcze_osiagalna(dzis) is True
    assert czeka_zbyt_dlugo(dzis) is False
