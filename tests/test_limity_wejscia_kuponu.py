"""Kupon z wejścia użytkownika ma górne granice, nie tylko dolne.

ZNALEZISKO (audyt bezpieczeństwa 24.09.2026): `_validate_manual_coupon` pilnował
dolnych granic (stawka > 0, kurs > 1.0, pola niepuste) i długości pojedynczych
napisów, ale NIE liczby nóg ani wysokości stawki. `POST /api/coupon/manual` z
listą stu tysięcy nóg przechodził walidację i lądował w bazie jako jeden
gigantyczny `legs_json`.

Skutki są dwa i oba dotykają innych użytkowników, nie tylko autora:

* wiersz `coupons` puchnie bez ograniczenia, a `GET /api/coupons` zwraca go
  w całości — jeden wpis potrafi zatkać odpowiedź i przekroczyć timeout 10 s
  ustawiony w `api/main`;
* rejestracja jest otwarta, więc kosztem ataku jest jedno konto.

Rejestracja otwarta znaczy też, że limity muszą być w KODZIE, nie w dobrej woli
GUI — formularz frontu nie jest granicą systemu.

Granica na liczbę nóg to ta sama wartość, co w `/coupon/preview-signal`
(`_MAX_PREVIEW_LEGS = 30`) — istniała tam od początku, a w zapisie jej nie było,
czyli podgląd był ostrożniejszy niż zapis do bazy.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

import footstats.api.routes.coupons as coupons


def _noga(i: int = 0) -> dict:
    return {"home": f"Gospodarz {i}", "away": f"Gosc {i}", "tip": "1", "odds": 1.85}


def _zadanie(ile_nog: int = 1, stawka: float = 10.0) -> coupons.ManualCouponRequest:
    return coupons.ManualCouponRequest(
        legs=[coupons.ManualLeg(**_noga(i)) for i in range(ile_nog)],
        stake_pln=stawka,
    )


def test_normalny_kupon_przechodzi():
    coupons._validate_manual_coupon(_zadanie(ile_nog=4, stawka=25.0))


def test_kupon_na_granicy_przechodzi():
    coupons._validate_manual_coupon(_zadanie(ile_nog=coupons._MAX_NOG_KUPONU))


def test_za_duzo_nog_odrzucone():
    with pytest.raises(HTTPException) as exc:
        coupons._validate_manual_coupon(_zadanie(ile_nog=coupons._MAX_NOG_KUPONU + 1))
    assert exc.value.status_code == 400
    assert "nog" in exc.value.detail.lower() or "nóg" in exc.value.detail.lower()


def test_tysiac_nog_nie_trafia_do_bazy():
    """Scenariusz z opisu: jeden request, jeden gigantyczny wiersz."""
    with pytest.raises(HTTPException) as exc:
        coupons._validate_manual_coupon(_zadanie(ile_nog=1000))
    assert exc.value.status_code == 400


def test_absurdalna_stawka_odrzucona():
    """Dziennik liczy jednostki, nie prawdziwe pieniądze — ale 10^12 w statystyce
    rozjeżdża ROI i wykres postępu wszystkim, kto trafi na taki wpis w rankingu.
    """
    with pytest.raises(HTTPException) as exc:
        coupons._validate_manual_coupon(_zadanie(stawka=coupons._MAX_STAWKI + 1))
    assert exc.value.status_code == 400


def test_stawka_na_granicy_przechodzi():
    coupons._validate_manual_coupon(_zadanie(stawka=coupons._MAX_STAWKI))


def test_limit_nog_nie_jest_luzniejszy_niz_w_podgladzie():
    """Podgląd sygnału miał limit 30 od początku. Zapis do bazy nie może być
    bardziej pobłażliwy niż podgląd, który nic nie zapisuje.
    """
    assert coupons._MAX_NOG_KUPONU <= coupons._MAX_PREVIEW_LEGS
