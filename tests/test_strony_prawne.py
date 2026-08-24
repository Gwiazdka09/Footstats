"""Regulamin i polityka prywatności muszą opisywać serwis, który naprawdę istnieje.

Kierunek ustalony 2026-08-24: **wypuszczamy za darmo**, bez firmy, bez reklam
(patrz `.claude/rules/wypuszczenie-pl.md`). Regulamin był pisany pod porzucony
pivot monetyzacyjny sprzed 2026-07-06 i opisywał subskrypcje, auto-odnawianie
oraz Lemon Squeezy/Paddle — produkt, którego nie ma.

Trzy rzeczy były realnie ryzykowne, nie tylko nieaktualne:

1. §7 ograniczał odpowiedzialność do „opłat poniesionych w ciągu ostatnich 30 dni".
   Przy serwisie darmowym to zero, czyli **całkowite wyłączenie odpowiedzialności
   wobec konsumenta** — typowy kandydat na klauzulę niedozwoloną.
2. §10 narzucał sąd właściwy dla „siedziby Operatora". Wobec konsumenta takie
   zastrzeżenie ogranicza mu prawo do sądu miejsca zamieszkania.
3. Brakowało trybu postępowania reklamacyjnego, którego wymaga ustawa
   o świadczeniu usług drogą elektroniczną (art. 8) od każdego regulaminu.

Testy pilnują STANU, nie brzmienia — sprawdzają, czego w dokumencie być nie może
i co musi być, żeby zmiana treści nie wymagała przepisywania asercji.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KORZEN = Path(__file__).resolve().parents[1]
REGULAMIN = KORZEN / "src" / "footstats" / "api" / "regulamin.html"
POLITYKA = KORZEN / "src" / "footstats" / "api" / "polityka_prywatnosci.html"


def _regulamin() -> str:
    return REGULAMIN.read_text(encoding="utf-8")


# ── serwis jest darmowy: nie wolno opisywać płatności, których nie ma ───────

@pytest.mark.parametrize("fraza", [
    "Lemon Squeezy", "Paddle", "odnawiana automatycznie",
    "okresu rozliczeniowego", "przed dokonaniem zakupu",
])
def test_brak_opisu_nieistniejacych_platnosci(fraza: str):
    assert fraza not in _regulamin(), (
        f"regulamin opisuje '{fraza}', a serwis jest darmowy"
    )


def test_regulamin_mowi_wprost_ze_serwis_jest_nieodplatny():
    """Cisza nie wystarcza — użytkownik ma wiedzieć, że nic nie zapłaci."""
    assert re.search(r"nieodpłat|bezpłat|darmow", _regulamin(), re.IGNORECASE)


# ── odpowiedzialność: brak zera dla konsumenta ─────────────────────────────

def test_odpowiedzialnosc_nie_jest_ograniczona_do_oplat():
    """Przy darmowym „do wysokości opłat" znaczy „do zera"."""
    assert "wysokości opłat poniesionych" not in _regulamin()


def test_ostrzezenie_o_ryzyku_zostaje():
    tresc = _regulamin()
    assert "Graj odpowiedzialnie" in tresc
    assert "nie jest bukmacherem" in tresc


# ── wymogi ustawy o świadczeniu usług drogą elektroniczną ──────────────────

def test_jest_tryb_reklamacyjny():
    """Art. 8 uśude: regulamin określa tryb postępowania reklamacyjnego."""
    assert re.search(r"reklamac", _regulamin(), re.IGNORECASE), (
        "regulamin nie opisuje trybu reklamacyjnego"
    )


def test_jest_adres_kontaktowy():
    assert re.search(r"mailto:[^\"']+@[^\"']+", _regulamin())


def test_sad_wlasciwy_nie_narzucony_konsumentowi():
    """Zastrzeżenie sądu „właściwego dla siedziby Operatora" odbiera konsumentowi
    prawo do sądu miejsca zamieszkania."""
    assert "właściwy dla siedziby Operatora" not in _regulamin()


# ── dane operatora ─────────────────────────────────────────────────────────

def test_nie_powoluje_sie_na_nieistniejaca_firme():
    """Regulamin zakładał rejestrację JDG, której nie ma i nie będzie —
    kierunek to działalność nierejestrowana albo brak przychodów w ogóle."""
    assert "po rejestracji JDG" not in _regulamin()


def test_placeholder_danych_operatora_wciaz_do_uzupelnienia():
    """TRIPWIRE, nie asercja poprawności — świadomie odwrócona.

    Ustawa o świadczeniu usług drogą elektroniczną (art. 5) wymaga podania imienia,
    nazwiska i adresu. Tych danych nie ma w repozytorium i nie mogę ich wymyślić.
    Dopóki w dokumencie siedzi placeholder, ten test przechodzi i przypomina,
    że **publikacja jest zablokowana na L1**.

    Gdy dane zostaną wpisane, test zacznie padać — i to jest cel: wymusza
    zamknięcie L1 w TODO oraz odwrócenie tej asercji na `not in`.
    """
    for plik in (REGULAMIN, POLITYKA):
        assert "UZUPEŁNIĆ PRZED PUBLIKACJĄ" in plik.read_text(encoding="utf-8"), (
            f"{plik.name}: placeholder zniknął — uzupełnij L1 w TODO.md "
            "i odwróć ten test na `not in`"
        )


def test_zaden_dokument_nie_zaklada_nip_ani_firmy():
    """Polityka miała placeholder „NIP: [NIP]". Osoba fizyczna prowadząca serwis
    nieodpłatnie nie ma NIP-u nadanego dla działalności — pole zostałoby puste
    albo, gorzej, wypełnione prywatnym NIP-em bez potrzeby."""
    for plik in (REGULAMIN, POLITYKA):
        tresc = plik.read_text(encoding="utf-8")
        assert "NIP: [NIP]" not in tresc
        assert "nazwa firmy" not in tresc


# ── polityka prywatności ───────────────────────────────────────────────────

def test_polityka_opisuje_usuniecie_konta():
    """`DELETE /api/auth/me` istnieje i jest w GUI — polityka ma o tym mówić."""
    assert re.search(r"usun|usuni", POLITYKA.read_text(encoding="utf-8"), re.IGNORECASE)


def test_polityka_wskazuje_faktycznego_dostawce_bazy():
    """Polityka wymieniała **Neon.tech**, a produkcja stoi na Supabase od 18.07.2026
    (migracja po quota-blocku Neona). Wskazanie nieprawdziwego podprocesora jest
    poważniejsze niż nieaktualna wzmianka o płatnościach: RODO wymaga, by lista
    odbiorców danych odpowiadała stanowi faktycznemu.

    Zweryfikowane 24.08 na produkcji — host bazy to `*.pooler.supabase.com`.
    """
    tresc = POLITYKA.read_text(encoding="utf-8")

    assert "Neon" not in tresc, "polityka wskazuje Neon, a dane leżą na Supabase"
    assert "Supabase" in tresc


@pytest.mark.parametrize("fraza", ["Lemon Squeezy", "Paddle", "Merchant of Record"])
def test_polityka_nie_wymienia_procesora_platnosci(fraza: str):
    """Podprocesor, który nie dostaje żadnych danych, nie ma prawa być na liście."""
    assert fraza not in POLITYKA.read_text(encoding="utf-8")


def test_okres_przechowywania_nie_zalezy_od_subskrypcji():
    """„Przez czas trwania subskrypcji" nie znaczy nic, skoro subskrypcji nie ma —
    a okres retencji jest obowiązkowym elementem informacji z art. 13 RODO."""
    assert "czas trwania subskrypcji" not in POLITYKA.read_text(encoding="utf-8")
