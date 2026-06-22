"""utils/mailer.py — email transakcyjny przez Resend (HTTP API, bez zależności SDK).

Klucz: env RESEND_API_KEY (lub resend_api_key). Nadawca: RESEND_FROM lub domyślny test-sender
Resend (onboarding@resend.dev — podmień na własną zweryfikowaną domenę przed prod-launchem).
Graceful: brak klucza / błąd HTTP → log WARNING + False, NIGDY nie blokuje flow (rejestracja itp.).

LIMIT Resend Free: 100 emaili/DZIEŃ, 3000/mc, 1 domena. Welcome = 1/rejestrację (bezpieczne).
Przy skalowaniu (>100 rejestracji/dzień lub batch/marketing) — pilnuj limitu / upgrade planu.
"""
from __future__ import annotations

import html
import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

RESEND_API = "https://api.resend.com/emails"
_DEFAULT_FROM = "onboarding@resend.dev"
_DISCLAIMER = ("<p style='color:#94a3b8;font-size:12px'>FootStats nie jest bukmacherem, "
               "nie przyjmuje zakładów. Prognozy nie gwarantują wyników. Hazard 18+.</p>")


def _api_key() -> str:
    return (os.getenv("RESEND_API_KEY") or os.getenv("resend_api_key") or "").strip()


def send_email(to: str, subject: str, html_body: str, from_addr: str | None = None) -> bool:
    """Wysyła email przez Resend. True gdy sukces. Graceful przy braku klucza/błędzie."""
    key = _api_key()
    if not key:
        log.warning("Resend: brak RESEND_API_KEY — pomijam email do %s", to)
        return False
    sender = (from_addr or os.getenv("RESEND_FROM") or _DEFAULT_FROM).strip()
    try:
        r = requests.post(
            RESEND_API,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"from": sender, "to": [to], "subject": subject, "html": html_body},
            timeout=15,
        )
        if not r.ok:
            log.warning("Resend: HTTP %s — %s", r.status_code, (r.text or "")[:250])
        return r.ok
    except requests.RequestException as e:
        log.warning("Resend: błąd sieci: %s", e)
        return False


def send_welcome_email(to: str, username: str) -> bool:
    """Email powitalny po rejestracji (potwierdzenie założenia konta)."""
    u = html.escape(str(username), quote=False)
    body = (
        f"<h2>Witaj w FootStats, {u}!</h2>"
        "<p>Twoje konto zostało utworzone. Możesz już budować kupony w kreatorze.</p>"
        f"{_DISCLAIMER}"
    )
    return send_email(to, "FootStats — potwierdzenie rejestracji", body)


def send_password_reset_email(to: str, reset_link: str) -> bool:
    """Email z linkiem resetu hasła (gdy wpięty flow reset-tokenów)."""
    link = html.escape(str(reset_link), quote=True)
    body = (
        "<h2>Reset hasła FootStats</h2>"
        f"<p>Kliknij, aby ustawić nowe hasło: <a href='{link}'>{link}</a></p>"
        "<p style='color:#94a3b8;font-size:12px'>Link wygasa po 1h. Jeśli to nie Ty — zignoruj.</p>"
        f"{_DISCLAIMER}"
    )
    return send_email(to, "FootStats — reset hasła", body)
