"""zapisz_fikstury_fotmob.py — jednorazowo pobiera prawdziwe odpowiedzi FotMoba
i zapisuje przyciete fikstury do tests/fixtures/fotmob/.

Uruchamiac RECZNIE, nie z pytesta: `python scripts/zapisz_fikstury_fotmob.py 20260830`.
Pytest nigdy nie dotyka sieci (.claude/rules/tests-no-prod.md), a fikstura ma byc
PRAWDZIWA — zmyslony ksztalt przechodzi na blednym kodzie.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_BASE = "https://www.fotmob.com/api/data"
_CEL = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "fotmob"


def _get(sciezka: str, **params) -> dict:
    r = requests.get(f"{_BASE}/{sciezka}", params=params,
                     headers={"User-Agent": _UA}, timeout=25)
    r.raise_for_status()
    return r.json()


def _przytnij_dzien(dane: dict, ile_lig: int = 2, ile_meczow: int = 3) -> dict:
    """Zostawia kilka lig i meczow — fikstura ma byc czytelna, nie kompletna."""
    ligi = []
    for liga in (dane.get("leagues") or [])[:ile_lig]:
        ligi.append({
            "ccode": liga.get("ccode"),
            "name": liga.get("name"),
            "id": liga.get("id"),
            "matches": [
                {"id": m.get("id"),
                 "home": {"name": (m.get("home") or {}).get("name")},
                 "away": {"name": (m.get("away") or {}).get("name")}}
                for m in (liga.get("matches") or [])[:ile_meczow]
            ],
        })
    return {"leagues": ligi}


def _przytnij_mecz(dane: dict) -> dict:
    """Zostawia wylacznie to, co czyta parser: lineup + infoBox.Referee."""
    tresc = dane.get("content") or {}
    return {
        "general": {k: (dane.get("general") or {}).get(k)
                    for k in ("matchId", "matchTimeUTCDate")},
        "content": {
            "lineup": tresc.get("lineup"),
            "matchFacts": {"infoBox": (tresc.get("matchFacts") or {}).get("infoBox")},
        },
    }


def _zapisz(nazwa: str, dane: dict) -> None:
    (_CEL / nazwa).write_text(
        json.dumps(dane, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    data = sys.argv[1] if len(sys.argv) > 1 else "20260830"
    _CEL.mkdir(parents=True, exist_ok=True)

    dzien = _get("matches", date=data)
    _zapisz("matches_day.json", _przytnij_dzien(dzien))
    print(f"zapisano matches_day.json ({len(dzien.get('leagues') or [])} lig w zrodle)")

    znalezione: dict[str, int] = {}
    for liga in dzien.get("leagues") or []:
        for mecz in liga.get("matches") or []:
            if len(znalezione) == 2:
                break
            mid = mecz.get("id")
            if not mid:
                continue
            szczegoly = _get("matchDetails", matchId=mid)
            typ = ((szczegoly.get("content") or {}).get("lineup") or {}).get("lineupType")
            if typ in ("predicted", "lastStarting11") and typ not in znalezione:
                znalezione[typ] = mid
                nazwa = ("match_predicted.json" if typ == "predicted"
                         else "match_last_xi.json")
                _zapisz(nazwa, _przytnij_mecz(szczegoly))
                print(f"zapisano {nazwa} (matchId={mid}, typ={typ})")

    if len(znalezione) < 2:
        print(f"UWAGA: znaleziono tylko {sorted(znalezione)} — powtorz dla innej daty")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
