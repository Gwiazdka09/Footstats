"""Backup musi nazywać się po tym, co REALNIE zrzuca, i mówić to w logu.

PO CO: produkcja przeniosła się z Neona na Supabase 20.07.2026, a workflow dalej
nazywał się „Run Neon backup" i pisał pliki `neon_<data>.sql.gz`. Skrypt bierze
conn string z Secret Managera, więc najpewniej zrzucał już Supabase — ale NIKT
tego nie widzi po nazwie ani po logu. W incydencie ktoś sięgnie po
`neon_latest.sql.gz` przekonany, że to kopia Neona, i przywróci nie tę bazę.

Log ma podawać SAM HOST, bez użytkownika i hasła — dowód tożsamości bazy nie może
być kolejnym miejscem, w którym wycieka conn string.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKRYPT = ROOT / "scripts" / "backup_db.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "backup.yml"


def test_nazwy_plikow_nie_udaja_neona() -> None:
    tresc = SKRYPT.read_text(encoding="utf-8")
    sciezki = re.findall(r"gs://[^\"']+", tresc)
    zle = [s for s in sciezki if "neon" in s.lower()]
    assert not zle, f"backup pisze pod nazwa Neona, a prod to Supabase: {zle}"


def test_prune_sprzata_zrzuty_ktore_dzis_powstaja() -> None:
    """Prune po starym wzorcu zostawia nowe pliki na zawsze — koszt rosnie cicho."""
    tresc = WORKFLOW.read_text(encoding="utf-8")
    assert "prod_" in tresc, "krok prune nie zna nowego prefiksu plikow"


def test_skrypt_loguje_host_bazy() -> None:
    """Bez tego nie da sie po fakcie stwierdzic, ktora baze zrzucil."""
    tresc = SKRYPT.read_text(encoding="utf-8")
    assert "DB_HOST" in tresc, "skrypt nie wyciaga hosta z conn stringa"
    assert "Backing up" in tresc and "$DB_HOST" in tresc, "host nie trafia do logu"


def test_wyciecie_hosta_nie_zostawia_fragmentu_hasla() -> None:
    """Hasło z niezakodowanym "@" — cięcie do PIERWSZEGO "@" zostawia jego ogon.

    Sprawdzamy sam wzorzec sed z pliku, żeby test nie wymagał basha na Windows.
    """
    tresc = SKRYPT.read_text(encoding="utf-8")
    assert "s#^.*@##" in tresc, "wzorzec tnie do pierwszego @ zamiast do ostatniego"

    # Ta sama semantyka co sed: zachłanne `.*@` = wszystko do ostatniego @.
    url = "postgresql://user:tajne@haslo@db.abc.supabase.co:5432/postgres"
    host = re.sub(r"[:/?].*$", "", re.sub(r"^.*@", "", url))
    assert host == "db.abc.supabase.co"
    assert "tajne" not in host and "haslo" not in host


def test_log_nie_zawiera_calego_conn_stringa() -> None:
    """`echo "$DB_URL"` wypchnalby haslo do publicznych logow GitHub Actions."""
    for linia in SKRYPT.read_text(encoding="utf-8").splitlines():
        goly = linia.strip()
        if goly.startswith("echo") or goly.startswith("printf"):
            assert "$DB_URL" not in goly, f"conn string w logu: {goly}"
