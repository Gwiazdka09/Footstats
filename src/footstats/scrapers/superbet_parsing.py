"""
superbet_parsing.py — czyste parsery kuponów Superbet (bez Playwright).

Wydzielone z superbet.py (god-moduł 1128 linii) — funkcje transformujące
dane (dict/str/list → dict), niezależne od `page`/DOM, więc testowalne w izolacji.
Scrapery Playwright (zaloguj/pobierz_*) zostają w superbet.py i wołają te helpery.
"""
from __future__ import annotations

import json
import re
from datetime import datetime


def _parsuj_json_api(data, nick: str = "?") -> list:
    """Parsuje odpowiedź JSON API — obsługuje format ticket oraz inne struktury."""
    if isinstance(data, dict) and 'ticketId' in data:
        k = _parsuj_ticket(data, nick)
        return [k] if k else []

    kupony = []
    if isinstance(data, list):
        for item in data:
            k = _parsuj_item_api(item)
            if k:
                kupony.append(k)
    elif isinstance(data, dict):
        for key in ['data', 'items', 'results', 'coupons', 'tickets',
                    'bets', 'content', 'feed', 'posts', 'picks']:
            if key in data and isinstance(data[key], list):
                for item in data[key]:
                    k = _parsuj_item_api(item)
                    if k:
                        kupony.append(k)
    return kupony


