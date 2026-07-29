"""
closing_odds.py — darmowe kursy zamknięcia z football-data.co.uk.

Po co: `core/clv_tracker.record_closing_odds` istnieje od dawna, ale nie miał
taniego źródła kursu zamknięcia. API-Football ma budżet 100 zapytań/dzień i podaje
kursy tylko dla nadchodzących meczów, więc historii nie da się nadrobić.

Tymczasem CSV football-data.co.uk — który projekt i tak pobiera (`FootballDataSource`,
cache 6h) — ma 132 kolumny, w tym komplet kursów ZAMKNIĘCIA:
    PSCH/PSCD/PSCA   — Pinnacle (najostrzejszy bukmacher, wzorzec CLV)
    AvgCH/AvgCD/AvgCA — średnia rynkowa
    PC>2.5 / PC<2.5   — Pinnacle Over/Under 2.5

Dlaczego to ważne: bicie **linii zamknięcia** to jedyny uczciwy test, czy model ma
edge. Sama trafność nic nie mówi, jeśli graliśmy po kursach gorszych niż rynkowe.
To wprost karmi walidację P1 (czy w ogóle flipować progi selekcji).

UWAGA: to football-data.co.uk (CSV), NIE football-data.org (API) — inne serwisy.
"""
from __future__ import annotations

import csv
import io
import logging

from footstats.scrapers.sources.footballdata_source import KODY_LIG, FootballDataSource
from footstats.utils.normalize import _norm_ascii

log = logging.getLogger(__name__)

# Kolejność prób: najostrzejszy rynek najpierw. Pinnacle prawie nie ma marży
# i najszybciej wchłania informację, więc jest najuczciwszym punktem odniesienia.
_ZRODLA_1X2 = (
    ("pinnacle-closing", "PSCH", "PSCD", "PSCA"),
    ("rynek-avg-closing", "AvgCH", "AvgCD", "AvgCA"),
    ("rynek-max-closing", "MaxCH", "MaxCD", "MaxCA"),
)

_ZRODLA_OU = (
    ("PC>2.5", "PC<2.5"),
    ("AvgC>2.5", "AvgC<2.5"),
    ("B365C>2.5", "B365C<2.5"),
)


def _sezon_z_daty(data_iso: str) -> str:
    """
    YYYY-MM-DD → kod sezonu football-data.co.uk (np. '2526' dla 2025/26).

    Sezon europejski startuje w lipcu, więc styczeń-czerwiec należy do sezonu,
    który zaczął się w POPRZEDNIM roku kalendarzowym.
    """
    rok, miesiac = int(data_iso[:4]), int(data_iso[5:7])
    start = rok if miesiac >= 7 else rok - 1
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def _csv_ligi(kod_ligi: str, sezon: str) -> str | None:
    """CSV ligi (reużywa pobierania i cache 6h z FootballDataSource). None przy błędzie."""
    try:
        return FootballDataSource()._pobierz_csv(kod_ligi, sezon)
    except (OSError, ValueError, KeyError) as e:
        log.debug("closing_odds: brak CSV %s/%s: %s", kod_ligi, sezon, e)
        return None


def _float(surowa: object) -> float | None:
    """Kurs jako float. None gdy pusty, nieliczbowy albo niemożliwy (<= 1.0)."""
    try:
        wartosc = float(str(surowa).strip())
    except (TypeError, ValueError):
        return None
    return wartosc if wartosc > 1.0 else None


def _data_csv_na_iso(surowa: str) -> str | None:
    """'15/08/2025' → '2025-08-15'. None gdy format inny."""
    czesci = (surowa or "").strip().split("/")
    if len(czesci) != 3:
        return None
    dzien, miesiac, rok = czesci
    if len(rok) == 2:
        rok = f"20{rok}"
    if not (dzien.isdigit() and miesiac.isdigit() and rok.isdigit()):
        return None
    return f"{rok}-{int(miesiac):02d}-{int(dzien):02d}"


def _kursy_z_wiersza(wiersz: dict) -> dict | None:
    """Wiersz CSV → {home, draw, away, [over_2_5, under_2_5], zrodlo}. None gdy brak 1X2."""
    for nazwa, k_h, k_d, k_a in _ZRODLA_1X2:
        home, draw, away = _float(wiersz.get(k_h)), _float(wiersz.get(k_d)), _float(wiersz.get(k_a))
        if home and draw and away:
            kursy = {"home": home, "draw": draw, "away": away, "zrodlo": nazwa}
            for k_over, k_under in _ZRODLA_OU:
                over, under = _float(wiersz.get(k_over)), _float(wiersz.get(k_under))
                if over and under:
                    kursy["over_2_5"] = over
                    kursy["under_2_5"] = under
                    break
            return kursy
    return None


def kursy_zamkniecia(
    gospodarz: str,
    goscie: str,
    data: str,
    kody_lig: list[str] | None = None,
) -> dict | None:
    """
    Kursy zamknięcia dla konkretnego meczu. None gdy nie znaleziono.

    Dopasowanie po `_norm_ascii` i WYŁĄCZNIE w tym samym kierunku (gospodarz musi
    być gospodarzem) — odwrócony mecz to inne zdarzenie i zafałszowałby CLV.
    Zawiera też dopasowanie po prefiksie, bo CSV używa krótkich nazw
    ("Aston Villa" vs nasze "Aston Villa FC").
    """
    cel_g, cel_a = _norm_ascii(gospodarz), _norm_ascii(goscie)
    if not cel_g or not cel_a:
        return None

    sezon = _sezon_z_daty(data)
    for kod_ligi in (kody_lig or list(KODY_LIG)):
        tekst = _csv_ligi(kod_ligi, sezon)
        if not tekst:
            continue
        try:
            wiersze = csv.DictReader(io.StringIO(tekst))
        except (csv.Error, ValueError):
            continue

        for wiersz in wiersze:
            if _data_csv_na_iso(wiersz.get("Date", "")) != data:
                continue
            csv_g = _norm_ascii(wiersz.get("HomeTeam", "") or "")
            csv_a = _norm_ascii(wiersz.get("AwayTeam", "") or "")
            if not _pasuje(csv_g, cel_g) or not _pasuje(csv_a, cel_a):
                continue
            kursy = _kursy_z_wiersza(wiersz)
            if kursy:
                kursy["liga"] = KODY_LIG.get(kod_ligi, kod_ligi)
                return kursy
    return None


def _pasuje(z_csv: str, nasze: str) -> bool:
    """Zgodność nazw: dokładna albo prefiksowa (CSV skraca — 'Aston Villa' vs '... FC')."""
    if not z_csv or not nasze:
        return False
    return z_csv == nasze or nasze.startswith(z_csv) or z_csv.startswith(nasze)
