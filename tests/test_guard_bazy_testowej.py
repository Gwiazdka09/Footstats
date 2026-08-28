"""Guard, który nie pozwala suicie pisać do produkcyjnej bazy.

INCYDENT 2026-07-29: `pytest tests/` odpalone bez `DATABASE_URL=""` poszło na
produkcyjne Supabase. Testy obciążyły papierowy bankroll Admin_JG o 2 PLN
i dopisały wiersz do `bankroll_history` — trzeba to było cofać ręcznie. Reguła
„testy nie dotykają proda" istniała w dokumentacji i nic jej nie egzekwowało.

Guard powstał wtedy jako DENYLISTA znanych hostów produkcyjnych. Ten plik
powstał 28.08 przy odwracaniu go na ALLOWLISTĘ i jest pierwszym testem tego
mechanizmu w ogóle — dotąd jedyna rzecz pilnująca całej suity przed zapisem do
proda sama nie była niczym pilnowana.

DLACZEGO ODWRÓCENIE: denylista gnije w jedną stronę. Baza przeprowadziła się już
raz (Neon → Supabase, 18.07) i lista przetrwała wyłącznie dlatego, że ktoś ją
ręcznie dopisał. Przy następnej przeprowadzce guard dalej wyglądałby na
działający, a nie chroniłby przed niczym — dokładnie ten kształt cichej
degradacji, który w tym projekcie kosztował już sześć dni potoku.
"""
from __future__ import annotations

import pytest

from tests.conftest import _ENV_OBEJSCIE, _powod_odmowy

PROD = "postgresql://user:tajnehaslo@db.abcdefgh.supabase.co:5432/postgres"
NEON = "postgresql://user:tajnehaslo@ep-cool-1.eu-central-1.aws.neon.tech/neondb"
OBCA_CHMURA = "postgresql://user:tajnehaslo@db.jakis-nowy-dostawca.io:5432/footstats"
LOKALNA = "postgresql://postgres:postgres@localhost:5432/footstats"
TESTOWA = "postgresql://user:tajnehaslo@db.abcdefgh.supabase.co:5432/footstats_test"


# ── to, po co guard istnieje ────────────────────────────────────────────────

def test_znana_produkcja_jest_blokowana():
    assert _powod_odmowy(PROD) is not None
    assert _powod_odmowy(NEON) is not None


def test_NIEZNANY_host_tez_jest_blokowany():
    """SEDNO ODWRÓCENIA. Denylista przepuszczała wszystko, czego nie znała —
    więc pierwszy dzień po przeprowadzce bazy suita znów pisałaby do proda.
    Allowlista wymaga świadomej decyzji zamiast trafienia w listę."""
    powod = _powod_odmowy(OBCA_CHMURA)
    assert powod is not None
    assert "footstats" in powod and "jakis-nowy-dostawca.io" in powod


def test_znana_produkcja_dostaje_ostrzejszy_komunikat():
    """Rozróżnienie zostaje: „to JEST prod" niesie inną informację niż
    „nie wiem, co to jest"."""
    assert "ZNANA" in (_powod_odmowy(PROD) or "")
    assert "ZNANA" not in (_powod_odmowy(OBCA_CHMURA) or "")


# ── to, czego guard blokować NIE MOŻE ───────────────────────────────────────

def test_tryb_unit_przechodzi():
    """`DATABASE_URL=""` to sposób, w jaki działa CI i cała suita lokalnie."""
    assert _powod_odmowy("") is None


def test_baza_lokalna_przechodzi():
    assert _powod_odmowy(LOKALNA) is None


def test_baza_z_test_w_nazwie_przechodzi():
    """Nawet na hoście produkcyjnego dostawcy — liczy się osobna baza,
    nie adres serwera. Inaczej nie dałoby się mieć testowej bazy obok proda."""
    assert _powod_odmowy(TESTOWA) is None


# ── higiena komunikatu ──────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [PROD, NEON, OBCA_CHMURA])
def test_komunikat_nie_zdradza_hasla_ani_loginu(url: str):
    """Komunikat leci na stdout CI i do logów. Reguła bezpieczeństwa repo:
    błędy nie wyciekają danych wrażliwych."""
    powod = _powod_odmowy(url) or ""
    assert "tajnehaslo" not in powod
    assert "user" not in powod
    assert "@" not in powod


def test_smiec_zamiast_url_nie_wywala_sesji():
    """Guard biegnie w `pytest_configure`. Wyjątek tutaj wysadziłby CAŁĄ sesję
    komunikatem o parsowaniu zamiast o bazie."""
    for smiec in ("nie-url", "://", "postgresql://"):
        assert _powod_odmowy(smiec) is not None or True  # ma nie rzucać


def test_obejscie_jest_jawna_zmienna_a_nie_ukryta_flaga():
    """Świadome uderzenie w proda musi wymagać nazwanej decyzji — i musi dać
    się znaleźć grepem, gdy ktoś zapomni jej wyłączyć."""
    assert _ENV_OBEJSCIE == "FOOTSTATS_ALLOW_PROD_DB"
