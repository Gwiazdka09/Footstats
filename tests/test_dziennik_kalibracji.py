"""test_dziennik_kalibracji.py — zapis KAŻDEJ oceny modelu, nie tylko obstawialnej.

PO CO: pipeline zapisuje do `predictions` wyłącznie to, co wyprodukował Groq,
czyli dopiero PO filtrze wartości (EV/Kelly). Log produkcyjny z 05.08:

    kandydaci=46 → blacklista lig → 3 → filtr EV/Kelly → 0 → zero predykcji

To nie jest awaria, tylko konsekwencja architektury: predykcja zapisuje się
tylko wtedy, gdy nadaje się do obstawienia. Ale kalibracja potrzebuje czegoś
innego — WSZYSTKICH przewidywań modelu wraz z wynikami, niezależnie od tego, czy
były opłacalne. Bez tego model nigdy się nie dowie, czy jego prawdopodobieństwa
są trafne, bo widzi wyłącznie rzadkie przypadki, które przeszły filtr.

Dziennik jest CELOWO osobną tabelą, nie kolejnym `kupon_type` w `predictions`:
20 zapytań w 10 modułach liczy z `predictions` skuteczność selekcji i żadne nie
filtruje po `kupon_type`. Dopisanie tam wierszy kalibracyjnych zafałszowałoby
każdą z tych metryk.

Rozdzielone są więc dwie rzeczy, które dotąd były sklejone:
  * SELEKCJA DO OBSTAWIANIA — zostaje ostra (tylko dodatnie EV);
  * DZIENNIK KALIBRACYJNY — zapisuje wszystko, zero wpływu na kupony.
"""
from __future__ import annotations

import pytest

from footstats.core import kalibracja_log as kl


class _Kursor:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _Conn:
    """Atrapa bazy — notuje zapytania, oddaje ustalone wiersze."""

    def __init__(self, istnieje=None, pending=None):
        self.istnieje = istnieje
        self.pending = pending or []
        self.zapytania: list[tuple] = []
        self.blad: Exception | None = None

    def execute(self, sql, params=()):
        if self.blad is not None:
            raise self.blad
        plaski = " ".join(sql.split())
        self.zapytania.append((plaski, params))
        g = plaski.upper()
        if g.startswith("SELECT ID FROM MODEL_LOG"):
            return _Kursor([{"id": 7}] if self.istnieje else [])
        if g.startswith("SELECT") and "TIP_CORRECT IS NULL" in g:
            return _Kursor(self.pending)
        if "INSERT INTO MODEL_LOG" in g:
            return _Kursor([{"id": 42}])
        return _Kursor([])

    def executescript(self, sql):
        self.zapytania.append((" ".join(sql.split()), ()))

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def zawierajace(self, fragment: str) -> list[tuple]:
        return [z for z in self.zapytania if fragment.upper() in z[0].upper()]


@pytest.fixture
def baza(monkeypatch):
    stan = {"conn": _Conn()}
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: stan["conn"])
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: None)
    return stan


def _kandydat(**nadpisz) -> dict:
    k = {
        "gospodarz": "Legia", "goscie": "Lech", "liga": "POL-Ekstraklasa",
        "data": "2026-08-10",
        "pw": 55.0, "pr": 25.0, "pp": 20.0, "o25": 48.0, "bt": 52.0,
        "lambda_h": 1.62, "lambda_a": 1.05,
    }
    k.update(nadpisz)
    return k


# ── zapis pojedynczej oceny ────────────────────────────────────────────────

def test_zapisuje_ocene_modelu(baza):
    assert kl.zapisz_ocene(_kandydat()) == 42
    assert baza["conn"].zawierajace("INSERT INTO model_log")


def test_zapisuje_prawdopodobienstwa_1x2(baza):
    kl.zapisz_ocene(_kandydat(pw=60.0, pr=22.0, pp=18.0))

    params = baza["conn"].zawierajace("INSERT INTO model_log")[0][1]

    assert 60.0 in params and 22.0 in params and 18.0 in params


def test_zapisuje_lambdy(baza):
    """λ to rdzeń modelu — bez nich nie da się ocenić, czy Poisson był dobrze
    wyskalowany, a tylko czy typ trafił."""
    kl.zapisz_ocene(_kandydat(lambda_h=2.10, lambda_a=0.85))

    params = baza["conn"].zawierajace("INSERT INTO model_log")[0][1]

    assert 2.10 in params and 0.85 in params


def test_zapisuje_rynki_pochodne(baza):
    kl.zapisz_ocene(_kandydat(o25=63.0, bt=58.0))

    params = baza["conn"].zawierajace("INSERT INTO model_log")[0][1]

    assert 63.0 in params and 58.0 in params


def test_wyznacza_typ_z_argmaxu(baza):
    """Typ modelu to argmax jego własnych prawdopodobieństw — nie wybór Groq."""
    kl.zapisz_ocene(_kandydat(pw=20.0, pr=25.0, pp=55.0))

    params = baza["conn"].zawierajace("INSERT INTO model_log")[0][1]

    assert "2" in params


@pytest.mark.parametrize("pw,pr,pp,typ", [
    (60.0, 20.0, 20.0, "1"), (20.0, 60.0, 20.0, "X"), (20.0, 20.0, 60.0, "2"),
])
def test_argmax_dla_kazdego_faworyta(baza, pw, pr, pp, typ):
    kl.zapisz_ocene(_kandydat(pw=pw, pr=pr, pp=pp))

    assert typ in baza["conn"].zawierajace("INSERT INTO model_log")[0][1]


