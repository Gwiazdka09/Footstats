"""Prompt przekraczał budżet tokenów w KAŻDYM przebiegu produkcyjnym.

ZMIERZONE 15.08 na `footstats-final`: prompt 5763 tokenów przy budżecie 4300,
więc `dopasuj_do_budzetu` przycinało go na ślepo w KAŻDYM uruchomieniu. Sam
szkielet (bez ani jednego meczu) zajmował 2077 tokenów — 48% budżetu na samą
instrukcję. Największy tłuszcz: struktura kuponu powielona 4× w przykładzie JSON
i reguła „wysoka pewność + wysoki kurs" powtórzona trzykrotnie.

Ten plik pilnuje DWÓCH rzeczy naraz:
  1. szkielet mieści się w rozsądnym budżecie (bramka regresji, nie ideał),
  2. kompresja NIE zgubiła żadnego zakazu ani elementu kontraktu JSON —
     bo cichy zanik zakazu „kurs < 1.20 NIGDY" zobaczylibyśmy dopiero po
     przegranym kuponie.
"""
from __future__ import annotations

import pytest

from footstats.ai.prompts import build_pewniaczki_prompt

# Bramka na ZNAKACH, nie tokenach — celowo. `szacuj_tokeny` to heurystyka
# 1.4 znaku/token, ustawiona pesymistycznie po produkcyjnym 413; dla szkieletu
# przeszacowuje ~2x (mierzone tokenizerem: 1873 znaki = 655 realnych tokenow,
# heurystyka twierdzi 1338). Test na znakach jest deterministyczny i nie zalezy
# od tego, ktora heurystyka akurat obowiazuje.
#
# Historia: szkielet mial 2907 znakow (~1330 realnych tokenow). Po kompresji
# i przejsciu instrukcji na angielski: 1873 znaki / 655 tokenow — o 51% taniej
# przy tych samych regulach.
MAKS_ZNAKOW_SZKIELETU = 2000


def _szkielet() -> str:
    return build_pewniaczki_prompt(
        n_mecze=5, sygnaly="", kalibracja_str="", feedback_str="",
        mecze_opisy_text="", cel_kuponow_text="",
    )


def test_szkielet_miesci_sie_w_budzecie():
    znaki = len(_szkielet())
    assert znaki <= MAKS_ZNAKOW_SZKIELETU, (
        f"szkielet ma {znaki} znakow — zjada budzet, ktory nalezy sie meczom"
    )


@pytest.mark.parametrize("fragment", [
    "top3", "kupon_a", "kupon_b", "kupon_c", "kupon_d",
    "zdarzenia", "kurs_laczny", "pewnosc_pct", "ryzyko", "ostrzezenia",
])
def test_kontrakt_json_kompletny(fragment):
    """Model musi wiedzieć, jakie klucze ma zwrócić — inaczej potok nic nie zapisze."""
    assert fragment in _szkielet()


@pytest.mark.parametrize("zakaz", [
    "1.20",        # kurs ponizej — nigdy
    "AKO",         # tylko single
    "BetBuilder",  # Over+BTTS z jednego meczu
    "60",          # minimalna pewnosc nogi
    "12%",         # podatek
])
def test_zakazy_przetrwaly_kompresje(zakaz):
    assert zakaz in _szkielet(), f"kompresja zgubila regule: {zakaz}"


def test_wymog_trzech_ryzyk_zostal():
    szk = _szkielet()
    assert "3" in szk and "ryzyko" in szk


def test_dynamiczne_czesci_trafiaja_do_promptu():
    prompt = build_pewniaczki_prompt(
        n_mecze=2, sygnaly="SYGNAL_X", kalibracja_str="KALIB_X",
        feedback_str="FEEDBACK_X", mecze_opisy_text="MECZ_X",
        cel_kuponow_text="CEL_X",
    )
    for znacznik in ("SYGNAL_X", "KALIB_X", "FEEDBACK_X", "MECZ_X", "CEL_X"):
        assert znacznik in prompt


def test_dlugie_wycinki_sa_przycinane():
    """Kalibracja i lekcje mają twarde limity — inaczej jeden długi wpis zjada mecze."""
    prompt = build_pewniaczki_prompt(
        n_mecze=1, sygnaly="", kalibracja_str="K" * 5000, feedback_str="F" * 5000,
        mecze_opisy_text="", cel_kuponow_text="",
    )
    assert prompt.count("K") <= 700
    assert prompt.count("F") <= 500


# ── emoji: 2-4 tokeny za znak, zero informacji ─────────────────────────────

def test_emoji_wycinane_z_dynamicznych_czesci():
    """Ikony czynnikow ida do konsoli i Telegrama — do modelu nie musza."""
    prompt = build_pewniaczki_prompt(
        n_mecze=1, sygnaly="⚔️ Zemsta", kalibracja_str="🏅 patent",
        feedback_str="😫 zmeczenie", mecze_opisy_text="🏰 TWIERDZA(Legia 5m dom)",
        cel_kuponow_text="👑 lider",
    )
    for e in ("⚔️", "🏅", "😫", "🏰", "👑"):
        assert e not in prompt, f"emoji {e} kosztuje 2-4 tokeny i nic nie wnosi"
    # tresc zostaje
    for slowo in ("Zemsta", "patent", "zmeczenie", "TWIERDZA", "lider"):
        assert slowo in prompt


def test_strzalki_zostaja():
    """`→` kosztuje 1 token i rozdziela tresc — ciecie na oslep zabiera sens."""
    from footstats.ai.prompts import bez_emoji
    assert "→" in bez_emoji("λg=1.8 → gospodarz dominuje")


def test_polskie_znaki_nietkniete():
    from footstats.ai.prompts import bez_emoji
    assert bez_emoji("zmęczenie ŁÓDŹ ćwierćfinał") == "zmęczenie ŁÓDŹ ćwierćfinał"


# ── jezyk: instrukcje EN (taniej w tokenach), odpowiedz PL ─────────────────

def test_wymog_polskiej_odpowiedzi_jest_jawny():
    """Instrukcje po angielsku sa tansze, ale teksty ida do UZYTKOWNIKA po polsku."""
    szk = _szkielet()
    assert "POLISH" in szk.upper()
    for pole in ("uzasadnienie", "ryzyko_ogolne", "ostrzezenia"):
        assert pole in szk


def test_klucze_json_nie_zostaly_przetlumaczone():
    """Parser i baza stoja na tych nazwach — tlumaczenie ich zerwaloby potok."""
    szk = _szkielet()
    for klucz in ("kurs_laczny", "szansa_wygranej_pct", "wygrana_netto", "pewnosc_pct"):
        assert klucz in szk
