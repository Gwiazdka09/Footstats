"""Czas meczu: moment rozpoczecia i ocena, czy mecz juz sie zaczal.

Wspolne dla kreatora kuponu i zakladki Analizy meczow.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

_log = logging.getLogger(__name__)


# Statusy, przy ktorych zrodlo mowi WPROST, ze meczu juz nie ma po co typowac.
# Lista jest blokujaca, nie dopuszczajaca: status nieznany NIE wyklucza meczu,
# tylko oddaje decyzje zegarowi. Odwrotnie — allowlista — oprozniłaby kreator
# w dniu, w ktorym dostawca zmieni slownik, i nikt by nie zauwazyl dlaczego.
STATUSY_ROZPOCZETE = frozenset({
    "inprogress", "in_progress", "live", "playing", "halftime", "ht",
    "finished", "ft", "ended", "aet", "pen", "afterpen",
    "cancelled", "canceled", "postponed", "abandoned", "suspended", "awarded",
})


def moment_meczu(m: dict) -> datetime | None:
    """Poczatek meczu jako moment ZE STREFA (UTC). None gdy nie da sie odczytac.

    Pole `godzina` NIE MA jednej konwencji w tym projekcie: `api_football`
    i `football_data` dopisuja do niej " UTC", `bzzoiro` i `terminarz` oddaja
    goly wycinek ISO. Poprzednia wersja parsowala to jednym `strptime`
    z `"%H:%M"`, wiec wiersze z sufiksem rzucaly `ValueError` i wypadaly CICHO —
    kreator gubil cale zrodla, a lista dalej wygladala poprawnie.

    `data_full` (pelne ISO, czesto z przesunieciem strefy) jest wiarygodniejsze
    i dlatego idzie pierwsze. Gdy zostaje sama `data`+`godzina` bez strefy,
    przyjmujemy UTC — i to jest ZALOZENIE, nie fakt: `bzzoiro.py` tnie
    `event_date` bez normalizacji, a jego przesuniecie nie jest w kodzie nigdzie
    potwierdzone. Dlatego zegar NIE jest tu jedynym zabezpieczeniem i pracuje
    razem z `STATUSY_ROZPOCZETE`.
    """
    pelna = str(m.get("data_full") or "").strip()
    data = str(m.get("data") or "").strip()
    godzina = str(m.get("godzina") or "").strip()
    if godzina.upper().endswith("UTC"):
        godzina = godzina[:-3].strip()
    godzina = godzina[-5:] if len(godzina) > 5 else godzina

    try:
        if pelna:
            dt = datetime.fromisoformat(pelna.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        if data and godzina:
            return datetime.strptime(f"{data} {godzina}", "%Y-%m-%d %H:%M").replace(
                tzinfo=timezone.utc)
    except (ValueError, TypeError):
        # NIE cisza. Mecz bez czytelnej daty wypada z kreatora, a wlasnie tak
        # znikaly cale zrodla: `strptime` dlawilo sie sufiksem " UTC", `except`
        # polykalo blad i lista dalej wygladala poprawnie.
        _log.warning("Nieczytelna data meczu id=%s: data_full=%r data=%r godzina=%r",
                     m.get("id"), pelna, data, m.get("godzina"))
    return None


def juz_sie_zaczal(m: dict, teraz: datetime) -> bool:
    """Czy mecz odpadl z typowania. Status jest wazniejszy niz zegar.

    Status pochodzi od dostawcy i jest stwierdzeniem faktu; godzina wymaga
    zalozenia o strefie. Gdy oba sa dostepne, wystarczy jedno, zeby wykluczyc.
    """
    if str(m.get("status") or "").strip().lower().replace(" ", "") in STATUSY_ROZPOCZETE:
        return True
    moment = moment_meczu(m)
    return moment is not None and moment <= teraz
