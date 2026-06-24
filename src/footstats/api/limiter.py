"""Współdzielony rate-limiter (slowapi).

Wydzielony do osobnego modułu, by zarówno `api.main` (rejestracja middleware),
jak i routery (np. `api.auth` — twardszy limit na logowanie) mogły go importować
bez cyklu importów. `api.main` re-eksportuje `limiter` (testy/conftest go stamtąd biorą).
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Globalny limit 60/min per IP (siatka bezpieczeństwa); endpointy wrażliwe
# (logowanie/rejestracja) dokładają własny, twardszy limit dekoratorem.
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
