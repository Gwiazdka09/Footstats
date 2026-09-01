"""Alarm o cichej awarii nauczył się kłamać w drugą stronę.

PRODUKCJA 23.08 (`footstats-final-pptp4`): 32 kandydatów, 14 po filtrach, Groq
odpowiedział poprawnie, **5 predykcji wylądowało w bazie** — a alarm krzyknął
„ZERO predykcji zapisanych".

Mechanizm: `ma_typy` czytało `dane["top3"]` PO weryfikacji kursów (KROK 4), a zapis
do `predictions` dzieje się PRZED nią (KROK 3). Groq wytypował trzy rynki, których
źródło nie wycenia (`Over 1.5`, `Handicap +1 Gość`, `2 (wygrana gościa)`) —
weryfikacja słusznie wycięła komplet, `top3` zrobiło się puste i alarm uznał to
za dzień bez predykcji.

Alarm od cichych awarii, który wyje bez powodu, przestaje być czytany — a wtedy
przegapi się prawdziwą awarię. Dlatego pytamy teraz o to, co NAPRAWDĘ wylądowało
w bazie, a nie o to, co zostało w słowniku po przycinaniu.

Osobno: komplet typów wycięty przez weryfikację to NIE jest cisza — predykcje są —
ale też nie jest zdrowy dzień. To własny, inaczej nazwany sygnał.
"""
from __future__ import annotations

from footstats.ai.analyzer_helpers import _auto_zapisz_backtest
from footstats.daily_agent import wykryj_anomalie_runu as wykryj


# ── licznik zapisanych predykcji ────────────────────────────────────────────

def test_zapis_liczy_ile_wierszy_naprawde_poszlo(monkeypatch):
    """Bez tego licznika alarm nie ma jak odróżnić „nic nie zapisano" od
    „zapisano, tylko potem wycięto z kuponu"."""
    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "save_prediction", lambda **kw: (1, True))

    dane = {"top3": [{"mecz": "A vs B", "typ": "1", "kurs": 1.5},
                     {"mecz": "C vs D", "typ": "2", "kurs": 2.0}]}
    _auto_zapisz_backtest(dane, [{"gospodarz": "A", "goscie": "B"},
                                 {"gospodarz": "C", "goscie": "D"}])

    assert dane["_zapisanych"] == 2


def test_nieudany_zapis_nie_liczy_sie_jako_zapisany(monkeypatch):
    """Awaria bazy ma OBNIŻAĆ licznik, inaczej alarm znowu przespałby ciszę."""
    import footstats.core.backtest as bt

    def kaprysny(**kw):
        if kw["team_home"] == "A":
            raise RuntimeError("baza padla")
        return 1, True

    monkeypatch.setattr(bt, "save_prediction", kaprysny)

    dane = {"top3": [{"mecz": "A vs B", "typ": "1", "kurs": 1.5},
                     {"mecz": "C vs D", "typ": "2", "kurs": 2.0}]}
    _auto_zapisz_backtest(dane, [{"gospodarz": "A", "goscie": "B"},
                                 {"gospodarz": "C", "goscie": "D"}])

    assert dane["_zapisanych"] == 1


def test_brak_typow_do_zapisu_daje_zero(monkeypatch):
    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "save_prediction", lambda **kw: (1, True))

    dane: dict = {"top3": []}
    _auto_zapisz_backtest(dane, [])

    assert dane["_zapisanych"] == 0


# ── alarm nie może już kłamać ───────────────────────────────────────────────

def test_predykcje_zapisane_to_NIE_cicha_awaria():
    """Sedno: dokładny przypadek z 23.08 — 5 wierszy w bazie, `top3` puste po
    weryfikacji. Wcześniej leciał alarm „ZERO predykcji zapisanych"."""
    assert wykryj(32, 14, 0, ma_typy=True, typy_po_weryfikacji=False) is not None
    komunikat = wykryj(32, 14, 0, ma_typy=True, typy_po_weryfikacji=False)

    assert "ZERO predykcji" not in komunikat, "predykcje SA zapisane — to klamstwo"
    assert "weryfikac" in komunikat.lower()


def test_komplet_wyciety_przez_weryfikacje_ma_wlasny_komunikat():
    """Dzień, w którym wszystkie typy poszły na rynki bez kursu, jest wart
    zgłoszenia — ale jako co innego niż brak predykcji."""
    komunikat = wykryj(32, 14, 0, ma_typy=True, typy_po_weryfikacji=False) or ""

    assert "użytecz" in komunikat.lower() or "wycie" in komunikat.lower()


def test_zdrowy_run_dalej_milczy():
    assert wykryj(42, 7, 0, ma_typy=True, typy_po_weryfikacji=True) is None


def test_prawdziwa_cisza_dalej_alarmuje():
    """Regresja: naprawa fałszywego alarmu nie może uciszyć prawdziwego."""
    komunikat = wykryj(42, 7, 0, ma_typy=False, typy_po_weryfikacji=False) or ""

    assert "ZERO predykcji" in komunikat


def test_brak_informacji_o_weryfikacji_zachowuje_stare_zachowanie():
    """Wołający, który nie przekazuje nowego argumentu, nie może dostać alarmu
    znikąd — parametr jest opcjonalny."""
    assert wykryj(42, 7, 0, ma_typy=True) is None


def test_zero_kandydatow_dalej_wazniejsze():
    assert "kandydat" in (wykryj(0, 0, 0, ma_typy=False,
                                 typy_po_weryfikacji=False) or "").lower()
