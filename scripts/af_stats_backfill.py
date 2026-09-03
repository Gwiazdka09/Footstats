#!/usr/bin/env python
"""af_stats_backfill.py — dociąga strzały celne z API-Football do historii.

16 lig datasetu ma zero strzałów u football-data, więc `WAGA_STRZALOW=0.7` jest
tam cicho ignorowana: `form.sily_ligowe` przechodzi guard obecności kolumn,
po `dropna` dostaje pustkę i λ leci z samych goli.

DOMYŚLNIE NA SUCHO. Bez `--wykonaj` skrypt tylko liczy, ile meczów by dopasował
i ile requestów by wydał. Wydanie kilku tysięcy zapytań ze wspólnego z produkcją
limitu 7500/dobę ma być decyzją, nie efektem ubocznym uruchomienia.

    python scripts/af_stats_backfill.py --ligi "POL-Ekstraklasa" --od 2024-07-01
    python scripts/af_stats_backfill.py --ligi "POL-Ekstraklasa" --od 2024-07-01 --wykonaj

Zgodność pola sprawdzona ZANIM wydaliśmy budżet: na Eredivisie (liga mająca
strzały u obu źródeł) `Shots on Goal` z API-Football zgadza się z `HST`
z football-data w 60 z 60 meczów, co do sztuki.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from footstats.data.af_backfill import (  # noqa: E402
    REZERWA_POTOKU, SEZONY_KANDYDACI, backfill, dopasuj_mecze,
    fixtures_ligi_sezonu, pobierz_statystyki, wczytaj_mape_lig,
)
from footstats.data.af_stats import wczytaj_af_stats  # noqa: E402

# Poniżej tego odsetka dopasowań zapis jest wstrzymany. Tak niski wynik znaczy
# zepsutą mapę składu albo złe id ligi, nie brak danych u dostawcy — a wtedy
# to, co BY się zapisało, jest tym bardziej podejrzane.
PROG_DOPASOWANIA = 0.70


def zbuduj_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ligi", default=None,
                   help="ligi datasetu po przecinku (domyslnie: wszystkie z mapy)")
    p.add_argument("--od", default="2024-07-01", help="data od (YYYY-MM-DD)")
    p.add_argument("--budzet", type=int, default=3000,
                   help="maks. zapytan w tym przebiegu")
    p.add_argument("--wykonaj", action="store_true",
                   help="realnie wydaj zapytania (domyslnie: tylko raport)")
    p.add_argument("--force", action="store_true",
                   help=f"zapisz mimo dopasowania ponizej {PROG_DOPASOWANIA:.0%}")
    return p


def ligi_do_przebiegu(wybrane: list[str] | None) -> dict[str, dict]:
    mapa = wczytaj_mape_lig()
    if not wybrane:
        return mapa
    brak = [liga for liga in wybrane if liga not in mapa]
    if brak:
        raise SystemExit(
            f"Ligi bez id w data/af_league_ids.json: {brak}\n"
            "Id lig wybiera CZLOWIEK — automat po nazwie wybralby druga klase"
            " albo lige kobiet (patrz komentarz w tym pliku)."
        )
    return {liga: mapa[liga] for liga in wybrane}


def _klient():
    from footstats.core.apisports_gate import klucz as klucz_af
    from footstats.scrapers.api_football import APIFootball

    k = klucz_af()
    if not k:
        raise SystemExit("Brak klucza API-Football albo bramka zamknieta"
                         " (APISPORTS_ENABLED=0). Nic nie robie.")
    return APIFootball(k), k


def main() -> None:
    args = zbuduj_parser().parse_args()

    from footstats.data.historical_loader import load_cached

    wybrane = [x.strip() for x in args.ligi.split(",")] if args.ligi else None
    ligi = ligi_do_przebiegu(wybrane)
    if not ligi:
        raise SystemExit("Mapa lig pusta — sprawdz data/af_league_ids.json")

    df = load_cached(z_af=False)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    juz = wczytaj_af_stats()
    juz_klucze = set()
    if not juz.empty:
        juz_klucze = set(zip(
            pd.to_datetime(juz["date"], errors="coerce").dt.normalize(),
            juz["home"].astype(str), juz["away"].astype(str),
        ))

    klient, klucz = _klient()
    lacznie_par = lacznie_pobranych = 0

    for liga, wpis in ligi.items():
        podzbior = df[(df["league"] == liga) & (df["date"] >= args.od)]
        if podzbior.empty:
            print(f"{liga}: brak meczow od {args.od} — pomijam")
            continue

        fixtures: list[dict] = []
        for sezon in SEZONY_KANDYDACI:
            fixtures += fixtures_ligi_sezonu(klient, wpis["af_league_id"], sezon)

        pary, raport = dopasuj_mecze(podzbior, fixtures, juz_pobrane=juz_klucze)
        rozwazane = len(podzbior) - raport["juz_mamy"]
        odsetek = len(pary) / rozwazane if rozwazane else 0.0
        print(f"\n{liga}: {len(pary)}/{rozwazane} dopasowanych ({odsetek:.0%})  {raport}")

        if odsetek < PROG_DOPASOWANIA and not args.force:
            print(f"  ODMOWA: ponizej {PROG_DOPASOWANIA:.0%}. To znaczy zepsuta mapa"
                  " skladu albo zle id ligi, nie brak danych. Przejrzyj nazwy"
                  " albo uzyj --force.")
            continue

        lacznie_par += len(pary)
        if not args.wykonaj:
            continue

        wynik = backfill(pary, pobierz=pobierz_statystyki, api_key=klucz,
                         budzet=args.budzet - lacznie_pobranych)
        lacznie_pobranych += wynik["pobrane"]
        print(f"  pobrane={wynik['pobrane']} ok={wynik['ok']}"
              f" bez_statystyk={wynik['bez_statystyk']} stop={wynik['powod_stopu']}")
        if wynik["powod_stopu"] != "koniec":
            print(f"\n  PRZERWANE ({wynik['powod_stopu']}). Wznow ta sama komenda —"
                  " pobrane mecze sa juz w pliku i nie beda platne drugi raz.")
            break

    if not args.wykonaj:
        print(f"\nNA SUCHO: {lacznie_par} meczow do pobrania = tyle zapytan"
              f" (+ indeks fixture'ow). Rezerwa dla potoku: {REZERWA_POTOKU}.")
        print("Uruchom ponownie z --wykonaj, zeby realnie pobrac.")


if __name__ == "__main__":
    main()
