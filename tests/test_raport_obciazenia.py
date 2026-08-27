"""ZADANIE: mocny test obciążenia na całej próbie + naprawa tabeli kubełkowej.

PO CO: 26.08 dwa razy odczytano gołą kolumnę `roznica` w `raport_kalibracji_1x2`
(np. +6.5pp przy n=113) jako "model jest źle wyskalowany". To 1.4 błędu
standardowego — czysty szum, jedyna bramka (`PROG_MALA_PROBA = 30`) przez niego
przechodzi. Test na całej próbie naraz (`sprawdz_obciazenie`) ma dużo większą
moc i pokazuje, że model NIE jest obciążony na żadnym wyjściu (|z| < 1.3).

Ten plik sprawdza:
1. `raport_obciazenia_modelu` — nowy raport, model bez obciążenia.
2. `raport_obciazenia_modelu` — model jawnie zaniżający jedno wyjście (remis).
3. ANTYREGRESJA (sedno zadania) — koszyk w `raport_kalibracji_1x2` z dużą
   różnicą w pp, ale małym n z punktu widzenia mocy statystycznej, NIE jest
   oznaczony jako rozbieżność, bo mieści się w przedziale Wilsona.
4. Oba raporty na pustym `model_log` piszą "BRAK DANYCH" i nie wywalają wyjątku.
5. Wiersz z nierozliczalnym `actual_result` (dogrywka) jest pomijany.
"""
from __future__ import annotations

from scripts import stan_uczenia


# ── atrapy połączenia — ten sam ksztalt co w test_testy_przewagi.py/test_remisy_mierzone.py ──

class _Kursor:
    def __init__(self, wiersze: list[dict]):
        self._w = wiersze

    def fetchall(self) -> list[dict]:
        return self._w


class _ConnObciazenia:
    """Atrapa zwracająca zawsze te same wiersze — `raport_obciazenia_modelu`
    wykonuje dokładnie jedno zapytanie SELECT."""

    def __init__(self, wiersze: list[dict]):
        self.wiersze = wiersze
        self.zapytania: list[str] = []

    def execute(self, zapytanie: str, params=None) -> _Kursor:
        self.zapytania.append(zapytanie)
        return _Kursor(self.wiersze)


class _ConnKalibracji:
    """Ten sam ksztalt co `_ConnKalibracji` w `test_testy_przewagi.py` —
    `raport_kalibracji_1x2` czyta wiersze `{"pewnosc": ..., "tip_correct": ...}`."""

    def __init__(self, wiersze: list[dict]):
        self.wiersze = wiersze
        self.zapytania: list[str] = []

    def execute(self, zapytanie: str, params=None) -> _Kursor:
        self.zapytania.append(zapytanie)
        return _Kursor(self.wiersze)


def _linia(tekst: str, etykieta: str) -> str:
    return next(w for w in tekst.splitlines() if w.strip().startswith(etykieta))


def _wiersz(actual_result: str) -> dict:
    """Wiersz `model_log` ze STAŁYMI deklarowanymi prawdopodobieństwami
    (40/30/30/50/50 w procentach) — jedyne, co się zmienia, to wynik."""
    return {
        "prob_home": 40.0,
        "prob_draw": 30.0,
        "prob_away": 30.0,
        "prob_over25": 50.0,
        "prob_btts": 50.0,
        "actual_result": actual_result,
    }


# ── 1. Model bez obciążenia — żadne wyjście nie ISTOTNE ─────────────────────

def test_raport_obciazenia_brak_obciazenia_na_zadnym_wyjsciu(capsys):
    """Skonstruowane tak, że deklarowane = zaszłe DOKŁADNIE dla każdego z 5
    wyjść i dla argmaksu 1X2 (n=200):
      - "2-1" x60 (dom wygrywa, over 2.5, BTTS)      -> home=80, over=100, btts=100
      - "2-0" x20 (dom wygrywa, under, bez BTTS)
      - "0-0" x60 (remis, under, bez BTTS)            -> draw=60
      - "1-2" x40 (wyjazd wygrywa, over, BTTS)        -> away=60
      - "0-2" x20 (wyjazd wygrywa, under, bez BTTS)
    P(dom)=80/200=0.40, P(remis)=60/200=0.30, P(wyjazd)=60/200=0.30,
    P(over)=100/200=0.50, P(BTTS)=100/200=0.50 — dokładnie deklarowane wartości.
    """
    wiersze = (
        [_wiersz("2-1")] * 60
        + [_wiersz("2-0")] * 20
        + [_wiersz("0-0")] * 60
        + [_wiersz("1-2")] * 40
        + [_wiersz("0-2")] * 20
    )
    conn = _ConnObciazenia(wiersze)

    stan_uczenia.raport_obciazenia_modelu(conn)

    out = capsys.readouterr().out
    assert "ISTOTNE" not in out, out
    assert "nie wykazuje systematycznego obciazenia" in out.lower(), out


# ── 2. Model jawnie zaniżający remis ─────────────────────────────────────────

