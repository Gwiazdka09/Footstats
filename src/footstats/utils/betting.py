import logging
import re

log = logging.getLogger(__name__)

# Znaczniki dogrywki i karnych. Dopasowanie po CALYCH slowach — inaczej nazwa
# zawierajaca "pen" (np. "Openda") falszywie unieważnialaby wynik.
_DOGRYWKA = re.compile(r"(?<![a-z])(aet|a\.e\.t\.?|et|dogrywk\w*)(?![a-z])", re.IGNORECASE)
_KARNE = re.compile(r"(?<![a-z])(pens?|ap|karn\w*|k\.k\.)(?![a-z])", re.IGNORECASE)


def powod_nierozliczalny(actual_result) -> str | None:
    """Zwraca powod, dla ktorego wyniku NIE da sie uczciwie rozliczyc, albo None.

    Standardowe rynki (1X2, Over/Under, BTTS) rozliczaja sie PO 90 MINUTACH, a zapis
    w rodzaju "2-1aet" niesie wynik po dogrywce — regulaminowego w nim nie ma.

    Kuszace "skoro byla dogrywka, to po 90 minutach byl remis" jest ZAWODNE:
    w dwumeczu dogrywke wymusza remis w DWUMECZU, wiec sam mecz mogl skonczyc sie
    1-0. Zgadywanie dawaloby ciche przeklamania w statystykach modelu — a to
    wlasnie one sa jedynym produktem tego systemu.

    UWAGA: brak wyniku ("" / None) to NIE to samo. Tam po prostu jeszcze nie wiemy;
    tutaj wiemy i wiemy, ze sie nie da.
    """
    if actual_result is None:
        return None
    if isinstance(actual_result, (tuple, list)):
        return None                      # krotka to czyste bramki, bez adnotacji
    tekst = str(actual_result).strip()
    if not tekst:
        return None
    if _KARNE.search(tekst):
        return "karne"
    if _DOGRYWKA.search(tekst):
        return "dogrywka"
    return None


