"""test_telegram_bot.py — bot Telegram: bramka chatu i wiązanie konta.

PO CO: bot przyjmuje komendy z internetu i jedna z nich (`/void`) ZMIENIA STAN
KUPONU. Chroni go pojedynczy warunek `chat_id != allowed`. Dwie rzeczy muszą
trzymać:

  * FAIL-CLOSED przy braku `TELEGRAM_CHAT_ID` — nieustawiona zmienna ma odrzucać
    WSZYSTKO, nie przepuszczać wszystkiego. Deploy gubiący env nie może otworzyć
    bota dla świata (a taki deploy już się zdarzył: 27.07 Cloud Run zgubił
    JWT_SECRET).
  * `/start` DZIAŁA PRZED bramką — świadomie, bo nowy użytkownik nie jest jeszcze
    autoryzowany. Dlatego cała weryfikacja własności czatu opiera się na nonce.

Nonce to druga połowa mechanizmu z `telegram_link_start`: konto dostaje kod,
a bot wiąże je z chat_id NADAWCY — nie z tym, co ktoś wpisał. Bez sprawdzenia
terminu ważności i bez zużycia kodu po jednym użyciu cały ten mechanizm byłby
pozorny.

ZASADA: żaden test nie może wysłać niczego do prawdziwego bota — `requests`
jest podmieniony globalnie w tym pliku.
"""
from __future__ import annotations

import json

import pytest

import footstats.telegram_bot as tb
import footstats.utils.db as dbmod

CHAT_DOZWOLONY = "111222333"
CHAT_OBCY = "999888777"


class _Kursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self, row=None):
        self.row = row
        self.zapytania: list[tuple] = []

    def execute(self, sql, params=()):
        self.zapytania.append((" ".join(sql.split()), params))
        return _Kursor(self.row)

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def zawierajace(self, fragment: str) -> list[tuple]:
        return [z for z in self.zapytania if fragment.upper() in z[0].upper()]


@pytest.fixture(autouse=True)
def bot(monkeypatch):
    """Odcina sieć i bazę; zwraca uchwyt do wysłanych odpowiedzi i zapytań."""
    stan = {"wyslane": [], "conn": _Conn()}

    def zakazana_siec(*a, **kw):
        raise AssertionError("test dotknął prawdziwego API Telegrama")

    monkeypatch.setattr(tb.requests, "post", zakazana_siec)
    monkeypatch.setattr(tb.requests, "get", zakazana_siec)
    monkeypatch.setattr(tb, "_reply", lambda chat_id, text: stan["wyslane"].append((str(chat_id), text)))
    monkeypatch.setattr(dbmod, "connect", lambda *a, **k: stan["conn"])
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT_DOZWOLONY)
    return stan


def _wiadomosc(tekst: str, chat_id: str = CHAT_DOZWOLONY) -> dict:
    return {"chat": {"id": chat_id}, "text": tekst}


# ── bramka chatu ────────────────────────────────────────────────────────────

def test_obcy_chat_nie_wykonuje_komend(bot):
    """`/void` zmienia stan kuponu — obcy chat nie może go dotknąć."""
    tb._handle(_wiadomosc("/void 7", chat_id=CHAT_OBCY))

    assert bot["wyslane"] == []
    assert bot["conn"].zawierajace("UPDATE coupons") == []


@pytest.mark.parametrize("komenda", ["/status", "/kupon", "/stats", "/void 1", "/help"])
def test_wszystkie_komendy_zablokowane_dla_obcego(bot, komenda):
    tb._handle(_wiadomosc(komenda, chat_id=CHAT_OBCY))

    assert bot["wyslane"] == []


def test_brak_zmiennej_odrzuca_wszystko(bot, monkeypatch):
    """FAIL-CLOSED: nieustawiony TELEGRAM_CHAT_ID nie może otworzyć bota."""
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")

    tb._handle(_wiadomosc("/void 7"))

    assert bot["wyslane"] == []
    assert bot["conn"].zawierajace("UPDATE coupons") == []


def test_dozwolony_chat_wykonuje_komende(bot):
    bot["conn"].row = None

    tb._handle(_wiadomosc("/kupon"))

    assert len(bot["wyslane"]) == 1


def test_tekst_bez_komendy_ignorowany(bot):
    tb._handle(_wiadomosc("dzien dobry"))

    assert bot["wyslane"] == []


def test_pusta_wiadomosc_nie_wywala(bot):
    tb._handle({"chat": {"id": CHAT_DOZWOLONY}})

    assert bot["wyslane"] == []


def test_sufiks_bota_obcinany(bot):
    """W grupach Telegram dokleja @nazwa_bota do komendy."""
    bot["conn"].row = None

    tb._handle(_wiadomosc("/kupon@FootStatsBot"))

    assert len(bot["wyslane"]) == 1


def test_wielkosc_liter_bez_znaczenia(bot):
    bot["conn"].row = None

    tb._handle(_wiadomosc("/KUPON"))

    assert len(bot["wyslane"]) == 1


def test_nieznana_komenda_nie_wywala(bot):
    tb._handle(_wiadomosc("/cosdziwnego"))

    assert bot["conn"].zapytania == []


# ── /start: wiązanie konta przez nonce ──────────────────────────────────────

def test_start_dziala_przed_bramka_chatu(bot):
    """Nowy user nie jest jeszcze autoryzowany — inaczej nie mógłby się związać."""
    tb._handle(_wiadomosc("/start abc123", chat_id=CHAT_OBCY))

    assert len(bot["wyslane"]) == 1
    assert bot["wyslane"][0][0] == CHAT_OBCY


