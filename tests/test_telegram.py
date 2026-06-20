"""
test_telegram.py – Testy integracji modułu telegram_notify.

Wersja: v3.2
Sprawdza dostępność Telegramu i wysyłanie testowych wiadomości.

SETUP:
  1. Dodaj do .env:
       TELEGRAM_BOT_TOKEN=<twój_token_od_BotFather>
       TELEGRAM_CHAT_ID=<twoje_chat_id>
  2. Uruchom test: pytest tests/test_telegram.py -v -s
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from dotenv import load_dotenv

# Import modułu Telegramu
from footstats.utils.telegram_notify import (
    telegram_dostepny,
    send_message,
    send_kupon,
    send_wynik_update,
    send_draft_kupon,
    check_and_alert_source_down,
)

load_dotenv()


class TestTelegramAvailability:
    """Weryfikacja dostępu do Telegramu."""

    def test_telegram_credentials_exist(self):
        """Sprawdza czy TELEGRAM_BOT_TOKEN i TELEGRAM_CHAT_ID są w .env."""
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        if not token or not chat_id:
            pytest.skip("Telegram credentials not configured in .env")

        assert token, "TELEGRAM_BOT_TOKEN must be set"
        assert chat_id, "TELEGRAM_CHAT_ID must be set"

    def test_telegram_dostepny_returns_true(self):
        """Zwraca True jeśli kredencjały są dostępne."""
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            pytest.skip("Telegram not configured")

        result = telegram_dostepny()
        assert result is True, "telegram_dostepny() should return True when credentials exist"


class TestTelegramMessaging:
    """Testy wysyłania wiadomości."""

    @pytest.mark.unit
    def test_send_simple_message(self):
        """send_message() zwraca True — _send zamockowany (BEZ realnej wysyłki)."""
        with patch("footstats.utils.telegram_notify._send", return_value=True):
            result = send_message("test")
        assert result is True, "send_message() should return True on success"

    @pytest.mark.integration
    def test_send_kupon_test_data(self):
        """send_kupon() zwraca True gdy requests.post odpowiada ok=True."""
        mock_resp = MagicMock()
        mock_resp.ok = True

        test_kupon = {
            "kupon_a": {
                "zdarzenia": [
                    {
                        "nr": 1,
                        "mecz": "Arsenal - Chelsea",
                        "typ": "Over 2.5",
                        "kurs": 1.85,
                        "_verified": True,
                    },
                    {
                        "nr": 2,
                        "mecz": "Liverpool - Man City",
                        "typ": "Over 2.5",
                        "kurs": 1.75,
                        "_verified": True,
                    },
                ],
                "kurs_laczny": 3.24,
                "szansa_wygranej_pct": 78,
            },
            "kupon_b": {
                "zdarzenia": [
                    {
                        "nr": 1,
                        "mecz": "Arsenal - Chelsea",
                        "typ": "Over 1.5",
                        "kurs": 1.45,
                        "_verified": True,
                    },
                ],
                "kurs_laczny": 1.45,
                "szansa_wygranej_pct": 85,
            },
            "top3": [
                {"mecz": "Man United - Tottenham", "typ": "Over 2.5", "kurs": 1.80, "ev_netto": 12.5},
                {"mecz": "Brighton - Aston Villa", "typ": "1", "kurs": 2.10, "ev_netto": 8.3},
                {"mecz": "West Ham - Newcastle", "typ": "2", "kurs": 1.95, "ev_netto": 5.2},
            ],
            "ostrzezenia": "Test message — ignore this",
        }

        with patch(
            "footstats.utils.telegram_notify._send", return_value=True
        ), patch(
            "footstats.utils.telegram_notify._already_sent_recently", return_value=False
        ):
            result = send_kupon(test_kupon, stawka_a=10.0, stawka_b=5.0)
        assert result is True, "send_kupon() should return True on success"

    @pytest.mark.unit
    def test_send_wynik_update_test(self):
        """send_wynik_update() zwraca True — _send zamockowany (BEZ realnej wysyłki)."""
        with patch("footstats.utils.telegram_notify._send", return_value=True):
            result = send_wynik_update(
                match_id=1,
                mecz="Test A - Test B",
                ai_tip="Over 2.5",
                actual_result="3:2",
                tip_correct=1,
            )
        assert result is True, "send_wynik_update() should return True on success"

    @pytest.mark.unit
    def test_send_draft_kupon_test(self):
        """send_draft_kupon() zwraca True — _send zamockowany (BEZ realnej wysyłki)."""
        test_legs = [
            {"mecz": "Test A - Test B", "typ": "Over 2.5", "kurs": 1.85, "decision_score": 0.87},
        ]
        with patch("footstats.utils.telegram_notify._send", return_value=True):
            result = send_draft_kupon(coupon_id=999, legs=test_legs, total_odds=1.85)
        assert result is True, "send_draft_kupon() should return True on success"


class TestTelegramWithoutCredentials:
    """Testy działania bez skonfigurowanych kredencjałów."""

    @pytest.mark.unit
    def test_telegram_dostepny_returns_false_without_token(self, monkeypatch):
        """Zwraca False jeśli brak tokenu."""
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        result = telegram_dostepny()
        assert result is False, "telegram_dostepny() should return False without credentials"

    @pytest.mark.unit
    def test_send_message_returns_false_without_token(self, monkeypatch):
        """Zwraca False przy wysłaniu bez kredencjałów."""
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        result = send_message("test")
        assert result is False, "send_message() should return False without credentials"


class TestPerUserTelegram:
    """FAZA 15.6 — powiadomienia per-user (telegram_chat_id z DB)."""

    @pytest.mark.unit
    def test_send_uzywa_jawnego_chat_id(self, monkeypatch):
        """_send z chat_id override wysyła do podanego czatu, nie globalnego."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "GLOBAL")
        from footstats.utils import telegram_notify as tn
        captured = {}

        class _Resp:
            ok = True

        def _fake_post(url, json, timeout):
            captured["chat_id"] = json["chat_id"]
            return _Resp()

        monkeypatch.setattr(tn.requests, "post", _fake_post)
        assert tn._send("hej", chat_id="USER123") is True
        assert captured["chat_id"] == "USER123"

    @pytest.mark.unit
    def test_send_fallback_na_globalny(self, monkeypatch):
        """Bez chat_id override → globalny env."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "GLOBAL")
        from footstats.utils import telegram_notify as tn
        captured = {}

        class _Resp:
            ok = True

        monkeypatch.setattr(tn.requests, "post",
                            lambda url, json, timeout: captured.update(chat_id=json["chat_id"]) or _Resp())
        tn._send("hej")
        assert captured["chat_id"] == "GLOBAL"

    @pytest.mark.unit
    def test_send_to_user_brak_chat_id_false(self, monkeypatch):
        """User bez telegram_chat_id → False (nie wysyła)."""
        from footstats.utils import telegram_notify as tn

        class _Conn:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def execute(self, *a): return self
            def fetchone(self): return {"telegram_chat_id": None}

        monkeypatch.setattr(tn, "_send", lambda *a, **k: True)  # gdyby wysłał = błąd
        import footstats.utils.db as dbmod
        monkeypatch.setattr(dbmod, "connect", lambda: _Conn())
        assert tn.send_message_to_user(99, "hej") is False


class TestSourceHealthCheck:
    """Health-check zrodel danych — alert gdy scraper zwraca 0 wydarzen/niedostepny (dlug techniczny #2)."""

    @pytest.mark.unit
    def test_alert_wysylany_gdy_zero_wynikow(self, monkeypatch):
        """0 wydarzen → woła send_alert (mock), zwraca True."""
        from footstats.utils import telegram_notify as tn
        mock_alert = MagicMock(return_value=True)
        monkeypatch.setattr(tn, "send_alert", mock_alert)

        result = tn.check_and_alert_source_down("Bzzoiro", ok=True, n_wyniki=0)

        assert result is True
        mock_alert.assert_called_once()

    @pytest.mark.unit
    def test_alert_wysylany_gdy_niedostepny(self, monkeypatch):
        """ok=False (walidacja klienta nie przeszla) → woła send_alert, niezaleznie od n_wyniki."""
        from footstats.utils import telegram_notify as tn
        mock_alert = MagicMock(return_value=True)
        monkeypatch.setattr(tn, "send_alert", mock_alert)

        result = tn.check_and_alert_source_down("Bzzoiro", ok=False, n_wyniki=5)

        assert result is True
        mock_alert.assert_called_once()

    @pytest.mark.unit
    def test_brak_alertu_gdy_dane_normalne(self, monkeypatch):
        """ok=True i n_wyniki>0 → NIE woła send_alert."""
        from footstats.utils import telegram_notify as tn
        mock_alert = MagicMock(return_value=True)
        monkeypatch.setattr(tn, "send_alert", mock_alert)

        result = tn.check_and_alert_source_down("Bzzoiro", ok=True, n_wyniki=12)

        assert result is False
        mock_alert.assert_not_called()