def oblicz_tip_correct(ai_tip: str, actual_result) -> int | None:
    """
    Oblicza czy typ był trafiony na podstawie wyniku meczu.
    Obsługuje formaty: str ("2-1"), tuple (2, 1) oraz list [2, 1].
    Opcjonalny sufiks wyniku połowy: "2-1;HT:1-0" — wymagany tylko przez
    rynki half-time (np. GG2H); pozostałe rynki parsują samo FT i działają
    identycznie z sufiksem lub bez niego.
    """
    if not actual_result:
        return None

    # NOWOŚĆ: Obsługa krotek i list (naprawa błędu AttributeError)
    if isinstance(actual_result, (tuple, list)):
        try:
            actual_result = f"{actual_result[0]}-{actual_result[1]}"
        except (IndexError, TypeError):
            return None

    actual_result = str(actual_result)
    tip  = (ai_tip or "").strip().upper()

    # Dogrywka/karne: wynik ISTNIEJE, ale nie da sie z niego uczciwie rozliczyc rynkow
    # 90-minutowych. Wczesniej zachowanie zalezalo od ZAPISU zrodla: "2-1aet" dawalo
    # None (limbo do czasu VOID po 10 dniach), a "2-1 (AET)" bylo rozliczane jako
    # wygrana gospodarza — mimo ze po 90 minutach mogl byc remis. Ten sam mecz,
    # dwa rozne werdykty. Teraz oba traktowane tak samo i GLOSNO.
    powod = powod_nierozliczalny(actual_result)
    if powod:
        log.warning("Wynik '%s' (%s) nie pozwala rozliczyc typu '%s' — "
                    "rynki 90-minutowe wymagaja wyniku regulaminowego",
                    actual_result, powod, ai_tip)
        return None

    # BetBuilder combo: "BB: 1 + Over 1.5" = KONIUNKCJA członów (wszystkie muszą trafić).
    # Bez tego oceniany byl tylko pierwszy pasujacy czlon -> przegrane combo jako WON.
    # Rekursja dostaje ORYGINALNY actual_result (z sufiksem HT) — człony typu GG2H
    # potrzebują go niezależnie od reszty kombinacji.
    if tip.startswith("BB:") or tip.startswith("BB "):
        czlony = [c.strip() for c in tip[3:].split("+") if c.strip()]
        if not czlony:
            return None
        wyniki = [oblicz_tip_correct(c, actual_result) for c in czlony]
        if any(w is None for w in wyniki):
            return None          # któryś człon nierozliczalny → całość nieznana
        return 1 if all(w == 1 for w in wyniki) else 0

    # Wydziel sufiks HT (";HT:hh-ha") — reszta (FT) parsowana jak dotychczas.
    ht_home = ht_away = None
    if ";HT:" in actual_result:
        actual_result, ht_part = actual_result.split(";HT:", 1)
        ht_clean = ht_part.strip().replace("–", "-")
        ht_parts = ht_clean.split("-")
        try:
            ht_home = int(ht_parts[0].strip())
            ht_away = int(ht_parts[1].strip())
        except (ValueError, IndexError):
            ht_home = ht_away = None

    # Upewniamy się, że res jest stringiem przed strip()
    res = str(actual_result).strip()

    # Spróbuj sparsować wynik bramkowy
    home_g = away_g = None
    if "-" in res and res not in ("1", "X", "2"):
        # Usuń informacje o karnych lub dogrywce np. "2-1 (AET)"
        res_clean = re.sub(r"\(.*?\)", "", res).strip()
        parts = res_clean.replace("–", "-").split("-")
        try:
            home_g = int(parts[0].strip())
            away_g = int(parts[1].strip())
        except (ValueError, IndexError):
            pass

    # Wyznacz wynik 1/X/2 z bramek
    if home_g is not None and away_g is not None:
        if home_g > away_g:
            match_result = "1"
        elif home_g == away_g:
            match_result = "X"
        else:
            match_result = "2"
        total_goals = home_g + away_g
        btts        = home_g > 0 and away_g > 0
    elif res in ("1", "X", "2"):
        match_result = res
        total_goals  = None
        btts         = None
    else:
        return None

    # Sprawdź typ
    if tip in ("1", "X", "2"):
        return 1 if match_result == tip else 0

    # "[wynik] & gol w każdej połowie" (GG2H) — wynik 1X2 ORAZ ≥1 gol w 1. poł.
    # ORAZ ≥1 gol w 2. poł. (semantyka Superbet). Wymaga danych HT — brak → None.
    gg2h = re.match(r"^(1|X|2)\s*&\s*GG2H$", tip)
    if gg2h:
        if match_result is None or ht_home is None or ht_away is None:
            return None
        if home_g is None or away_g is None:
            return None
        if match_result != gg2h.group(1):
            return 0
        ht_total = ht_home + ht_away
        sh_total = (home_g + away_g) - ht_total
        return 1 if (ht_total >= 1 and sh_total >= 1) else 0

    if tip == "1X":
        return 1 if match_result in ("1", "X") else 0

    if tip == "X2":
        return 1 if match_result in ("X", "2") else 0

    if tip == "12":
        return 1 if match_result in ("1", "2") else 0

    # Gole drużyny: "1 OVER 0.5" = gospodarz strzeli >0.5 (1+) goli, "2 UNDER 1.5" = gość <1.5 itd.
    team_goals = re.match(r"^(1|2)\s+(OVER|UNDER)\s+(\d+\.\d+|\d+)$", tip)
    if team_goals:
        if home_g is None or away_g is None:
            return None
        side, direction, val = team_goals.group(1), team_goals.group(2), float(team_goals.group(3))
        goals = home_g if side == "1" else away_g
        if direction == "OVER":
            return 1 if goals > val else 0
        return 1 if goals < val else 0

    # Gole druzyny w zapisie POLSKIM: "GOSPODARZ STRZELI 0.5+" / "GOŚĆ STRZELI 1.5+".
    # Tak generuje je `bet_builder.py` (linie 150-154) — a rozliczanie znalo tylko
    # zapis "GOSPODARZ OVER 0.5" nizej. Dwa slowniki, obslugiwany jeden, wiec typ
    # na ten rynek NIGDY nie dostawal `tip_correct`: nie liczyl sie jako rozliczony,
    # nie wchodzil do statystyk trafnosci i NIE STAWAL SIE LEKCJA w petli uczenia.
    # W bazie lezala predykcja #8 z gotowym wynikiem "2-0" i pustym tip_correct.
    #
    # "strzeli 0.5+" = WIECEJ NIZ 0.5 gola, czyli co najmniej jeden — identycznie
    # jak "OVER 0.5". Zapis z plusem to konwencja bukmacherska.
    # Sufiks "(Szansa: 78%)" doklejany przez bet_builder jest odcinany.
    tip_bez_nawiasu = re.sub(r"\(.*?\)", "", tip).strip()
    team_pl = re.match(
        r"^(GOSPODARZ|GOŚCIE|GOSCIE|GOŚĆ|GOSC)\s+STRZEL\w*\s+(\d+\.\d+|\d+)\+?$",
        tip_bez_nawiasu,
    )
    if team_pl:
        if home_g is None or away_g is None:
            return None
        strona, val = team_pl.group(1), float(team_pl.group(2))
        goals = home_g if strona == "GOSPODARZ" else away_g
        return 1 if goals > val else 0

    # Gole druzyny nazwane (BetBuilder): "GOSPODARZ OVER 0.5" / "GOŚĆ OVER 1.5".
    # MUSI byc przed generycznym Over/Under (ten liczy TOTAL, nie gole druzyny).
    team_named = re.match(r"^(GOSPODARZ|GOŚĆ|GOSC)\s+(OVER|UNDER)\s+(\d+\.\d+|\d+)$", tip)
    if team_named:
        if home_g is None or away_g is None:
            return None
        side, direction, val = team_named.group(1), team_named.group(2), float(team_named.group(3))
        goals = home_g if side == "GOSPODARZ" else away_g
        if direction == "OVER":
            return 1 if goals > val else 0
        return 1 if goals < val else 0

    # Over/Under
    if "OVER" in tip or "UNDER" in tip:
        if total_goals is None: return None
        try:
            val_match = re.search(r"(\d+\.\d+|\d+)", tip)
            if not val_match: return None
            val = float(val_match.group(1))
            if "OVER" in tip:
                return 1 if total_goals > val else 0
            else:
                return 1 if total_goals < val else 0
        except (AttributeError, ValueError):
            return None

    # BTTS
    if tip == "BTTS":
        if btts is None: return None
        return 1 if btts else 0
    if tip in ("BTTS NO", "NO BTTS", "BTTS NIE", "NIE BTTS"):
        if btts is None: return None
        return 1 if not btts else 0

    # Handicap europejski: "1 (-1.5)" / "2 (+1.5)" — wygrana po doliczeniu handicapu,
    # remis po korekcie = przegrana (wariant europejski, bez zwrotu).
    hcp = re.match(r"^(1|2)\s*\(\s*([+-]?\d+(?:\.\d+)?)\s*\)$", tip)
    if hcp:
        if home_g is None or away_g is None:
            return None
        side, line = hcp.group(1), float(hcp.group(2))
        if side == "1":
            return 1 if (home_g + line) > away_g else 0
        return 1 if (away_g + line) > home_g else 0

    # Nazwane handicapy z BetBuilder (betbuilder_rules._PREDYKATY) — by combo "BB: ..." z nimi
    # bylo rozliczalne. Semantyka 1:1 z regulami: -1 Gospodarz = wygrana o 2+, +1 Gosc = h-a<=1.
    if tip == "HANDICAP -1 GOSPODARZ":
        if home_g is None or away_g is None:
            return None
        return 1 if (home_g - away_g) >= 2 else 0
    if tip == "HANDICAP +1 GOŚĆ":
        if home_g is None or away_g is None:
            return None
        return 1 if (away_g + 1) >= home_g else 0

    # Parzysta / nieparzysta liczba goli (0 = parzysta)
    if tip in ("PARZYSTE", "EVEN"):
        if total_goals is None: return None
        return 1 if total_goals % 2 == 0 else 0
    if tip in ("NIEPARZYSTE", "ODD"):
        if total_goals is None: return None
        return 1 if total_goals % 2 == 1 else 0

    # Dokładny wynik: "WYNIK 2:1" lub "2:1" — bramki dom:gość muszą się zgadzać dokładnie.
    cs = re.match(r"^(?:WYNIK\s+)?(\d+)\s*:\s*(\d+)$", tip)
    if cs:
        if home_g is None or away_g is None:
            return None
        return 1 if (home_g == int(cs.group(1)) and away_g == int(cs.group(2))) else 0

    # Multigoal: "MULTIGOAL 2-3" — łączna liczba goli w przedziale [lo, hi] włącznie.
    mg = re.match(r"^MULTIGOAL\s+(\d+)\s*-\s*(\d+)$", tip)
    if mg:
        if total_goals is None:
            return None
        lo, hi = int(mg.group(1)), int(mg.group(2))
        return 1 if lo <= total_goals <= hi else 0

    # Rozwlekły zapis 1X2 z opisem słownym: "2 (wygrana gościa)", "1 (wygrana
    # gospodarza)", "X (remis)" — to samo co samo "1"/"X"/"2", tylko ubrane w
    # slownictwo modelu jezykowego. Dokladny wiersz z produkcji: predykcja #249,
    # typ "2 (wygrana gościa)" + wynik "0-3", zapisana z tip_correct=NULL na
    # zawsze (patrz `uzupelnij_tip_correct` w core/backtest.py).
    #
    # Umieszczone celowo na SAMYM KONCU, po wszystkich bardziej specyficznych
    # formatach z nawiasem (m.in. handicap europejski "1 (-1.5)" wyzej) — dzieki
    # temu regula jest wazka i nie przechwytuje niczego, co juz ma wlasna,
    # bardziej szczegolowa obsluge.
    opisowy = re.match(r"^([1X2])\s*\(.*\)$", tip)
    if opisowy:
        return 1 if match_result == opisowy.group(1) else 0

    return None
