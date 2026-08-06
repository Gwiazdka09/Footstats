"""test_kalibracja_rozliczanie.py — dopisywanie wyników do dziennika kalibracji.

PO CO: dziennik zbiera oceny modelu, ale bez wyników jest bezużyteczny —
kalibracja porównuje przewidziane prawdopodobieństwo z tym, co faktycznie padło.

Ten przebieg jest CELOWO oddzielony od rozliczania kuponów:
  * kupony ścigają się z czasem (bankroll, wypłaty) i mają okno 2-3 dni;
  * dziennik nie ściga się z niczym — może spokojnie nadrabiać zaległości,
    więc bierze szersze okno. Predykcja #8 leżała z gotowym wynikiem od 26.07
    właśnie dlatego, że wypadła z okna kuponów i nikt jej nie odwiedził.

Źródła wyników są współdzielone z rozliczaniem kuponów, więc dziedziczą całą
ochronę przed dopasowaniem cudzego meczu (min zamiast średniej, znaczniki
rezerw) — patrz `test_dopasowanie_nazw_audyt.py`.
"""
from __future__ import annotations

import pytest

from footstats.core import kalibracja_rozlicz as kr


@pytest.fixture
def dziennik(monkeypatch):
    """Podstawia dziennik i źródło wyników; notuje, co zapisano."""
    stan = {
        "pending": [],
        "wyniki": {},          # (home, away, date) -> "2-1"
        "zapisane": [],        # (id, wynik, tip)
        "blad_zrodla": None,
    }

    monkeypatch.setattr(kr, "pobierz_nierozliczone", lambda dni_wstecz=14: stan["pending"])

    def fake_zapisz(wpis_id, wynik, model_tip):
        stan["zapisane"].append((wpis_id, wynik, model_tip))
        return wynik is not None

    def fake_znajdz(home, away, data):
        if stan["blad_zrodla"] is not None:
            raise stan["blad_zrodla"]
        return stan["wyniki"].get((home, away, data))

    monkeypatch.setattr(kr, "zapisz_wynik", fake_zapisz)
    monkeypatch.setattr(kr, "_znajdz_wynik_meczu", fake_znajdz)
    return stan


def _wpis(wpis_id=1, home="Legia", away="Lech", data="2026-08-01", tip="1") -> dict:
    return {"id": wpis_id, "team_home": home, "team_away": away,
            "match_date": data, "model_tip": tip}


# ── przebieg podstawowy ────────────────────────────────────────────────────

def test_brak_zaleglosci_to_zero_pracy(dziennik):
    assert kr.rozlicz_dziennik()["rozliczone"] == 0


def test_rozlicza_wpis_z_dostepnym_wynikiem(dziennik):
    dziennik["pending"] = [_wpis()]
    dziennik["wyniki"] = {("Legia", "Lech", "2026-08-01"): "2-1"}

    raport = kr.rozlicz_dziennik()

    assert raport["rozliczone"] == 1
    assert dziennik["zapisane"] == [(1, "2-1", "1")]


def test_brak_wyniku_zostawia_wpis_w_kolejce(dziennik):
    """Mecz jeszcze nierozegrany albo źródło go nie zna — wpis ma wrócić."""
    dziennik["pending"] = [_wpis()]

    raport = kr.rozlicz_dziennik()

    assert raport["rozliczone"] == 0
    assert raport["bez_wyniku"] == 1
    assert dziennik["zapisane"] == []


def test_przetwarza_wszystkie_wpisy(dziennik):
    dziennik["pending"] = [_wpis(i, home=f"Klub{i}") for i in range(1, 6)]
    dziennik["wyniki"] = {(f"Klub{i}", "Lech", "2026-08-01"): "1-0" for i in range(1, 6)}

    assert kr.rozlicz_dziennik()["rozliczone"] == 5


def test_jeden_bez_wyniku_nie_blokuje_reszty(dziennik):
    dziennik["pending"] = [_wpis(1, home="A"), _wpis(2, home="B"), _wpis(3, home="C")]
    dziennik["wyniki"] = {("A", "Lech", "2026-08-01"): "1-0",
                          ("C", "Lech", "2026-08-01"): "0-2"}

    raport = kr.rozlicz_dziennik()

    assert raport["rozliczone"] == 2
    assert raport["bez_wyniku"] == 1


# ── tryb na sucho ──────────────────────────────────────────────────────────

def test_dry_run_nic_nie_zapisuje(dziennik):
    """Podgląd przed zapisem — ta sama zasada co przy rozliczaniu kuponów."""
    dziennik["pending"] = [_wpis()]
    dziennik["wyniki"] = {("Legia", "Lech", "2026-08-01"): "2-1"}

    raport = kr.rozlicz_dziennik(dry_run=True)

    assert raport["rozliczone"] == 1, "raport ma pokazać, co BY się stało"
    assert dziennik["zapisane"] == []


# ── odporność ──────────────────────────────────────────────────────────────

def test_awaria_zrodla_nie_zatrzymuje_przebiegu(dziennik):
    """Padnięte źródło wyników nie może zablokować całego przebiegu —
    następnym razem spróbujemy ponownie."""
    dziennik["pending"] = [_wpis()]
    dziennik["blad_zrodla"] = RuntimeError("API padlo")

    raport = kr.rozlicz_dziennik()

    assert raport["bledy"] == 1
    assert raport["rozliczone"] == 0


def test_bledy_liczone_osobno_od_braku_wyniku(dziennik):
    """„Źródło padło" to co innego niż „mecz jeszcze nie rozegrany" —
    pierwsze wymaga reakcji, drugie jest normalne."""
    dziennik["pending"] = [_wpis(1, home="A"), _wpis(2, home="B")]
    dziennik["wyniki"] = {}

    raport = kr.rozlicz_dziennik()

    assert raport["bledy"] == 0
    assert raport["bez_wyniku"] == 2


def test_okno_przekazane_do_zapytania(dziennik, monkeypatch):
    przekazane = []
    monkeypatch.setattr(kr, "pobierz_nierozliczone",
                        lambda dni_wstecz=14: przekazane.append(dni_wstecz) or [])

    kr.rozlicz_dziennik(dni_wstecz=30)

    assert przekazane == [30]


def test_okno_domyslne_szersze_niz_kuponowe(dziennik, monkeypatch):
    """Kupony mają 2-3 dni; dziennik nie ściga się z czasem i nadrabia zaległości."""
    przekazane = []
    monkeypatch.setattr(kr, "pobierz_nierozliczone",
                        lambda dni_wstecz=14: przekazane.append(dni_wstecz) or [])

    kr.rozlicz_dziennik()

    assert przekazane[0] >= 7


def test_raport_zawiera_komplet_liczb(dziennik):
    dziennik["pending"] = [_wpis()]

    raport = kr.rozlicz_dziennik()

    assert set(raport) >= {"sprawdzone", "rozliczone", "bez_wyniku", "bledy"}


def test_sprawdzone_liczy_wszystkie_wpisy(dziennik):
    dziennik["pending"] = [_wpis(i, home=f"K{i}") for i in range(1, 4)]

    assert kr.rozlicz_dziennik()["sprawdzone"] == 3