def _parsuj_ticket(data: dict, nick: str = "?") -> dict | None:
    """Parsuje odpowiedź Superbet Ticket Presentation API."""
    ticket_id = data.get('ticketId', '')

    kurs_laczny = None
    for key in ['coefficient', 'initialCoefficient']:
        if key in data:
            try:
                k = float(data[key])
                if k > 1.0:
                    kurs_laczny = k
                    break
            except (ValueError, TypeError):
                pass

    # Stawka
    stawka = None
    payment = data.get('payment', {})
    if isinstance(payment, dict):
        for k in ['amount', 'value', 'stake', 'betAmount']:
            if k in payment:
                try:
                    stawka = float(payment[k])
                    break
                except (ValueError, TypeError):
                    pass
    elif isinstance(payment, (int, float)):
        stawka = float(payment)

    # Zdarzenia
    zdarzenia = []
    for ev in data.get('events', []):
        if not isinstance(ev, dict):
            continue
        # Nazwa meczu
        mecz = (ev.get('name') or ev.get('eventName') or
                f"{ev.get('homeTeamName', '')} - {ev.get('awayTeamName', '')}").strip(' -')
        # Typ zakładu
        typ = (ev.get('marketName') or ev.get('betTypeName') or
               ev.get('oddName') or ev.get('betName') or
               ev.get('selectionName') or '?')
        # Kurs per zdarzenie
        kurs_ev = None
        for kk in ['coefficient', 'odds', 'price', 'oddValue']:
            if kk in ev:
                try:
                    kurs_ev = float(ev[kk])
                    break
                except (ValueError, TypeError):
                    pass
        zdarzenia.append({
            'mecz': str(mecz)[:80] or '?',
            'typ':  str(typ)[:80],
            'kurs': kurs_ev,
            'betbuilder': _czy_betbuilder(str(typ)),
        })

    if not zdarzenia and not kurs_laczny:
        return None

    return {
        'nick':       nick,
        'ticket_id':  ticket_id,
        'kurs_laczny': kurs_laczny,
        'stawka':     stawka,
        'zdarzenia':  zdarzenia,
        'linie_raw':  [],
        'tresc':      json.dumps(data, ensure_ascii=False)[:600],
        'zrodlo':     'superbet_ticket_api',
        'pobrano':    datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _parsuj_item_api(item) -> dict | None:
    """Parsuje element z ogólnej listy API (nie-ticket format)."""
    if not isinstance(item, dict):
        return None

    nick = "?"
    for path in [
        ['username'], ['nick'], ['login'], ['name'],
        ['user', 'username'], ['user', 'nick'], ['user', 'login'],
        ['author', 'username'], ['author', 'nick'],
        ['tipster', 'username'], ['tipster', 'nick'],
    ]:
        try:
            v = item
            for k in path:
                v = v[k]
            if isinstance(v, str) and v:
                nick = v[:40]
                break
        except (KeyError, TypeError):
            pass

    kurs_laczny = None
    for key in ['totalOdds', 'total_odds', 'odds', 'kurs', 'rate', 'totalRate']:
        if key in item:
            try:
                kurs_laczny = float(item[key])
                break
            except (ValueError, TypeError):
                pass

    zdarzenia = []
    for key in ['selections', 'events', 'bets', 'picks', 'legs', 'items']:
        if key in item and isinstance(item[key], list):
            for sel in item[key]:
                if not isinstance(sel, dict):
                    continue
                mecz = (sel.get('eventName') or sel.get('event') or
                        sel.get('match') or sel.get('name') or '?')
                typ  = (sel.get('marketName') or sel.get('market') or
                        sel.get('pick') or sel.get('selection') or '?')
                kurs = None
                for kk in ['odds', 'price', 'rate', 'kurs', 'coefficient']:
                    if kk in sel:
                        try:
                            kurs = float(sel[kk])
                            break
                        except (ValueError, TypeError):
                            pass
                zdarzenia.append({
                    'mecz': str(mecz)[:80],
                    'typ':  str(typ)[:80],
                    'kurs': kurs,
                    'betbuilder': _czy_betbuilder(str(typ)),
                })
            break

    if nick == "?" and not zdarzenia and not kurs_laczny:
        return None

    return {
        'nick':        nick,
        'kurs_laczny': kurs_laczny,
        'stawka':      None,
        'zdarzenia':   zdarzenia,
        'linie_raw':   [],
        'tresc':       json.dumps(item, ensure_ascii=False)[:600],
        'zrodlo':      'superbet_api',
        'pobrano':     datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


_SLOWA_MECZ_NIE = [
    "gol", "polowa", "połowa", "karta", "rzut", "strzal", "strzał",
    "faul", "corner", "liczba", "przedzial", "przedział", "powyzej",
    "powyżej", "ponizej", "poniżej", "wynik", "mecz:", "oba",
]


def _czy_linia_to_mecz(linia: str) -> bool:
    """True jeśli linia wygląda jak 'Druzyna A - Druzyna B', nie jak typ BetBuilder."""
    if " - " not in linia and " – " not in linia:
        return False
    czesci = re.split(r' [-–] ', linia, maxsplit=1)
    if len(czesci) < 2:
        return False
    lewa, prawa = czesci[0].strip(), czesci[1].strip()
    # Oba człony muszą być >= 3 znaki i zaczynać się wielką literą
    if len(lewa) < 3 or len(prawa) < 3:
        return False
    if not lewa[0].isupper() or not prawa[0].isupper():
        return False
    # Nie może zawierać słów kluczowych typów
    linia_lower = linia.lower()
    if any(s in linia_lower for s in _SLOWA_MECZ_NIE):
        return False
    # Prawa strona nie może być samą liczbą (np. "1-3" to zakres, nie drużyna)
    if re.match(r'^\d+[-–]\d+$', prawa.strip()):
        return False
    return True


def _parsuj_zdarzenia(linie: list[str]) -> list[dict]:
    """
    Wyciąga listę zdarzeń z linii tekstowych kuponu.
    Obsługuje: standardowe typy (1/X/2, Over, BTTS) oraz BetBuilder.
    """
    zdarzenia = []

    # Wzorzec kursu per zdarzenie: liczba >= 1.01
    kurs_re = re.compile(r'\b(\d+[.,]\d{2})\b')

    i = 0
    while i < len(linie):
        linia = linie[i]

        # Pomijaj linie które są nagłówkami lub meta-danymi
        if any(x in linia.lower() for x in
               ["stawka", "kurs", "wygrana", "za ", "obserwu", "kupony",
                "analizy", "statystyki", "zainspirowani", "srednia"]):
            i += 1
            continue

        is_mecz = _czy_linia_to_mecz(linia)

        if is_mecz:
            mecz = linia.strip()
            typ  = ""
            kurs = None

            # Następna(e) linie mogą być typem i kursem
            if i + 1 < len(linie):
                nastepna = linie[i + 1]
                # Sprawdź czy to typ zakładu (nie mecz, nie gołe metadane)
                if not _czy_linia_to_mecz(nastepna):
                    typ = nastepna.strip()
                    i += 1

                    # Kurs może być w tej samej linii lub kolejnej
                    m_kurs = kurs_re.search(typ)
                    if m_kurs:
                        try:
                            k = float(m_kurs.group(1).replace(",", "."))
                            if 1.01 < k < 100:
                                kurs = k
                        except ValueError:
                            pass
                    elif i + 1 < len(linie):
                        m_kurs = kurs_re.search(linie[i + 1])
                        if m_kurs:
                            try:
                                k = float(m_kurs.group(1).replace(",", "."))
                                if 1.01 < k < 100:
                                    kurs = k
                                    i += 1
                            except ValueError:
                                pass

            zdarzenia.append({
                "mecz": mecz,
                "typ":  typ,
                "kurs": kurs,
                "betbuilder": _czy_betbuilder(typ),
            })

        i += 1

    return zdarzenia


def _czy_betbuilder(typ: str) -> bool:
    """Wykrywa czy typ to BetBuilder (kombinacja z jednego meczu)."""
    slowa_bb = [
        "przedział", "przedzial", "polowa", "połowa", "karta",
        "rzut rożny", "strzal", "strzał", "faul", "corner",
        "liczba goli", "gole w", "strzelec", "asyst",
    ]
    typ_lower = typ.lower()
    return any(s in typ_lower for s in slowa_bb)
