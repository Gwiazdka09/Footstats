import re

def oblicz_tip_correct(ai_tip: str, actual_result) -> int | None:
    """
    Oblicza czy typ był trafiony na podstawie wyniku meczu.
    Obsługuje formaty: str ("2-1"), tuple (2, 1) oraz list [2, 1].
    """
    if not actual_result:
        return None

    # NOWOŚĆ: Obsługa krotek i list (naprawa błędu AttributeError)
    if isinstance(actual_result, (tuple, list)):
        try:
            actual_result = f"{actual_result[0]}-{actual_result[1]}"
        except (IndexError, TypeError):
            return None

    tip  = (ai_tip or "").strip().upper()

    # BetBuilder combo: "BB: 1 + Over 1.5" = KONIUNKCJA członów (wszystkie muszą trafić).
    # Bez tego oceniany byl tylko pierwszy pasujacy czlon -> przegrane combo jako WON.
    if tip.startswith("BB:") or tip.startswith("BB "):
        czlony = [c.strip() for c in tip[3:].split("+") if c.strip()]
        if not czlony:
            return None
        wyniki = [oblicz_tip_correct(c, actual_result) for c in czlony]
        if any(w is None for w in wyniki):
            return None          # któryś człon nierozliczalny → całość nieznana
        return 1 if all(w == 1 for w in wyniki) else 0

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

    return None