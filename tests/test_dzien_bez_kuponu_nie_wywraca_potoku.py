"""Dzień bez kuponu: `dane["kupon_x"]` bywa None, nie brakiem klucza.

`.get(klucz, {})` oddaje wtedy None, bo default dziala tylko przy BRAKU klucza —
i `None.get("zdarzenia")` wywala potok. Nie hipotetycznie:

* 2026-07-09 crash `final-9hkn2` w `_weryfikuj_kupony` — naprawiony `or {}`;
* 2026-09-21 crash `footstats-final-hxg5f` (DWIE proby, obie exit 1)
  w `_ocen_zdarzenia_decision_score`, czyli w NASTEPNEJ kopii tej samej linii.
  Tego dnia Groq nie dal ani jednego typu ("Zaden typ nie przezyl weryfikacji"),
  wiec `dane` mialo `kupon_a: None` i potok padl PO zapisaniu model_log,
  a PRZED rozliczeniami.

Poprawka z lipca trafila do jednego wejscia z czterech — wzorzec, ktory w tym
repo wracal juz kilka razy. Dlatego ostatni test WYLICZA wejscia ze zrodel
zamiast wierzyc, ze sa cztery.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

_PUSTY_DZIEN = {
    "kupon_a": None,
    "kupon_b": None,
    "kupon_c": None,
    "kupon_d": None,
    "top3": [],
    "ostrzezenia": "",
}


def test_decision_score_przezywa_dzien_bez_kuponu() -> None:
    """To dokladnie ta linia, ktora wywrocila prod 21.09."""
    from footstats.daily_agent_decision import _ocen_zdarzenia_decision_score

    _ocen_zdarzenia_decision_score(dict(_PUSTY_DZIEN), phase="final")


def test_wyswietl_przezywa_dzien_bez_kuponu() -> None:
    from footstats.daily_agent_output import _wyswietl

    _wyswietl(dict(_PUSTY_DZIEN), 10.0, 5.0)


def test_zapisz_txt_przezywa_dzien_bez_kuponu(tmp_path, monkeypatch) -> None:
    """LOGS_DIR podmieniony — test nie ma pisac do katalogu repo."""
    import footstats.daily_agent_output as wy

    monkeypatch.setattr(wy, "LOGS_DIR", tmp_path)
    sciezka = wy._zapisz_txt(dict(_PUSTY_DZIEN), 10.0, 5.0)

    assert sciezka.exists()


def test_telegram_przezywa_dzien_bez_kuponu(monkeypatch) -> None:
    """Zero ruchu do Telegrama: `_send` podmieniony, wysylka tylko zapisana."""
    import footstats.utils.telegram_notify as tn

    wyslane: list[str] = []
    monkeypatch.setattr(tn, "_already_sent_recently", lambda h: False)
    monkeypatch.setattr(tn, "_mark_sent", lambda h: None)
    monkeypatch.setattr(tn, "_send", lambda msg: wyslane.append(msg) or True)

    assert tn.send_kupon(dict(_PUSTY_DZIEN), 10.0, 5.0) is True
    assert len(wyslane) == 1


# Wzorzec kruchy: `.get(<cokolwiek kupon>, {})`. Bezpieczny: `.get(...) or {}`.
_KRUCHY = re.compile(r"\.get\(\s*(?:kupon_key|[\"']kupon_[abcd][\"'])\s*,\s*\{\}\s*\)")


def test_zadne_wejscie_nie_uzywa_domyslnego_slownika_w_get() -> None:
    """Straznik WYLICZA wejscia z kodu — lista w glowie rozjechala sie dwa razy."""
    winowajcy = []
    for plik in SRC.rglob("*.py"):
        for nr, linia in enumerate(plik.read_text(encoding="utf-8").splitlines(), 1):
            if _KRUCHY.search(linia):
                winowajcy.append(f"{plik.relative_to(ROOT)}:{nr}")

    assert not winowajcy, (
        "kupon bywa None, wiec default `.get(k, {})` NIE zadziala — uzyj"
        f" `(dane.get(k) or {{}})`. Kruche wejscia: {winowajcy}"
    )