def test_raport_obciazenia_wykrywa_zanizony_remis(capsys):
    """Model deklaruje 20% remisu, a remis zachodzi w 45% (135/300) —
    to wyjście ma zostać oznaczone ISTOTNE, kierunek "model zaniża"
    (roznica dodatnia: realnie > deklarowane)."""
    wiersze = (
        [{"prob_home": None, "prob_draw": 20.0, "prob_away": None,
          "prob_over25": None, "prob_btts": None, "actual_result": "1-1"}] * 135
        + [{"prob_home": None, "prob_draw": 20.0, "prob_away": None,
            "prob_over25": None, "prob_btts": None, "actual_result": "2-1"}] * 165
    )
    conn = _ConnObciazenia(wiersze)

    stan_uczenia.raport_obciazenia_modelu(conn)

    out = capsys.readouterr().out
    linia_x = _linia(out, "X (prob_draw)")
    assert "ISTOTNE" in linia_x, linia_x
    assert "n= 300" in linia_x, linia_x
    assert "model zanizza" in out.lower(), out


# ── 3. ANTYREGRESJA — sedno zadania ──────────────────────────────────────────

def test_kalibracja_1x2_duza_roznica_pp_male_n_nie_jest_rozbieznoscia(capsys):
    """Replika zdarzenia z 26.08: koszyk "50-60%" n=113, model=54.6%,
    realnie≈61.1% (69/113), roznica≈+6.5pp. Przedział Wilsona dla 69/113
    to [51.8%; 69.5%] — 54.6% MIEŚCI SIĘ w środku, więc wiersz NIE ma prawa
    być oznaczony jako rozbieżność. To jest sedno całego zadania: bez tego
    testu naprawa mogłaby się cicho cofnąć do gołej różnicy w pp.
    """
    wiersze = (
        [{"pewnosc": 54.6, "tip_correct": 1}] * 69
        + [{"pewnosc": 54.6, "tip_correct": 0}] * 44
    )
    conn = _ConnKalibracji(wiersze)

    stan_uczenia.raport_kalibracji_1x2(conn)

    out = capsys.readouterr().out
    linia = _linia(out, "50-60%")
    assert "roznica=+6.5pp" in linia, linia
    assert "ROZBIEZNOSC" not in linia, linia
    assert "niepewnosci" in linia, linia


def test_kalibracja_1x2_koszyk_poza_przedzialem_wilsona_jest_oznaczony(capsys):
    """Kontrapunkt do testu wyżej — gdy model NAPRAWDĘ leży poza przedziałem
    Wilsona (tu: przy dużym n, więc wąski przedział), koszyk MA być oznaczony.
    n=200, trafienia=150 (realnie 75%), model deklarowany 50.0% (koszyk
    "50-60%" — granice domknięte od dołu) — Wilson dla 150/200 to
    [68.6%; 80.5%] i nie obejmuje 50%."""
    wiersze = (
        [{"pewnosc": 50.0, "tip_correct": 1}] * 150
        + [{"pewnosc": 50.0, "tip_correct": 0}] * 50
    )
    conn = _ConnKalibracji(wiersze)

    stan_uczenia.raport_kalibracji_1x2(conn)

    out = capsys.readouterr().out
    linia = _linia(out, "50-60%")
    assert "ROZBIEZNOSC" in linia, linia


# ── 4. Puste model_log — oba raporty piszą BRAK DANYCH, zero wyjątku ─────────

def test_oba_raporty_na_pustym_model_log_pisza_brak_danych(capsys):
    conn_obciazenia = _ConnObciazenia([])
    conn_kalibracji = _ConnKalibracji([])

    stan_uczenia.raport_obciazenia_modelu(conn_obciazenia)
    stan_uczenia.raport_kalibracji_1x2(conn_kalibracji)

    out = capsys.readouterr().out
    assert out.count("BRAK DANYCH") == 2, out


# ── 5. Nierozliczalny actual_result jest pomijany, nie wywraca raportu ──────

def test_raport_obciazenia_pomija_nierozliczalny_wynik(capsys):
    """5 wierszy z `prob_home`, jeden z dogrywką ("2-1 (AET)") — ma zniknąć
    z `n`, nie liczyć się jako błąd ani wywrócić raportu."""
    wiersze = [
        {"prob_home": 50.0, "prob_draw": None, "prob_away": None,
         "prob_over25": None, "prob_btts": None, "actual_result": "1-0"},
        {"prob_home": 50.0, "prob_draw": None, "prob_away": None,
         "prob_over25": None, "prob_btts": None, "actual_result": "1-0"},
        {"prob_home": 50.0, "prob_draw": None, "prob_away": None,
         "prob_over25": None, "prob_btts": None, "actual_result": "1-0"},
        {"prob_home": 50.0, "prob_draw": None, "prob_away": None,
         "prob_over25": None, "prob_btts": None, "actual_result": "0-1"},
        {"prob_home": 50.0, "prob_draw": None, "prob_away": None,
         "prob_over25": None, "prob_btts": None, "actual_result": "2-1 (AET)"},
    ]
    conn = _ConnObciazenia(wiersze)

    stan_uczenia.raport_obciazenia_modelu(conn)

    out = capsys.readouterr().out
    linia = _linia(out, "1 (prob_home)")
    assert "n=   4" in linia, linia