def test_pomija_kandydata_bez_prawdopodobienstw(baza):
    """Wiersz bez prob to nie jest ocena modelu — nie ma czego kalibrować."""
    assert kl.zapisz_ocene(_kandydat(pw=None, pr=None, pp=None)) is None
    assert baza["conn"].zawierajace("INSERT INTO model_log") == []


def test_pomija_kandydata_bez_nazw(baza):
    assert kl.zapisz_ocene(_kandydat(gospodarz="")) is None


def test_pomija_kandydata_bez_daty(baza):
    """Bez daty meczu nie da się później dopasować wyniku."""
    assert kl.zapisz_ocene(_kandydat(data="")) is None


# ── dedup ───────────────────────────────────────────────────────────────────

def test_ten_sam_mecz_nie_dubluje_sie(baza):
    """Job final i evening oceniają ten sam mecz — bez dedupu kalibracja
    liczyłaby go dwukrotnie i zawyżała pewność."""
    baza["conn"].istnieje = True

    assert kl.zapisz_ocene(_kandydat()) == 7
    assert baza["conn"].zawierajace("INSERT INTO model_log") == []


def test_dedup_po_meczu_i_dacie(baza):
    kl.zapisz_ocene(_kandydat())

    sql = baza["conn"].zawierajace("SELECT id FROM model_log")[0][0]

    assert "team_home" in sql and "team_away" in sql and "match_date" in sql


# ── zapis partii ────────────────────────────────────────────────────────────

def test_zapisuje_cala_liste(baza):
    kandydaci = [_kandydat(gospodarz=f"Klub{i}") for i in range(5)]

    assert kl.zapisz_partie(kandydaci) == 5


def test_partia_pomija_wadliwe_ale_zapisuje_reszte(baza):
    """Jeden zepsuty kandydat nie może zablokować zapisu pozostałych."""
    kandydaci = [_kandydat(), _kandydat(pw=None), _kandydat(gospodarz="Trzeci")]

    assert kl.zapisz_partie(kandydaci) == 2


def test_pusta_lista_nie_wywala(baza):
    assert kl.zapisz_partie([]) == 0


def test_awaria_bazy_nie_zatrzymuje_pipeline(baza):
    """Dziennik to obserwacja, nie warunek działania — jego awaria nie może
    zabić generowania kuponów."""
    baza["conn"].blad = RuntimeError("brak polaczenia")

    assert kl.zapisz_partie([_kandydat()]) == 0


# ── rozliczanie ─────────────────────────────────────────────────────────────

def test_pobiera_nierozliczone(baza):
    baza["conn"].pending = [
        {"id": 1, "team_home": "Legia", "team_away": "Lech",
         "match_date": "2026-08-01", "model_tip": "1"},
    ]

    assert len(kl.pobierz_nierozliczone(dni_wstecz=14)) == 1


def test_nierozliczone_ograniczone_oknem(baza):
    kl.pobierz_nierozliczone(dni_wstecz=30)

    sql = baza["conn"].zapytania[0][0]

    assert "match_date" in sql and "tip_correct IS NULL" in sql


def test_zapisuje_wynik_i_trafnosc(baza):
    kl.zapisz_wynik(5, "2-1", model_tip="1")

    sql, params = baza["conn"].zawierajace("UPDATE model_log")[0]

    assert "actual_result" in sql and "tip_correct" in sql
    assert 5 in params


@pytest.mark.parametrize("typ,wynik,oczekiwane", [
    ("1", "2-1", 1), ("1", "1-2", 0), ("X", "1-1", 1), ("2", "0-3", 1),
])
def test_trafnosc_liczona_z_typu_modelu(baza, typ, wynik, oczekiwane):
    kl.zapisz_wynik(5, wynik, model_tip=typ)

    params = baza["conn"].zawierajace("UPDATE model_log")[0][1]

    assert oczekiwane in params


@pytest.mark.parametrize("wynik,typ", [
    (None, "1"), ("", "1"),
    ("2-1", "Nieznany rynek XYZ"),       # typ, ktorego parser nie rozpoznaje
])
def test_nierozliczalny_wynik_nie_zapisuje_trafnosci(baza, wynik, typ):
    """„Nie wiemy" to nie to samo co „model sie pomylil" — zapis 0 zafalszowalby
    kalibracje, a wiersz wygladalby na rozliczony i nie wrocilby do kolejki."""
    assert kl.zapisz_wynik(5, wynik, model_tip=typ) is False
    assert baza["conn"].zawierajace("UPDATE model_log") == []


# ── tabela musi powstac zanim ktokolwiek o nia zapyta ──────────────────────
#
# REGRESJA 2026-08-06: `init_kalibracja_log()` odpalal sie WYLACZNIE w
# `zapisz_partie` (czyli w dziennym jobie). Endpoint `/cron/kalibracja-rozlicz`
# wolal `pobierz_nierozliczone` jako pierwszy i dostawal
# `relation "model_log" does not exist` -> HTTP 500 z golym tracebackiem.

def test_pobieranie_tworzy_tabele_gdy_brak(monkeypatch):
    """Czytelnik nie moze zakladac, ze ktos inny juz utworzyl tabele."""
    wolania = []
    monkeypatch.setattr(kl, "init_kalibracja_log", lambda: wolania.append("init"))
    monkeypatch.setattr(kl, "_connect", lambda *a, **k: _Conn())

    kl.pobierz_nierozliczone()

    assert wolania == ["init"]
