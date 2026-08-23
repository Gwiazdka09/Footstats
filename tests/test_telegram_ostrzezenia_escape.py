"""Dzienna wiadomość przepadała, gdy ostrzeżenie zawierało znak `<`.

PRODUKCJA 23.08 (`footstats-final-pptp4`), przebieg planowy 11:00:

    Telegram _send: HTTP 400 — can't parse entities:
    Unsupported start tag "1.20)." at byte offset 493

Nazwy drużyn i typy przechodzą przez `_esc` — pole `ostrzezenia` jako jedyne szło
do wiadomości surowe. Tekst zawierał `<1.20).`, Telegram w trybie HTML uznał `<`
za początek tagu i odrzucił CAŁĄ wiadomość. To ta sama awaria, którą `_esc`
opisuje w swoim docstringu dla nazw drużyn (06-22) — jedno pole zostało pominięte.

Treść ostrzeżeń pochodzi od modelu językowego i z listy wyciętych halucynacji,
czyli z miejsc, gdzie nawiasy i znaki nierówności są normalne. Escapowanie tego
pola nie jest kosmetyką, tylko warunkiem dostarczenia wiadomości.

Druga warstwa: nawet gdy któreś pole znowu zostanie pominięte, wiadomość ma
DOJŚĆ. Po odmowie parsera ponawiamy raz bez formatowania — brzydsza wiadomość
jest lepsza niż cisza.
"""
from __future__ import annotations

import footstats.utils.telegram_notify as tg


class _Odp:
    def __init__(self, ok: bool, status: int = 200, text: str = ""):
        self.ok, self.status_code, self.text = ok, status, text


def _przechwyc(monkeypatch, odpowiedzi):
    """Podstawia HTTP; zwraca listę wysłanych payloadów."""
    wyslane: list[dict] = []
    kolejka = list(odpowiedzi)

    def fake_post(url, json=None, timeout=None):
        wyslane.append(json)
        return kolejka.pop(0) if kolejka else _Odp(True)

    monkeypatch.setattr(tg.requests, "post", fake_post)
    monkeypatch.setattr(tg, "_get_credentials", lambda: ("token", "123"))
    return wyslane


# ── escapowanie ostrzeżeń ───────────────────────────────────────────────────

def test_ostrzezenie_ze_znakiem_mniejszosci_jest_escapowane(monkeypatch):
    """Sedno: `<1.20` musi wyjść jako encja, inaczej Telegram odrzuca wiadomość."""
    wyslane = _przechwyc(monkeypatch, [_Odp(True)])
    monkeypatch.setattr(tg, "_already_sent_recently", lambda h: False)
    monkeypatch.setattr(tg, "_zapisz_wyslany", lambda h: None, raising=False)

    tg.send_kupon({"top3": [], "ostrzezenia": "Kurs <1.20). Uwaga & ryzyko"})

    tekst = wyslane[0]["text"]
    assert "<1.20" not in tekst
    assert "&lt;1.20" in tekst
    assert "&amp;" in tekst


def test_tresc_ostrzezenia_nie_ginie(monkeypatch):
    """Escapowanie nie może zjeść treści — ostrzeżenie ma dalej być czytelne."""
    wyslane = _przechwyc(monkeypatch, [_Odp(True)])
    monkeypatch.setattr(tg, "_already_sent_recently", lambda h: False)
    monkeypatch.setattr(tg, "_zapisz_wyslany", lambda h: None, raising=False)

    tg.send_kupon({"top3": [], "ostrzezenia": "Kurs <1.20). Uwaga"})

    assert "Uwaga" in wyslane[0]["text"]


# ── druga warstwa: wiadomość ma dojść mimo wszystko ─────────────────────────

def test_po_odmowie_parsera_ponawiamy_bez_formatowania(monkeypatch):
    """Gdy któreś pole znowu zostanie pominięte, cisza jest gorsza niż brzydka
    wiadomość. Jedno ponowienie, bez `parse_mode`."""
    wyslane = _przechwyc(monkeypatch, [
        _Odp(False, 400, '{"description":"Bad Request: can\'t parse entities"}'),
        _Odp(True),
    ])

    assert tg._send("<b>cos</b> <zle") is True
    assert len(wyslane) == 2
    assert "parse_mode" not in wyslane[1] or wyslane[1]["parse_mode"] is None


def test_ponowienie_tylko_przy_bledzie_parsera(monkeypatch):
    """Blokada bota albo zły chat_id nie naprawi się ponowieniem — nie zaśmiecamy
    API kolejnym żądaniem."""
    wyslane = _przechwyc(monkeypatch, [
        _Odp(False, 403, '{"description":"Forbidden: bot was blocked by the user"}'),
    ])

    assert tg._send("cos") is False
    assert len(wyslane) == 1


def test_udana_wysylka_nie_ponawia(monkeypatch):
    wyslane = _przechwyc(monkeypatch, [_Odp(True)])

    assert tg._send("cos") is True
    assert len(wyslane) == 1
