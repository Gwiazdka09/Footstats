"""Raport stanu pętli uczenia — co realnie wchodzi, a co stoi. TYLKO ODCZYT.

PO CO: pętla ma cztery ogniwa i każde potrafi paść po cichu, dając ten sam
objaw co „jeszcze za mało danych":

    predykcja z `factors` → rozliczenie → lekcja w `ai_feedback` → wzorzec z RAG

Historia projektu to lista takich cichych awarii: `json_each` nie istnieje na
PostgreSQL (RAG milczał zawsze), `data_full` w heurystyce zmęczenia (tagi nie
zapalały się ani razu), brak `sentence-transformers` wywalający CAŁY blok
lekcji. Wszystkie z zielonymi testami. Ten raport pyta produkcję wprost.

Użycie:
    python -m scripts.stan_uczenia
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Próg z `scripts/porownaj_modele.py` — poniżej niego werdykt nie zapada.
MIN_ROZLICZONYCH = 30

# Osobny od MIN_ROZLICZONYCH mimo tej samej wartości — tamten dotyczy CAŁEJ
# próby przed werdyktem modelu, ten POJEDYNCZEGO koszyka w raporcie remisów.
# To ostrzeżenie o mocy statystycznej, nie wyrok: koszyk „30%+” z 26.08 miał
# n=33 i wypadł istotnie (test dwumianowy wobec bazy 23.6% dał p=0.024 po
# korekcie Šidáka na 5 koszyków) mimo że ledwie przekracza próg.
PROG_MALA_PROBA = 30


def _licz(conn, zapytanie: str) -> list[dict]:
    return [dict(r) for r in conn.execute(zapytanie).fetchall()]


def raport_predykcji(conn) -> dict:
    """Ile predykcji ma niepuste `factors` — kryterium odbioru U1."""
    wiersze = _licz(conn, """
        SELECT model_source,
               COUNT(*) AS wszystkie,
               COUNT(*) FILTER (WHERE factors <> '[]' AND factors <> '') AS z_faktorami,
               COUNT(tip_correct) AS rozliczone,
               COALESCE(SUM(tip_correct), 0) AS trafione
        FROM predictions
        GROUP BY model_source
        ORDER BY wszystkie DESC
    """)
    print("=== PREDYKCJE ===")
    print(f"{'model':14} {'razem':>7} {'z factors':>10} {'rozliczone':>11} {'trafione':>9}")
    for w in wiersze:
        print(f"{str(w['model_source'] or '(brak)'):14} {w['wszystkie']:7}"
              f" {w['z_faktorami']:10} {w['rozliczone']:11} {w['trafione']:9}")
    _raport_kursow(conn)
    return {w["model_source"]: w for w in wiersze}


def _raport_kursow(conn) -> None:
    """Ile predykcji ma kurs POTWIERDZONY, a ile tylko zaproponowany przez Groqa.

    Zapis do `predictions` dzieje sie w KROKU 3 `daily_agent`, a anty-halucynacyjna
    podmiana kursu dopiero w KROKU 4 — wiersze sprzed uzgodnienia (migracja 13)
    trzymaja kurs od modelu jezykowego. Na prodzie oznaczalo to ten sam kurs 52.58
    na trzech roznych meczach jednego dnia. ROI i CLV z takich wierszy nie znacza nic.
    """
    try:
        wiersze = _licz(conn, """
            SELECT COUNT(*) AS wszystkie,
                   COALESCE(SUM(CASE WHEN COALESCE(odds_verified, 0) = 1 THEN 1 ELSE 0 END), 0)
                       AS zweryfikowane,
                   COALESCE(SUM(CASE WHEN odds IS NOT NULL AND (odds < 1.2 OR odds > 4.0)
                                     THEN 1 ELSE 0 END), 0) AS poza_filtrem
            FROM predictions
        """)
    except Exception as e:                                   # noqa: BLE001
        # Skrypt chodzi lokalnie przeciw produkcji, a migracja 13 wchodzi dopiero
        # z nowym obrazem — brak kolumny to stan przejsciowy, nie awaria. Ale musi
        # byc WIDOCZNY, inaczej raport milczy o tym, ze kursy sa niezweryfikowane.
        if "odds_verified" in str(e):
            # Postgres zostawia transakcje w stanie aborted — bez rollbacku KAZDY
            # kolejny raport w tym polaczeniu pada, i to na cudzym zapytaniu.
            try:
                conn.rollback()
            except Exception:                                # noqa: BLE001
                pass
            print("\n  kurs zweryfikowany: BRAK KOLUMNY — migracja 13 niewdrozona."
                  "\n  → wszystkie kursy w `predictions` pochodza sprzed weryfikacji (KROK 4).")
            return
        raise
    if not wiersze:
        return
    w = wiersze[0]
    if not w.get("wszystkie"):
        return
    udzial = 100.0 * w["zweryfikowane"] / w["wszystkie"]
    print(f"\n  kurs zweryfikowany: {w['zweryfikowane']}/{w['wszystkie']} ({udzial:.0f}%)")
    if w["poza_filtrem"]:
        print(f"  kurs poza filtrem longshotow 1.2-4.0: {w['poza_filtrem']}"
              f" — te wiersze opisuja PROPOZYCJE, nie zagrane typy")
    if udzial < 100.0:
        print("  → ROI i CLV licz wylacznie na zweryfikowanych"
              " (reszta to kurs zaproponowany przez Groqa).")


def raport_lekcji(conn) -> None:
    """Lekcje uczą się TYLKO z porażek — pokazujemy skalę tego przechyłu."""
    wiersz = _licz(conn, """
        SELECT COUNT(*) AS lekcji,
               COUNT(DISTINCT match_id) AS meczow
        FROM ai_feedback
    """)[0]
    rozliczone = _licz(conn, """
        SELECT COALESCE(SUM(CASE WHEN tip_correct = 0 THEN 1 ELSE 0 END), 0) AS porazki,
               COALESCE(SUM(CASE WHEN tip_correct = 1 THEN 1 ELSE 0 END), 0) AS sukcesy
        FROM predictions WHERE tip_correct IS NOT NULL
    """)[0]

    print("\n=== LEKCJE (ai_feedback) ===")
    print(f"  lekcji: {wiersz['lekcji']} | dotyczą {wiersz['meczow']} meczów")
    print(f"  rozliczone predykcje: {rozliczone['porazki']} porażek"
          f" / {rozliczone['sukcesy']} trafień")
    if rozliczone["porazki"]:
        pokrycie = wiersz["meczow"] / rozliczone["porazki"] * 100
        print(f"  pokrycie porażek lekcjami: {pokrycie:.0f}%")
    print("  UWAGA: `_pobierz_porazki` bierze wyłącznie tip_correct = 0 —"
          " baza lekcji jest z definicji jednostronna.")


def raport_wzorcow(conn) -> None:
    """Czy RAG ma z czego liczyć wzorzec: rozliczone predykcje Z czynnikami."""
    wiersz = _licz(conn, """
        SELECT COUNT(*) AS gotowe
        FROM predictions
        WHERE tip_correct IS NOT NULL
          AND factors <> '[]' AND factors <> ''
    """)[0]
    print("\n=== WZORCE RAG ===")
    print(f"  rozliczonych predykcji z czynnikami: {wiersz['gotowe']}")
    if not wiersz["gotowe"]:
        print("  → `pobierz_rag_wzorce` zwróci pusty string niezależnie od zapytania.")
        print("    To NIE jest awaria — to brak paliwa.")


def raport_dziennika(conn) -> dict:
    """Skuteczność z `model_log` — dziennika zapisywanego PRZED filtrami wartości.

    PO CO OSOBNO OD `predictions`: tamta tabela dostaje wiersz dopiero wtedy, gdy
    mecz przejdzie filtry i nadaje się do obstawienia. 2026-08-13 produkcja:
    `kandydaci=45, po filtrach=0` — trzeci dzień z rzędu zero predykcji, więc
    raport pokazywał pętlę jako martwą. `model_log` w tym samym tygodniu zebrał
    202 oceny, z czego 105 rozliczonych. Dane były, tylko nikt ich nie czytał.
    """
    wiersze = _licz(conn, """
        SELECT model_source,
               COUNT(*) AS wpisow,
               COUNT(actual_result) AS rozliczone,
               COALESCE(SUM(tip_correct), 0) AS trafione
        FROM model_log
        GROUP BY model_source
        ORDER BY wpisow DESC
    """)
    print("\n=== DZIENNIK MODELU (model_log — przed filtrami) ===")
    if not wiersze:
        print("  PUSTY — to AWARIA, nie brak paliwa.")
        print("  `model_log` zapisuje się przed filtrami, więc pustka znaczy,")
        print("  że przebieg nie doszedł nawet do oceny modelu.")
        return {}

    print(f"{'model':14} {'wpisow':>7} {'rozliczone':>11} {'trafione':>9} {'skutecznosc':>12}")
    for w in wiersze:
        rozl = w["rozliczone"] or 0
        skut = f"{100.0 * w['trafione'] / rozl:.1f}%" if rozl else "—"
        print(f"{str(w['model_source'] or '(brak)'):14} {w['wpisow']:7}"
              f" {rozl:11} {w['trafione']:9} {skut:>12}")
    return {w["model_source"]: w for w in wiersze}


# Kolejnosc koszykow pewnosci 1X2 — stala, zeby nie zalezec od kolejnosci
# zwroconej przez baze (patrz zasada „sortowanie koszykow jawnie w Pythonie”
# w `raport_remisow`). Tutaj bucketing dzieje sie CALY w Pythonie, nie w SQL
# CASE, wlasnie po to, zeby granice 40/50/60/70 dalo sie przetestowac wprost
# na wartosciach granicznych, bez uruchamiania prawdziwej bazy.
_KOSZYKI_1X2 = ("<40%", "40-50%", "50-60%", "60-70%", "70%+")


def _koszyk_pewnosci(pewnosc: float) -> str:
    """Koszyk pewnosci modelu we WLASNYM typie 1X2 (GREATEST z trzech prob).

    Granice domkniete OD DOLU: 40.0 trafia juz do „40-50%”, nie do „<40%” —
    ten sam ksztalt co CASE w `raport_rynkow_golowych`/`raport_remisow`.
    """
    if pewnosc < 40:
        return "<40%"
    if pewnosc < 50:
        return "40-50%"
    if pewnosc < 60:
        return "50-60%"
    if pewnosc < 70:
        return "60-70%"
    return "70%+"


def raport_kalibracji_1x2(conn) -> None:
    """Czy pewnosc modelu we WLASNYM typie 1X2 jest wiarygodna? (model_log)

    PEWNOSC = GREATEST(prob_home, prob_draw, prob_away), czyli prawdopodobienstwo
    przypisane do argmaksu — niezaleznie od tego, ktora z trzech opcji wygrala.
    Zestawione z `tip_correct` (trafnosc TEGO argmaksu), a nie z pojedynczym
    prob_home/prob_draw/prob_away — inaczej mieszalibysmy pewnosc typu "1" z
    trafnoscia typu "X" w tym samym koszyku.

    ROZNICA W PP (realna minus deklarowana) jest sednem raportu: dodatnia
    znaczy, ze model jest NIEDOSZACOWANY w danym koszyku (realnie trafia
    czesciej, niz sam deklaruje), ujemna — ze jest ZA PEWNY SIEBIE. Sama
    krzywa rosnaca (jak w `raport_rynkow_golowych`/`raport_remisow`) mowi
    tylko, czy liczba cokolwiek rozroznia — te dwie diagnozy sa rozne i
    obie sa tu pokazane osobno.
    """
    print("\n=== KALIBRACJA 1X2: czy GREATEST(prob_home, prob_draw, prob_away)"
          " jest wiarygodne? (model_log) ===")
    # Bez sklejania nazw kolumn f-stringiem (bandit B608) — kolumny sa wprost
    # wypisane, tak jak w `raport_rynkow_golowych`.
    wiersze = _licz(conn, """
        SELECT GREATEST(prob_home, prob_draw, prob_away) AS pewnosc, tip_correct
        FROM model_log
        WHERE tip_correct IS NOT NULL
          AND prob_home IS NOT NULL AND prob_draw IS NOT NULL AND prob_away IS NOT NULL
    """)
    if not wiersze:
        print("  BRAK DANYCH — model_log nie ma jeszcze zadnego rozliczonego wiersza"
              " z kompletem prob_home/prob_draw/prob_away.")
        return

    grupy: dict[str, list[dict]] = {nazwa: [] for nazwa in _KOSZYKI_1X2}
    for w in wiersze:
        grupy[_koszyk_pewnosci(float(w["pewnosc"]))].append(w)

    koszyki = []
    for nazwa in _KOSZYKI_1X2:
        wpisy = grupy[nazwa]
        if not wpisy:
            continue
        n = len(wpisy)
        model = sum(float(w["pewnosc"]) for w in wpisy) / n
        realnie = 100.0 * sum(w["tip_correct"] for w in wpisy) / n
        koszyki.append({"koszyk": nazwa, "n": n, "model": model, "realnie": realnie})

    for k in koszyki:
        roznica = k["realnie"] - k["model"]
        znacznik = " — mala proba" if k["n"] < PROG_MALA_PROBA else ""
        print(f"  {k['koszyk']:8} n={k['n']:4}  model={k['model']:.1f}%"
              f"  realnie={k['realnie']:.1f}%  roznica={roznica:+.1f}pp{znacznik}")

    realne = [k["realnie"] for k in koszyki]
    rosnie = all(a <= b for a, b in zip(realne, realne[1:]))
    werdykt = "ROSNIE — liczba rozroznia" if rosnie else "NIE rosnie — brak uporzadkowania"
    print(f"  → krzywa {werdykt} (rozpietosc {max(realne) - min(realne):.1f} pp)")


def raport_rynkow_golowych(conn) -> None:
    """Czy prawdopodobieństwo modelu ROZRÓŻNIA mecze — osobno dla Over 2.5 i BTTS.

    D4, 2026-08-24. `model_log` od początku zapisywał `prob_over25` i `prob_btts`,
    ale mierzył wyłącznie `tip_correct`, czyli argmax 1X2. Rynki golowe — dziś
    główne wyjście selekcji — nie były sprawdzane z niczym. Wynik leżał w tej samej
    tabeli jako pełny rezultat (`"3-1"`), więc dało się je ocenić wstecznie.

    RAPORT POKAZUJE KOSZYKI, NIE ŚREDNIĄ, i to jest cały sens. Model, który zawsze
    mówi 52% przy realnych 52%, jest idealnie skalibrowany i zupełnie bezużyteczny.
    Dopiero rosnąca krzywa przez koszyki znaczy, że liczba cokolwiek rozróżnia.

    UWAGA PRZY CZYTANIU: to porównanie z WYNIKIEM, nie z rynkiem. Model może być
    świetnie skalibrowany i dalej przegrywać z kursami — tak właśnie wyszło dla
    1X2 (pomiar 14.08, n=15 460).
    """
    # Zapytanie jest CELOWO rozpisane dwa razy zamiast sklejane z nazw kolumn.
    # Wersja z f-stringiem czytala sie krocej, ale bandit slusznie ja blokowal
    # (B608) — nazwa kolumny wstawiana w SQL to wzorzec, ktory raz uzyty zaczyna
    # wedrowac po projekcie i konczy na wartosci z zewnatrz.
    wiersze = _licz(conn, """
        SELECT 'Over 2.5' AS rynek,
               CASE WHEN prob_over25 < 45 THEN '<45%'
                    WHEN prob_over25 < 50 THEN '45-50%'
                    WHEN prob_over25 < 55 THEN '50-55%'
                    WHEN prob_over25 < 60 THEN '55-60%'
                    ELSE '60%+' END AS koszyk,
               MIN(prob_over25) AS od, COUNT(*) AS n,
               AVG(prob_over25) AS model,
               100.0 * AVG(over25_correct) AS realnie
        FROM model_log WHERE over25_correct IS NOT NULL AND prob_over25 IS NOT NULL
        GROUP BY 1, 2
        UNION ALL
        SELECT 'BTTS',
               CASE WHEN prob_btts < 45 THEN '<45%'
                    WHEN prob_btts < 50 THEN '45-50%'
                    WHEN prob_btts < 55 THEN '50-55%'
                    WHEN prob_btts < 60 THEN '55-60%'
                    ELSE '60%+' END,
               MIN(prob_btts), COUNT(*),
               AVG(prob_btts),
               100.0 * AVG(btts_correct)
        FROM model_log WHERE btts_correct IS NOT NULL AND prob_btts IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1 DESC, 3
    """)

    for nazwa in ("Over 2.5", "BTTS"):
        koszyki = [w for w in wiersze if w["rynek"] == nazwa]
        print(f"\n=== {nazwa}: czy model rozróżnia mecze? (model_log) ===")
        if not koszyki:
            print("  BRAK DANYCH — uruchom `uzupelnij_rynki_golowe(dry_run=False)`.")
            continue
        for w in koszyki:
            print(f"  {str(w['koszyk']):8} n={w['n']:4}"
                  f"  model={float(w['model']):.1f}%  realnie={float(w['realnie']):.1f}%")
        realne = [float(w["realnie"]) for w in koszyki]
        rosnie = all(a <= b for a, b in zip(realne, realne[1:]))
        werdykt = "ROSNIE — liczba rozroznia" if rosnie else "NIE rosnie — brak uporzadkowania"
        print(f"  → krzywa {werdykt} (rozpietosc {max(realne) - min(realne):.1f} pp)")


def raport_remisow(conn) -> None:
    """Czy `prob_draw` ROZRÓŻNIA mecze, skoro argmax 1X2 nigdy go nie wybiera.

    Pomiar 26.08 (n=427 z wynikiem): `model_tip` = "X" wystąpił ZERO razy
    (304x "1", 123x "2"), bo `prob_draw` ma maksimum 34% i nie może pokonać
    dwóch pozostałych opcji w argmaksie. Remis to jednak 23.6% realnych wyników —
    zdanie modelu o co czwartym meczu nie było zweryfikowane ani razu, bo
    `tip_correct` strukturalnie go nie widzi. `draw_correct` (D-remis, ten sam
    kształt co D4 dla Over 2.5/BTTS) liczy się z SAMEGO WYNIKU, niezależnie
    od tego, co obstawił model.

    KOSZYKI, NIE ŚREDNIA — jak w `raport_rynkow_golowych`: model mówiący zawsze
    „24%" przy realnych 24% jest skalibrowany i bezużyteczny. Rosnąca krzywa
    przez koszyki znaczy, że liczba cokolwiek rozróżnia.
    """
    print("\n=== REMISY: czy prob_draw rozróżnia mecze? (model_log) ===")
    baza = _licz(conn, """
        SELECT COUNT(*) AS n, 100.0 * AVG(draw_correct) AS realnie
        FROM model_log WHERE draw_correct IS NOT NULL
    """)
    if not baza or not baza[0]["n"]:
        print("  BRAK DANYCH — uruchom `uzupelnij_rynki_golowe(dry_run=False)`.")
        return
    print(f"  linia bazowa: n={baza[0]['n']}, realna czestosc remisow"
          f" {float(baza[0]['realnie']):.1f}%")

    # Zapytanie rozpisane wprost, bez sklejania nazw kolumn f-stringiem — patrz
    # komentarz w `raport_rynkow_golowych` (bandit B608 slusznie to blokuje).
    # `prob_draw IS NOT NULL` obok `draw_correct IS NOT NULL`: bez tego wiersz
    # z NULL w prob_draw wpadlby do CASE-owego ELSE, czyli koszyka '30%+'.
    koszyki = _licz(conn, """
        SELECT CASE WHEN prob_draw < 15 THEN '<15%'
                    WHEN prob_draw < 20 THEN '15-20%'
                    WHEN prob_draw < 25 THEN '20-25%'
                    WHEN prob_draw < 30 THEN '25-30%'
                    ELSE '30%+' END AS koszyk,
               MIN(prob_draw) AS od, COUNT(*) AS n,
               AVG(prob_draw) AS model,
               100.0 * AVG(draw_correct) AS realnie
        FROM model_log WHERE draw_correct IS NOT NULL AND prob_draw IS NOT NULL
        GROUP BY 1
        ORDER BY 2
    """)
    if not koszyki:
        print("  BRAK DANYCH — uruchom `uzupelnij_rynki_golowe(dry_run=False)`.")
        return
    # `ORDER BY 2` w zapytaniu sortuje po `od`, ale ta kolumna nigdzie sie nie
    # drukuje — ktos moglby ja usunac jako "nieuzywana" i ORDER BY 2 zaczalby
    # cicho sortowac po COUNT(*). Porzadek koszykow wymuszamy wiec jawnie tutaj.
    koszyki = sorted(koszyki, key=lambda w: float(w["od"]))
    for w in koszyki:
        znacznik = " — mala proba" if w["n"] < PROG_MALA_PROBA else ""
        print(f"  {str(w['koszyk']):8} n={w['n']:4}"
              f"  model={float(w['model']):.1f}%  realnie={float(w['realnie']):.1f}%{znacznik}")
    realne = [float(w["realnie"]) for w in koszyki]
    rosnie = all(a <= b for a, b in zip(realne, realne[1:]))
    werdykt = "ROSNIE — liczba rozroznia" if rosnie else "NIE rosnie — brak uporzadkowania"
    print(f"  → krzywa {werdykt} (rozpietosc {max(realne) - min(realne):.1f} pp)")


def raport_drugiego_wyboru(conn) -> None:
    """ZADANIE D — czy DRUGI (albo trzeci) typ modelu trafia częściej niż GŁÓWNY.

    `model_log` zapisuje wszystkie prawdopodobieństwa (1X2, Over/Under 2.5,
    BTTS/NIE) i pełny wynik, ale liczy trafność wyłącznie dla argmaksu. Ten
    raport porównuje pozycje #1/#2/#3 rankingu modelu (`ranking_rynkow`).

    PUŁAPKA: bazy 7 rynków są rozstrzelone o 31 pp (n=424, 26.08: "1" 43.9%,
    "X" 23.6%, "2" 32.5%, Over 2.5 55.0%, Under 2.5 45.0%, BTTS 52.6%).
    Rynek dwustronny wygrywa argmax po surowym prawdopodobieństwie SAMĄ
    definicją (jedna strona zawsze ≥50%) — dokładnie mechanizm `_pomijaj_btts`
    z `system_paper.py:42`. WERDYKT liczy się więc po PRZEWADZE nad bazą
    własnego rynku (`przewaga_nad_baza`), nie po surowej trafności — ta druga
    koronowałaby Over 2.5 za samą bazę, nie za wiedzę modelu. Naglowkowe
    "+Xpp" dla #1 jest SREDNIA po rynkach — tabela `rozklad_z_przewaga`
    pokazuje je osobno, bo usredniona liczba potrafi ukryc najczestszy
    rynek z przewaga UJEMNA (zmierzone 26.08: BTTS na #1, n=134, -3.3pp).
    """
    from footstats.core.ranking_rynkow import (
        policz_nierozliczalne,
        przewaga_nad_baza,
        ranking_rynkow,
        rozklad_z_przewaga,
    )

    print("\n=== DRUGI WYBÓR: czy pozycja #2/#3 bije #1? (model_log) ===")
    # Bez sklejania nazw kolumn f-stringiem (bandit B608) — patrz komentarz
    # w `raport_rynkow_golowych`. Kolumny sa tu wprost wypisane.
    wiersze = _licz(conn, """
        SELECT prob_home, prob_draw, prob_away, prob_over25, prob_btts, actual_result
        FROM model_log
        WHERE actual_result IS NOT NULL
    """)
    if not wiersze:
        print("  BRAK DANYCH — model_log nie ma jeszcze żadnego rozliczonego wiersza.")
        return

    # Ranking KAZDEGO wiersza liczymy RAZ i przekazujemy dalej — inaczej
    # kazda z funkcji nizej liczylaby go od nowa, mnozac ostrzezenia z
    # `oblicz_tip_correct` (3 nierozliczalne wiersze dawaly 147 linii
    # WARNING zamiast 21 przy jednym przejsciu po danych).
    rankingi = [ranking_rynkow(w) for w in wiersze]

    nierozliczalne_ogolem = policz_nierozliczalne(rankingi)
    if nierozliczalne_ogolem:
        print(f"  (pominięto {nierozliczalne_ogolem} z {len(wiersze)} wierszy —"
              f" wynik nierozliczalny: dogrywka/karne)")

    wyniki = {rank: przewaga_nad_baza(rankingi, rank) for rank in (1, 2, 3)}

    print(f"  {'pozycja':8} {'n':>5} {'trafność':>10} {'baza':>8} {'przewaga':>10}")
    for rank in (1, 2, 3):
        w = wyniki[rank]
        if not w["n"]:
            # DWIE rozne przyczyny n==0 — sklejenie ich w jeden komunikat
            # dawalo falszywa diagnoze (patrz docstring `przewaga_nad_baza`).
            print(f"  #{rank}       BRAK — {w['brak_pozycji']} wierszy bez {rank}. rynku,"
                  f" {w['nierozliczalne']} z nierozliczalnym wynikiem na tej pozycji")
            continue
        znacznik = " — mala proba" if w["n"] < PROG_MALA_PROBA else ""
        print(f"  #{rank}       {w['n']:5} {w['trafnosc']:9.1f}% {w['baza']:7.1f}%"
              f" {w['przewaga']:+9.1f}pp{znacznik}")

    rozklad = rozklad_z_przewaga(rankingi, rank=1)
    if rozklad:
        print("\n  rozkład rynków na pozycji #1 — n / trafność / baza / przewaga"
              " (stronniczość 2-way i jej realna wartość widać tutaj):")
        for poz in rozklad:
            znacznik = " — mala proba" if poz["n"] < PROG_MALA_PROBA else ""
            print(f"    {poz['rynek']:10} n={poz['n']:4}"
                  f"  trafność={poz['trafnosc']:5.1f}%  baza={poz['baza']:5.1f}%"
                  f"  przewaga={poz['przewaga']:+6.1f}pp{znacznik}")

    dostepne = {rank: w for rank, w in wyniki.items() if w["przewaga"] is not None}
    if not dostepne:
        print("\n  → brak rozliczalnych danych do werdyktu.")
        return

    if wyniki[1]["przewaga"] is None:
        # #1 nie ma czym wygrac — nie wolno mu tego doklejac domyslnie
        # (byla to dziura: `1 not in dostepne` liczylo sie jako zwycięstwo #1).
        najlepszy = max(dostepne, key=lambda rank: dostepne[rank]["przewaga"])
        print("\n  → #1 (typ główny) bez rozliczalnych danych na tej pozycji —"
              " brak podstawy do porównania.")
        print(f"  → spośród dostępnych pozycji najwyższą przewagę ma #{najlepszy}"
              f" ({dostepne[najlepszy]['przewaga']:+.1f}pp).")
        return

    najlepszy = max(dostepne, key=lambda rank: dostepne[rank]["przewaga"])
    if najlepszy == 1:
        print(f"\n  → WERDYKT: pozycja #1 (typ główny) ma najwyższą przewagę"
              f" ({wyniki[1]['przewaga']:+.1f}pp) — drugi/trzeci wybór jej NIE bije.")
    else:
        print(f"\n  → WERDYKT: pozycja #{najlepszy} BIJE typ główny — przewaga"
              f" {dostepne[najlepszy]['przewaga']:+.1f}pp vs #1 {wyniki[1]['przewaga']:+.1f}pp."
              f" Model wie więcej, niż pokazuje typ główny.")


def raport_przewagi_nad_kursem(conn) -> None:
    """TO JEST LICZBA, KTORA PRZESADZA O FLAGACH SELEKCJI (tabela `coupons`).

    Wszystkie pozostale raporty w tym pliku mierza przewage modelu nad WLASNA
    baza czestosci wynikow w probce (kalibracja, rozroznianie miedzy meczami).
    Ten mierzy cos innego i trudniejszego: czy bijemy CENE bukmachera. Model
    moze byc lepszy od „zgadywania po bazie” i wciaz systematycznie przeplacac
    wzgledem kursu — dopiero to drugie ma zwiazek z pieniedzmi (patrz
    `.claude/rules/wypuszczenie-pl.md`: dodatnia przewaga nad baza NIE
    oznacza zysku).

    Hipoteza zerowa: kupon wchodzi z prawdopodobienstwem `1/kurs` (z marza
    bukmachera). Test dokladny (Poisson-dwumianowy, `testy_przewagi.py`) —
    zero przyblizenia normalnego, bo pojedyncze rynki tu bywaja jednocyfrowe.
    """
    from footstats.core.testy_przewagi import test_przewagi

    print("\n=== PRZEWAGA NAD KURSEM BUKMACHERA (coupons, SINGLE, WON/LOST) ===")
    # Bez sklejania nazw kolumn f-stringiem (bandit B608) — jak wszedzie w tym pliku.
    wiersze = _licz(conn, """
        SELECT status, total_odds, stake_pln, payout_pln, legs_json
        FROM coupons
        WHERE status IN ('WON', 'LOST') AND kupon_type = 'SINGLE'
    """)
    if not wiersze:
        print("  BRAK DANYCH — brak rozliczonych kuponow SINGLE w `coupons`.")
        return

    wynik = test_przewagi(wiersze)
    rynki = wynik["rynki"]
    # DWIE ROZNE przyczyny pustego wyniku — sklejenie ich dawaloby falszywa
    # diagnoze (patrz zasady zadania S i `raport_drugiego_wyboru`).
    if wynik["pominieto_kurs"]:
        print(f"  pominieto {wynik['pominieto_kurs']} kupon(y) z kursem <= 1.0"
              " (dzielenie przez zero implikowanego prawdopodobienstwa)")
    if wynik["pominieto_legs"]:
        print(f"  pominieto {wynik['pominieto_legs']} kupon(y)"
              " z uszkodzonym/pustym legs_json")

    if not rynki:
        print("  WSZYSTKO ODFILTROWANE — zaden kupon nie mial poprawnego"
              " kursu/legs_json (a wiersze w bazie BYLY, patrz liczby wyzej).")
        return

    print(f"  {'rynek':12} {'n':>4} {'traf':>5} {'ocz.':>6} {'trafnosc':>9}"
          f" {'prog':>7} {'ROI':>8} {'p (1-str.)':>11}")
    posortowane = sorted(rynki.items(), key=lambda kv: kv[1]["n"], reverse=True)
    for rynek, dane in posortowane:
        trafnosc = 100.0 * dane["trafienia"] / dane["n"]
        prog = 100.0 * dane["oczekiwane"] / dane["n"]
        roi = f"{dane['roi']:+.1f}%" if dane["roi"] is not None else "—"
        print(f"  {rynek:12} {dane['n']:4} {dane['trafienia']:5} {dane['oczekiwane']:6.1f}"
              f" {trafnosc:8.1f}% {prog:6.1f}% {roi:>8} {dane['p_surowe']:11.4f}")

    najgorszy_rynek, najgorsze_dane = min(posortowane, key=lambda kv: kv[1]["p_surowe"])
    print(f"  korekta Sidaka na wybor najgorszego z {len(rynki)} rynkow:"
          f" {najgorszy_rynek} {najgorsze_dane['p_surowe']:.4f}"
          f" -> {najgorsze_dane['p_po_korekcie']:.4f}")
    print(f"  UWAGA: powyzsza korekta liczy sie na WYBOR NAJGORSZEGO z {len(rynki)}"
          " rynkow, nie na jeden z gory ustalony test — bez niej pojedynczy"
          " „istotny” wynik wsrod kilku to zwykly efekt wielokrotnego szukania.")
    print("  UWAGA: dodatnia przewaga nad BAZA (pozostale raporty w tym pliku)"
          " NIE oznacza zysku — dopiero pobicie KURSU bukmachera (ten raport)"
          " ma zwiazek z pieniedzmi.")


def raport_gotowosci(pred: dict, dziennik: dict | None = None) -> None:
    """Ile brakuje do werdyktu `porownaj_modele`.

    Liczy z WIĘKSZEJ z dwóch prób. `predictions` widzi wyłącznie mecze, które
    przeszły filtry wartości, więc samo z siebie każe czekać na dane, które
    już mamy w `model_log` (10 vs 23 rozliczonych dla poisson-dc na 13.08).
    """
    dziennik = dziennik or {}
    print("\n=== GOTOWOŚĆ DO WERDYKTU ===")
    for model in ("poisson-dc", "bzzoiro-ml"):
        n_pred = pred.get(model, {}).get("rozliczone", 0)
        n_dzien = dziennik.get(model, {}).get("rozliczone", 0)
        n = max(n_pred, n_dzien)
        zrodlo = "model_log" if n_dzien > n_pred else "predictions"
        brakuje = max(0, MIN_ROZLICZONYCH - n)
        stan = "gotowe" if not brakuje else f"brakuje {brakuje}"
        print(f"  {model:12} rozliczonych {n:4} / {MIN_ROZLICZONYCH} — {stan} ({zrodlo})")


def main() -> None:
    from footstats.utils.db import connect

    with connect() as conn:
        pred = raport_predykcji(conn)
        raport_lekcji(conn)
        raport_wzorcow(conn)
        dziennik = raport_dziennika(conn)
        raport_kalibracji_1x2(conn)
        raport_rynkow_golowych(conn)
        raport_remisow(conn)
        raport_drugiego_wyboru(conn)
        raport_przewagi_nad_kursem(conn)
        raport_gotowosci(pred, dziennik)


if __name__ == "__main__":
    main()
