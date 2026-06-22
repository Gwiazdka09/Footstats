"""Testy utils/mailer.py — Resend email transakcyjny (mock requests, BEZ realnej wysyłki)."""
from unittest.mock import patch, MagicMock
import footstats.utils.mailer as mailer


def _resp(ok=True, status=200, text=""):
    m = MagicMock()
    m.ok = ok
    m.status_code = status
    m.text = text
    return m


def test_send_email_brak_klucza_zwraca_false():
    with patch.object(mailer, "_api_key", return_value=""):
        assert mailer.send_email("a@b.pl", "S", "<p>x</p>") is False


def test_send_email_sukces():
    with patch.object(mailer, "_api_key", return_value="re_test"), \
         patch("footstats.utils.mailer.requests.post", return_value=_resp(ok=True)) as post:
        assert mailer.send_email("a@b.pl", "S", "<p>x</p>") is True
        # poprawny payload Resend
        _, kw = post.call_args
        assert kw["json"]["to"] == ["a@b.pl"]
        assert kw["headers"]["Authorization"] == "Bearer re_test"


def test_send_email_http_blad_zwraca_false():
    with patch.object(mailer, "_api_key", return_value="re_test"), \
         patch("footstats.utils.mailer.requests.post", return_value=_resp(ok=False, status=422, text="bad")):
        assert mailer.send_email("a@b.pl", "S", "<p>x</p>") is False


def test_welcome_email_escapuje_username():
    captured = {}
    with patch.object(mailer, "send_email",
                      side_effect=lambda to, subj, body, **k: captured.update(body=body, to=to) or True):
        assert mailer.send_welcome_email("u@b.pl", "Zły<User>&Co") is True
    assert "Zły&lt;User&gt;&amp;Co" in captured["body"]  # zaescapowane
    assert "<User>" not in captured["body"]


def test_klucz_czyta_lowercase(monkeypatch):
    # Prod (Linux/Cloud Run) jest case-sensitive, a .env ma 'resend_api_key' (lowercase).
    # Dual-read RESEND_API_KEY/resend_api_key musi go znaleźć. (Na Windows env case-insensitive.)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("resend_api_key", "re_lower")
    assert mailer._api_key() == "re_lower"
