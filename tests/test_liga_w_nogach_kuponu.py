"""Noga kuponu musi niesc lige — bez niej nie da sie zmierzyc, ktore ligi placa.

ZMIERZONE 01.09: proba policzenia ROI per liga na 243 rozliczonych kuponach
`phase='system'` skonczyla sie tak:

    rozliczonych: 243 | z rozpoznana liga: 25 | bez ligi: 218

Lige dalo sie odtworzyc tylko przez dopasowanie do `predictions` po nazwach
druzyn i dacie — a `predictions` zapisuje wylacznie typy, ktore przeszly przez
LLM-a, wiec 218 kuponow paper-tradingu nie ma tam odpowiednika. Na n=6
(`Chinese Super League`, ROI -31.2% ± 30.9pp) nie da sie orzec niczego.

To NIE jest nowe odkrycie — `core/user_stats.py` opisuje ten sam brak i z jego
powodu POMIJA grupowanie `per_league`:

    schemat legow kuponu jest NIESPOJNY miedzy zrodlami kuponow —
    risk_proposals.py/system_coupons.py dopisuja klucz "liga" do legow, ale
    daily_io.py/system_paper.py go nie maja (...) dlatego POMINIETE w tej wersji

`system_paper` to jedyne zrodlo kuponow, ktore realnie chodzi na produkcji
(326 wierszy `SINGLE`), wiec bez tej naprawy pytanie "ktore ligi sie oplacaja"
zostaje bez odpowiedzi na zawsze — a od niego zalezy decyzja o zawezeniu selekcji.
"""
from __future__ import annotations

import pytest

from footstats.core.system_paper import build_single_leg_coupons


@pytest.fixture
def przechwyc(monkeypatch):
    """Podglada nogi idace do `save_coupon`. Zero dotkniec bazy.

    `build_single_leg_coupons` importuje LOKALNIE (wewnatrz funkcji), wiec
    patchowanie atrybutow `system_paper` nic nie daje — trzeba podmienic
    nazwy w modulach ZRODLOWYCH, bo to stamtad import zaciaga je za kazdym
    wywolaniem.
    """
    zapisane: list[dict] = []
    import footstats.core.coupon_tracker as ct
    import footstats.core.system_paper as sp
    import footstats.utils.db as db

    class _Conn:
        def execute(self, *a, **k):
            class _C:
                def fetchone(self_inner):
                    return None
            return _C()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(db, "connect", lambda *a, **k: _Conn())
    monkeypatch.setattr(sp, "_resolve_system_user_id", lambda: 2, raising=False)

    def _save(**kw):
        zapisane.append(kw)
        return 1

    monkeypatch.setattr(ct, "save_coupon", _save)
    monkeypatch.setattr(ct, "update_coupon_status", lambda *a, **k: None)
    monkeypatch.setattr(ct, "init_coupon_tables", lambda: None)
    return zapisane


def _mecz(liga="Premier League"):
    return {
        "gospodarz": "Arsenal", "goscie": "Chelsea", "data": "2026-09-01",
        "liga": liga, "pw": 55.0, "pr": 25.0, "pp": 20.0, "bt": 52.0, "o25": 58.0,
        "odds": {"home": 1.85, "draw": 3.4, "away": 4.2,
                 "over_2_5": 1.75, "under_2_5": 2.05, "btts": 1.8},
    }


def test_noga_niesie_lige(przechwyc):
    build_single_leg_coupons([_mecz()])

    assert przechwyc, "nie powstal zaden kupon — atrapa zle ustawiona"
    noga = przechwyc[0]["legs"][0]
    assert noga.get("liga") == "Premier League", (
        f"noga bez ligi: {noga} — grupowanie per_league zostanie niemozliwe"
    )


def test_brak_ligi_w_zrodle_nie_wywala_kuponu(przechwyc):
    """Kontrola negatywna: liga to wzbogacenie, nie warunek powstania kuponu."""
    build_single_leg_coupons([_mecz(liga="")])

    assert przechwyc, "brak ligi zablokowal utworzenie kuponu"
    assert przechwyc[0]["legs"][0].get("liga", "") == ""


@pytest.mark.parametrize("klucz", ["home", "away", "tip", "odds", "mecz", "decision_score"])
def test_pozostale_pola_nogi_nietkniete(przechwyc, klucz):
    """Kontrola: dokladamy klucz, nie przebudowujemy schematu nogi."""
    build_single_leg_coupons([_mecz()])

    assert klucz in przechwyc[0]["legs"][0]


# ── druga sciezka: kupon LLM (`daily_io`) ───────────────────────────────────
#
# `user_stats` wymienial DWA zrodla bez ligi: `system_paper` i `daily_io`.
# Naprawa jednego zostawia schemat dalej niespojnym, a to wlasnie niespojnosc
# byla powodem pominiecia `per_league` — nie sam brak pola w jednym miejscu.

def _kandydat(liga="Bundesliga"):
    return {"mecz": "Bayern vs Dortmund", "typ": "Over 2.5", "kurs": 1.7,
            "decision_score": 65, "liga": liga, "data": "2026-09-01"}


def test_kupon_LLM_tez_niesie_lige(monkeypatch):
    zapisane: list[dict] = []
    import footstats.core.coupon_tracker as ct
    from footstats.core.daily_io import _zapisz_kupon_do_db

    import footstats.utils.db as db

    class _Conn:
        def execute(self, *a, **k):
            class _C:
                def fetchone(self_inner):
                    return None
                def fetchall(self_inner):
                    return []
            return _C()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(db, "connect", lambda *a, **k: _Conn())
    monkeypatch.setattr(ct, "save_coupon", lambda **kw: zapisane.append(kw) or 1)
    monkeypatch.setattr(ct, "init_coupon_tables", lambda: None)
    monkeypatch.setattr(ct, "get_draft_today", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(ct, "promote_to_active", lambda *a, **k: None, raising=False)
    # `_zapisz_kupon_do_db` po zapisie wola `process_bet`, ktory idzie do bazy
    # (bankroll). Dla tego testu to nieistotny efekt uboczny — ale BEZ tej atrapy
    # test przechodzil w izolacji i padal w pelnym zestawie, czyli byl zielony
    # z powodu kolejnosci, nie z powodu kodu.
    # Import jest LOKALNY (`daily_io.py:32`), wiec patchujemy modul ZRODLOWY —
    # podmiana na `daily_io` nie doszlaby do wywolania.
    import footstats.core.bankroll as br
    monkeypatch.setattr(br, "process_bet", lambda *a, **k: None)

    _zapisz_kupon_do_db([_kandydat()], phase="draft", groq_resp=None,
                        stake=10.0, total_odds=1.7)

    assert zapisane, "kupon nie powstal — atrapa zle ustawiona"
    assert zapisane[0]["legs"][0].get("liga") == "Bundesliga"