def test_poprawny_nonce_wiaze_konto(bot):
    bot["conn"].row = {"id": 42, "username": "jakub"}

    odpowiedz = tb._cmd_start(CHAT_DOZWOLONY, "kod-poprawny")

    assert "jakub" in odpowiedz
    assert bot["conn"].zawierajace("UPDATE users")


def test_wiazany_jest_chat_id_nadawcy(bot):
    """SEDNO MECHANIZMU: zapisujemy chat_id NADAWCY, nie wartość podaną przez
    użytkownika — inaczej dałoby się podpiąć cudzy czat."""
    bot["conn"].row = {"id": 42, "username": "jakub"}

    tb._cmd_start("555444333", "kod-poprawny")

    params = bot["conn"].zawierajace("UPDATE users")[0][1]
    assert params[0] == "555444333"


def test_nonce_sprawdzany_z_terminem_waznosci(bot):
    """Bez warunku na `exp` kod działałby wiecznie."""
    bot["conn"].row = {"id": 42, "username": "jakub"}

    tb._cmd_start(CHAT_DOZWOLONY, "kod")

    sql = bot["conn"].zawierajace("SELECT")[0][0]
    assert "telegram_link_nonce_exp >" in sql


def test_nonce_zuzywany_po_uzyciu(bot):
    """Kod jednorazowy — powtórne użycie przejętego kodu ma być niemożliwe."""
    bot["conn"].row = {"id": 42, "username": "jakub"}

    tb._cmd_start(CHAT_DOZWOLONY, "kod")

    sql = bot["conn"].zawierajace("UPDATE users")[0][0]
    assert "telegram_link_nonce = NULL" in sql
    assert "telegram_link_nonce_exp = NULL" in sql


def test_zly_lub_wygasly_nonce_nic_nie_wiaze(bot):
    bot["conn"].row = None

    odpowiedz = tb._cmd_start(CHAT_DOZWOLONY, "kod-zly")

    assert "Nieprawidłowy lub wygasły" in odpowiedz
    assert bot["conn"].zawierajace("UPDATE users") == []


@pytest.mark.parametrize("pusty", ["", "   "])
def test_start_bez_kodu_daje_instrukcje(bot, pusty):
    odpowiedz = tb._cmd_start(CHAT_DOZWOLONY, pusty)

    assert "Użycie" in odpowiedz
    assert bot["conn"].zapytania == []


def test_awaria_bazy_nie_wywala_bota(bot, monkeypatch):
    """Wyjątek w handlerze zabiłby pętlę pollingu całego bota."""
    def wybucha(*a, **k):
        raise OSError("brak polaczenia")

    monkeypatch.setattr(dbmod, "connect", wybucha)

    assert "Błąd" in tb._cmd_start(CHAT_DOZWOLONY, "kod")


# ── /void: zmiana stanu kuponu ──────────────────────────────────────────────

def test_void_ustawia_status(bot):
    odpowiedz = tb._cmd_void("7")

    assert "#7" in odpowiedz
    sql, params = bot["conn"].zawierajace("UPDATE coupons")[0]
    assert "VOID" in sql
    assert params == (7,)


@pytest.mark.parametrize("zly", ["abc", "", "7; DROP TABLE coupons", "1.5"])
def test_void_odrzuca_nienumeryczne_id(bot, zly):
    """ID idzie do zapytania — musi być liczbą, nie dowolnym tekstem."""
    odpowiedz = tb._cmd_void(zly)

    assert "Użycie" in odpowiedz
    assert bot["conn"].zawierajace("UPDATE coupons") == []


def test_void_przycina_biale_znaki(bot):
    tb._cmd_void("  7  ")

    assert bot["conn"].zawierajace("UPDATE coupons")[0][1] == (7,)


# ── /kupon i /stats: odczyt ─────────────────────────────────────────────────

def test_kupon_gdy_brak_kuponow(bot):
    bot["conn"].row = None

    assert "Brak kuponów" in tb._cmd_kupon()


def test_kupon_pokazuje_nogi(bot):
    legs = [{"home": "Legia", "away": "Lech", "tip": "1", "odds": 1.85}]
    bot["conn"].row = {"id": 5, "status": "ACTIVE", "total_odds": 1.85,
                       "stake_pln": 10.0, "legs_json": json.dumps(legs),
                       "created_at": "2026-08-02 12:00:00"}

    odpowiedz = tb._cmd_kupon()

    assert "Kupon #5" in odpowiedz
    assert "Legia vs Lech" in odpowiedz


def test_kupon_bez_nog_nie_wywala(bot):
    bot["conn"].row = {"id": 5, "status": "ACTIVE", "total_odds": 1.0,
                       "stake_pln": 10.0, "legs_json": None,
                       "created_at": "2026-08-02"}

    assert "Kupon #5" in tb._cmd_kupon()


def test_stats_gdy_brak_rozliczonych(bot):
    bot["conn"].row = {"cnt": 0, "won": 0, "pnl": 0}

    assert "Brak danych" in tb._cmd_stats()


def test_stats_liczy_accuracy_i_roi(bot):
    """10 zakładów, 6 trafionych, +20 PLN przy stawce 10 flat → ROI +20%."""
    bot["conn"].row = {"cnt": 10, "won": 6, "pnl": 20.0}

    odpowiedz = tb._cmd_stats()

    assert "60.0%" in odpowiedz
    assert "+20.0%" in odpowiedz


def test_stats_bez_trafien_nie_dzieli_przez_zero(bot):
    bot["conn"].row = {"cnt": 5, "won": None, "pnl": None}

    assert "0.0%" in tb._cmd_stats()
