"""Alarm o stojącym rozliczaniu ma milczeć na kuponach, których już nie odzyskamy.

ZMIERZONE NA PRODUKCJI 24.09.2026 (`gcloud logging read`, 8 dni wstecz): alarm
„rozliczanie stoi" poszedł **11 razy** — 16, 18, 19, 20, 21 (trzy razy), 22 i 23
września. Za każdym razem `czekajace_w_zasiegu` wynosiło 1–5, a od 19.09 stale 3:
to te same kupony #609, #618 i #619, na mecze z lig bez pokrycia źródeł wyników
(Brasileirão Série B, USL — zero wystąpień w zbiorze 40 lig).

Reakcji nie ma i nie będzie: wyniku nie ma skąd wziąć, a kupon sam zniknie po
`VOID_AFTER_DAYS`. Alarm, który zapala się codziennie i nic nie znaczy, uczy
ignorowania alarmów — i wtedy przestaje działać ten jeden, który znaczy coś
naprawdę. Dokładnie ten błąd naprawiano 23.08 przy alarmie o „ZERO predykcji"
i 24.08 przy `czeka_zbyt_dlugo`.

ROZRÓŻNIENIE, KTÓREGO BRAKOWAŁO: „jeszcze nie próbowaliśmy" kontra „próbowaliśmy
wiele razy i źródła nie mają wyniku". Predykcje mają to od 14.08 (`settle_attempts`
+ `MAX_PROB_ROZLICZENIA`), kupony nie miały nic — liczyły się do alarmu aż do VOID.

DLACZEGO TO NIE UCISZA PRAWDZIWEJ AWARII: przy zepsutym źródle codziennie
przychodzą NOWE kupony, więc zawsze istnieją takie z małą liczbą prób i alarm
leci dalej. Milkną tylko kupony, które przestały być odzyskiwalne — a te i tak
zgłasza osobny alarm `kupony_przepadly` w momencie VOID-owania.
"""
from __future__ import annotations

from footstats.core.coupon_settlement import (
    MAX_PROB_ROZLICZENIA_KUPONU,
    czeka_na_wynik_osiagalny,
    rozliczanie_stoi,
)


def _nogi(proby: int, ile: int = 1) -> list[dict]:
    return [{"home": "A", "away": "B", "tip": "1", "proby": proby} for _ in range(ile)]


def test_swiezy_kupon_liczy_sie_do_alarmu():
    """Pierwsze próby to normalny stan — jeśli wyniku brak, coś może być zepsute."""
    assert czeka_na_wynik_osiagalny(_nogi(proby=1)) is True


def test_kupon_na_granicy_prob_jeszcze_sie_liczy():
    assert czeka_na_wynik_osiagalny(_nogi(proby=MAX_PROB_ROZLICZENIA_KUPONU - 1)) is True


def test_kupon_po_wyczerpaniu_prob_nie_liczy_sie_do_alarmu():
    """SEDNO: #609/#618/#619 przestają podnosić alarm, bo próbowaliśmy wiele razy."""
    assert czeka_na_wynik_osiagalny(_nogi(proby=MAX_PROB_ROZLICZENIA_KUPONU)) is False
    assert czeka_na_wynik_osiagalny(_nogi(proby=MAX_PROB_ROZLICZENIA_KUPONU + 7)) is False


def test_kupon_bez_licznika_liczy_sie_do_alarmu():
    """Kupony sprzed tej zmiany nie mają pola `proby`. Traktujemy je jak świeże —
    inaczej wdrożenie uciszyłoby alarm dla wszystkiego, co już wisi w bazie."""
    assert czeka_na_wynik_osiagalny([{"home": "A", "away": "B", "tip": "1"}]) is True


def test_liczy_sie_najwyzsza_liczba_prob_wsrod_nog():
    """Kupon jest tak stary, jak jego najstarsza noga — jedna świeża noga nie
    czyni świeżym kuponu, który wisi od dwóch tygodni."""
    nogi = [
        {"home": "A", "away": "B", "tip": "1", "proby": MAX_PROB_ROZLICZENIA_KUPONU + 3},
        {"home": "C", "away": "D", "tip": "1", "proby": 0},
    ]
    assert czeka_na_wynik_osiagalny(nogi) is False


def test_alarm_dalej_zapala_sie_gdy_sa_swieze_kupony():
    """Prawdziwa awaria: nowe kupony przychodzą codziennie, więc alarm leci."""
    assert rozliczanie_stoi(settled=0, czekajace_w_zasiegu=4) is not None


def test_alarm_milczy_gdy_zostaly_tylko_kupony_po_probach():
    """Stan z 19-23.09: zero rozliczeń, ale nikt już nie odda tych wyników."""
    assert rozliczanie_stoi(settled=0, czekajace_w_zasiegu=0) is None
