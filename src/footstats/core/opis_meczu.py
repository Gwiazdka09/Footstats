"""core/opis_meczu.py — opis meczu dla właściciela: karta liczb + opis LLM.

Spec: docs/superpowers/specs/2026-10-23-opisy-meczow-admin-design.md.

Dwa kroki, celowo rozdzielone:
  1. `zbuduj_karte` — DETERMINISTYCZNA karta liczb z własnych danych (czysty Poisson,
     Bzzoiro-ML, rynek bez marży, forma z historii, statystyki drużyn). Bez LLM.
  2. `opisz` — Groq dostaje WYŁĄCZNIE kartę i ma ją zinterpretować. Prompt zabrania
     dopisywania faktów spoza karty i rekomendacji zakładu. Gdy LLM padnie, zwracamy
     `None`, a karta i tak trafia do GUI.

Wszystkie prawdopodobieństwa w karcie są w PROCENTACH (0-100, jedno miejsce po
przecinku) — tak jak `predict_match` i Bzzoiro. Wyjątek: `rynek_bez_marzy` zwraca
ułamki (suma = 1), a kartę przelicza `zbuduj_karte`.

Zależności (zbiór historyczny, event Bzzoiro, funkcja LLM) są wstrzykiwane — testy
nie potrzebują sieci. Ciężkie importy (pandas, poisson) są leniwe, żeby montowanie
routera nie zmieniało czasu ani pamięci startu API.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Callable

from footstats.ai.client import zapytaj_ai
from footstats.utils.normalize import normalize_team_name

if TYPE_CHECKING:
    import pandas as pd

log = logging.getLogger(__name__)

# Linie goli w karcie — jak w pomiarze z 23.10 (`scripts/stan_uczenia._LINIE_GOLI`).
_LINIE_GOLI: tuple[float, ...] = (0.5, 1.5, 2.5, 3.5, 4.5)

# Różnica model - rynek, od której prompt każe o niej mówić (spec: >= 5 pp).
_PROG_ROZNICY_PP = 5.0

# Ile ostatnich meczów liczy się do średniej goli (spec: 10).
_OKNO_SREDNIEJ = 10

_MAX_TOKENS_OPISU = 700
_TTL_CACHE_S = 6 * 3600
_MAX_WPISOW_CACHE = 200

# Uwagi dopisywane do KAŻDEJ karty — to są ograniczenia modelu, które LLM ma
# uwzględnić w sekcji „niepewność”, a właściciel widzieć obok liczb.
UWAGI_STALE: tuple[str, ...] = (
    "Czysty Poisson zaniża sumę goli o ok. 0,3 gola na mecz (próba odkrywcza z 23.10,"
    " w trakcie replikacji) — linie Over mogą być zaniżone, a Under zawyżone.",
    "Model nie bije rynku (zmierzone: 39 z 39 lig) — liczby opisują, czego model się"
    " spodziewa, a nie wskazują wartościowego zakładu.",
)


# ── Rynek bez marży ─────────────────────────────────────────────────────────

def _kurs(wartosc: Any) -> float | None:
    """Kurs dziesiętny > 1.0 albo None (brak, tekst, NaN, nielogiczna wartość)."""
    try:
        kurs = float(wartosc)
    except (TypeError, ValueError):
        return None
    if math.isnan(kurs) or math.isinf(kurs) or kurs <= 1.0:
        return None
    return kurs


def _bez_marzy(kursy: list[float | None]) -> list[float] | None:
    """Proporcjonalne zdjęcie marży: (1/kurs) znormalizowane do sumy 1.

    None, gdy którykolwiek kurs rynku brakuje — niepełny rynek (np. 1X2 bez remisu)
    zawyżyłby pozostałe wyniki.
    """
    if any(k is None for k in kursy):
        return None
    odwrotnosci = [1.0 / k for k in kursy if k is not None]
    suma = sum(odwrotnosci)
    return [o / suma for o in odwrotnosci]


def rynek_bez_marzy(odds: dict[str, Any] | None) -> dict[str, float] | None:
    """Prawdopodobieństwa rynku po zdjęciu marży, jako UŁAMKI (suma rynku = 1).

    `odds` to blok `odds` eventu Bzzoiro (`home/draw/away/over_2_5/under_2_5`).
    Klucze wyniku: `p1`, `px`, `p2` (1X2) oraz `over25`, `under25` — tylko dla
    rynków, które mają komplet kursów. None, gdy nie ma żadnego kompletu.
    """
    if not odds:
        return None
    wynik: dict[str, float] = {}
    x12 = _bez_marzy([_kurs(odds.get(k)) for k in ("home", "draw", "away")])
    if x12:
        wynik.update(zip(("p1", "px", "p2"), x12))
    ou = _bez_marzy([_kurs(odds.get("over_2_5")), _kurs(odds.get("under_2_5"))])
    if ou:
        wynik.update(zip(("over25", "under25"), ou))
    return wynik or None


# ── Dopasowanie eventu Bzzoiro ──────────────────────────────────────────────

def dopasuj_event(
    events: list[dict[str, Any]] | None, home: str, away: str, data: str | None = None,
) -> dict[str, Any] | None:
    """Event `predykcje_tygodnia` dla pary (gospodarz, gość), po znormalizowanych nazwach.

    Gdy para występuje kilka razy, wygrywa ta z datą równą `data`; bez daty (lub bez
    trafienia w datę) pierwsza pasująca. Odwrócona para (gość-gospodarz) NIE pasuje.
    """
    h, a = normalize_team_name(home), normalize_team_name(away)
    pasujace = [
        e for e in (events or [])
        if normalize_team_name(e.get("gosp") or "") == h
        and normalize_team_name(e.get("gosc") or "") == a
    ]
    if not pasujace:
        return None
    if data:
        for e in pasujace:
            if e.get("data") == data:
                return e
    return pasujace[0]


# ── Forma z historii ────────────────────────────────────────────────────────

def forma(df: pd.DataFrame | None, druzyna: str, n: int = 5) -> dict[str, Any] | None:
    """Ostatnie `n` meczów drużyny (najnowszy pierwszy) + średnie gole z ostatnich 10.

    Wynik zawsze z perspektywy badanej drużyny. Nazwa jest tłumaczona na zapis
    z historii tą samą funkcją co w `predict_match` ("Stoke City" -> "Stoke").
    None, gdy brak zbioru albo drużyna nie ma w nim rozegranych meczów.
    Mecze bez wyniku (NaN) są pomijane.
    """
    import pandas as pd

    from footstats.core.poisson import _kanoniczne_nazwy

    wymagane = {"data", "gospodarz", "goscie", "gole_g", "gole_a"}
    if df is None or df.empty or not wymagane <= set(df.columns):
        return None

    nazwa, _ = _kanoniczne_nazwy(df, druzyna, druzyna)
    mecze = df[(df["gospodarz"] == nazwa) | (df["goscie"] == nazwa)]
    mecze = mecze.dropna(subset=["gole_g", "gole_a"]).reset_index(drop=True)
    daty = pd.to_datetime(mecze["data"], errors="coerce").dropna()
    if daty.empty:
        return None
    daty = daty.sort_values(ascending=False, kind="stable")
    mecze = mecze.loc[daty.index]

    wiersze: list[dict[str, Any]] = []
    strzelone: list[int] = []
    stracone: list[int] = []
    for idx, r in mecze.head(_OKNO_SREDNIEJ).iterrows():
        dom = r["gospodarz"] == nazwa
        gf, ga = (int(r["gole_g"]), int(r["gole_a"])) if dom else (int(r["gole_a"]), int(r["gole_g"]))
        strzelone.append(gf)
        stracone.append(ga)
        if len(wiersze) < n:
            wiersze.append({
                "data": daty[idx].strftime("%Y-%m-%d"),
                "rywal": r["goscie"] if dom else r["gospodarz"],
                "wynik": f"{gf}:{ga}",
                "miejsce": "dom" if dom else "wyjazd",
                "rezultat": "W" if gf > ga else ("R" if gf == ga else "P"),
            })

    k = len(strzelone)
    return {
        "ostatnie": wiersze,
        "gole_strzelone_sr10": round(sum(strzelone) / k, 2),
        "gole_stracone_sr10": round(sum(stracone) / k, 2),
        "mecze_w_sredniej": k,
    }


# ── Karta liczb ─────────────────────────────────────────────────────────────

def _pct(ulamek: float) -> float:
    return round(ulamek * 100.0, 1)


def _poisson(home: str, away: str, df: pd.DataFrame | None) -> tuple[dict[str, Any] | None, str | None]:
    """(blok czystego Poissona, powód braku). Dokładnie jedno z nich jest None."""
    if df is None:
        return None, "brak zbioru historycznego meczów (Poisson niedostępny)"

    from footstats.core.poisson import predict_match, prob_linii_goli

    try:
        # Czysty Poisson: bez heurystyk/H2H/fortecy (to obiekty pipeline'u, nie karty).
        # Domyślne stage="REGULAR_SEASON" — jak w `quick_picks`.
        wynik = predict_match(home, away, df)
    except Exception as e:  # noqa: BLE001 — karta ma przeżyć awarię jednego ramienia
        log.warning("opis_meczu: predict_match(%s, %s) nieudany: %s: %s",
                    home, away, type(e).__name__, e)
        return None, f"błąd obliczeń Poissona ({type(e).__name__})"
    if not wynik:
        return None, ("predict_match: brak wyniku (za mało meczów pary w historii"
                      " albo nazwy nieznane w zbiorze)")

    lh, la = wynik["lambda_g"], wynik["lambda_a"]
    linie = {str(linia): _pct(p) for linia, p in prob_linii_goli(lh, la, _LINIE_GOLI).items()}
    return {
        "lambda_home": lh,
        "lambda_away": la,
        "p1": wynik["p_wygrana"],
        "px": wynik["p_remis"],
        "p2": wynik["p_przegrana"],
        "btts": wynik["btts"],
        "over25": linie["2.5"],
        "linie": linie,
    }, None


def _bzzoiro(bzz: dict[str, Any] | None) -> dict[str, float | None] | None:
    if not bzz:
        return None
    from footstats.scrapers.bzzoiro import _bzz_parse_prob

    parsed = _bzz_parse_prob(bzz.get("pred_ml") or {})
    if parsed is None:
        return None
    pw, pr, pp, bt, o25 = parsed
    # `predykcje_tygodnia` wstawia 0 za brakujące Over/BTTS — to brak, nie „0%”.
    return {"p1": pw, "px": pr, "p2": pp, "over25": o25 or None, "btts": bt or None}


def _rynek(bzz: dict[str, Any] | None) -> dict[str, float] | None:
    rynek = rynek_bez_marzy((bzz or {}).get("odds"))
    return {k: _pct(v) for k, v in rynek.items()} if rynek else None


def _statystyki(karta_druzyn: dict[str, Any] | None) -> dict[str, Any] | None:
    """Statystyki drużyn z `build_match_card` (gf_pg, ga_pg, rating, strzelcy).

    Kontuzje i składy z tej karty CELOWO nie wchodzą — prompt zabrania ich używać.
    """
    if not karta_druzyn:
        return None

    def blok(klucz: str) -> dict[str, Any] | None:
        b = karta_druzyn.get(klucz) or {}
        if not b.get("matches"):
            return None
        return {k: b.get(k) for k in ("matches", "gf_pg", "ga_pg", "rating")}

    def strzelcy(klucz: str) -> list[dict[str, Any]]:
        return [{"name": s.get("name"), "goal_share": s.get("goal_share")}
                for s in karta_druzyn.get(klucz) or []]

    home, away = blok("home_stats"), blok("away_stats")
    sh, sa = strzelcy("top_scorers_home"), strzelcy("top_scorers_away")
    if not (home or away or sh or sa):
        return None
    return {"home": home, "away": away, "strzelcy_home": sh, "strzelcy_away": sa}


def zbuduj_karte(
    home: str,
    away: str,
    liga: str | None,
    data: str | None,
    df: pd.DataFrame | None,
    bzz: dict[str, Any] | None,
    karta_druzyn: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Karta liczb meczu — wszystko, co o nim wiemy z własnych danych (bez LLM).

    `df` — zbiór historyczny w schemacie produkcyjnym (po `adapt_to_prod_schema`)
    albo None. `bzz` — event z `predykcje_tygodnia` już dopasowany do meczu
    (`dopasuj_event`) albo None. `karta_druzyn` — wynik `build_match_card`
    (opcjonalny; DB żyje po stronie endpointu, nie tutaj).
    """
    poisson, powod = _poisson(home, away, df)
    return {
        "home": home,
        "away": away,
        "liga": liga or (bzz or {}).get("liga"),
        "data": data or (bzz or {}).get("data"),
        "poisson": poisson,
        "poisson_powod": powod,
        "bzzoiro": _bzzoiro(bzz),
        "rynek": _rynek(bzz),
        "forma": None if df is None else {"home": forma(df, home), "away": forma(df, away)},
        "statystyki": _statystyki(karta_druzyn),
        "uwagi": list(UWAGI_STALE),
    }


# ── Prompt ──────────────────────────────────────────────────────────────────

def _fmt(wartosc: float | None, jednostka: str = "%") -> str:
    return "brak" if wartosc is None else f"{wartosc:.1f}{jednostka}"


def _linia_poissona(karta: dict[str, Any]) -> list[str]:
    p = karta.get("poisson")
    if not p:
        return [f"Czysty Poisson: brak — {karta.get('poisson_powod') or 'powód nieznany'}"]
    linie = ", ".join(f"Over {k}={v:.1f}%" for k, v in p["linie"].items())
    return [
        f"Czysty Poisson: λ gospodarzy {p['lambda_home']:.2f}, λ gości {p['lambda_away']:.2f};"
        f" 1={p['p1']:.1f}% X={p['px']:.1f}% 2={p['p2']:.1f}%; BTTS={p['btts']:.1f}%",
        f"Linie goli (czysty Poisson): {linie}",
    ]


def _linia_bzzoiro(karta: dict[str, Any]) -> str:
    b = karta.get("bzzoiro")
    if not b:
        return "Bzzoiro-ML: brak predykcji"
    return (f"Bzzoiro-ML: 1={_fmt(b['p1'])} X={_fmt(b['px'])} 2={_fmt(b['p2'])};"
            f" Over 2.5={_fmt(b['over25'])}; BTTS={_fmt(b['btts'])}")


def _linia_rynku(karta: dict[str, Any]) -> str:
    r = karta.get("rynek")
    if not r:
        return "Rynek bez marży: brak kursów rynkowych"
    czesci = []
    if "p1" in r:
        czesci.append(f"1={r['p1']:.1f}% X={r['px']:.1f}% 2={r['p2']:.1f}%")
    if "over25" in r:
        czesci.append(f"Over 2.5={r['over25']:.1f}% Under 2.5={r['under25']:.1f}%")
    return "Rynek bez marży: " + "; ".join(czesci)


def _linie_formy(karta: dict[str, Any]) -> list[str]:
    forma_obu = karta.get("forma")
    if not forma_obu:
        return ["Forma: brak danych historycznych"]
    wynik = []
    for klucz in ("home", "away"):
        nazwa = karta.get(klucz)
        f = forma_obu.get(klucz)
        if not f:
            wynik.append(f"Forma {nazwa}: brak meczów w historii")
            continue
        mecze = ", ".join(
            f"{m['wynik']} {m['miejsce']} z {m['rywal']} ({m['rezultat']}, {m['data']})"
            for m in f["ostatnie"])
        wynik.append(
            f"Forma {nazwa} (od najnowszego): {mecze}; średnio strzela"
            f" {f['gole_strzelone_sr10']:.2f}, traci {f['gole_stracone_sr10']:.2f}"
            f" (ostatnie {f['mecze_w_sredniej']} meczów)")
    return wynik


def _linie_statystyk(karta: dict[str, Any]) -> list[str]:
    s = karta.get("statystyki")
    if not s:
        return []
    wynik = []
    for klucz in ("home", "away"):
        b = s.get(klucz)
        if b:
            wynik.append(f"Statystyki sezonu {karta.get(klucz)}: {b['matches']} meczów,"
                         f" gole/mecz {b['gf_pg']} strzelone, {b['ga_pg']} stracone,"
                         f" rating {b['rating']}")
    for klucz, strona in (("strzelcy_home", "home"), ("strzelcy_away", "away")):
        if s.get(klucz):
            top = ", ".join(f"{x['name']} ({(x['goal_share'] or 0) * 100:.0f}% goli)"
                            for x in s[klucz])
            wynik.append(f"Główni strzelcy {karta.get(strona)}: {top}")
    return wynik


def _roznice_od_rynku(karta: dict[str, Any]) -> list[str]:
    """Różnice model - rynek >= progu; liczone tu, bo LLM słabo odejmuje."""
    rynek = karta.get("rynek")
    if not rynek:
        return []
    wynik = []
    for zrodlo, etykieta in (("poisson", "Poisson"), ("bzzoiro", "Bzzoiro-ML")):
        blok = karta.get(zrodlo)
        if not blok:
            continue
        for klucz, nazwa in (("p1", "1"), ("px", "X"), ("p2", "2"), ("over25", "Over 2.5")):
            m, r = blok.get(klucz), rynek.get(klucz)
            if m is None or r is None:
                continue
            d = round(m - r, 1)
            if abs(d) >= _PROG_ROZNICY_PP:
                wynik.append(f"{etykieta} {nazwa}: {m:.1f}% vs rynek {r:.1f}% ({d:+.1f} pp)")
    return wynik


def _sygnaly_niepewnosci(karta: dict[str, Any]) -> list[str]:
    wynik = []
    if not karta.get("poisson"):
        wynik.append("brak czystego Poissona (powód podany wyżej)")
    for klucz in ("home", "away"):
        f = (karta.get("forma") or {}).get(klucz)
        if karta.get("forma") and not f:
            wynik.append(f"brak historii meczów: {karta.get(klucz)}")
        elif f and f["mecze_w_sredniej"] < _OKNO_SREDNIEJ:
            wynik.append(f"mała historia: {karta.get(klucz)} ma w zbiorze tylko"
                         f" {f['mecze_w_sredniej']} meczów")
    if not karta.get("bzzoiro"):
        wynik.append("brak predykcji Bzzoiro-ML")
    if not karta.get("rynek"):
        wynik.append("brak kursów rynkowych")
    return wynik


def prompt_opisu(karta: dict[str, Any]) -> str:
    """Prompt dla LLM: karta + zakazy + 5 sekcji. Czyta TYLKO pola schematu karty."""
    roznice = _roznice_od_rynku(karta)
    sygnaly = _sygnaly_niepewnosci(karta)
    linie = [
        "Zinterpretuj poniższą KARTĘ LICZB meczu po polsku, dla właściciela systemu"
        " (tekst wewnętrzny).",
        "ZASADY (bezwzględne):",
        "1. Korzystaj WYŁĄCZNIE z liczb i faktów z karty. Niczego nie dopisuj z własnej"
        " wiedzy: żadnych kontuzji, składów, transferów, wiadomości, motywacji, pogody"
        " ani wyników spoza karty.",
        "2. Nie dawaj rekomendacji zakładu ani typu do postawienia i nie obiecuj skuteczności.",
        "3. Czego w karcie brak, tego nie zgaduj — napisz „brak danych”.",
        "",
        "KARTA LICZB",
        f"Mecz: {karta.get('home')} – {karta.get('away')}"
        f" ({karta.get('liga') or '?'}, {karta.get('data') or '?'})",
        *_linia_poissona(karta),
        _linia_bzzoiro(karta),
        _linia_rynku(karta),
        *_linie_formy(karta),
        *_linie_statystyk(karta),
        "Różnice względem rynku (>= 5 pp): "
        + ("; ".join(roznice) if roznice else
           ("brak różnic >= 5 pp" if karta.get("rynek") else "nie do oceny (brak kursów rynkowych)")),
        "Sygnały niepewności: " + ("; ".join(sygnaly) if sygnaly else "brak"),
        "Uwagi stałe:",
        *[f"- {u}" for u in karta.get("uwagi") or []],
        "",
        "Napisz opis w 5 sekcjach, każda z nagłówkiem w osobnej linii i 1–3 zdaniami"
        " (łącznie do ok. 220 słów):",
        "1. Siła i forma",
        "2. Czego spodziewa się model",
        "3. Gdzie model różni się od rynku (różnice co najmniej 5 pp)",
        "4. Niepewność (mała historia, brak Poissona, zaniżone gole)",
        "5. Podsumowanie (dokładnie 2 zdania)",
    ]
    return "\n".join(linie)


# ── Opis LLM z cache w pamięci procesu ──────────────────────────────────────
#
# Jeden użytkownik (admin), więc trwały cache w bazie to YAGNI; SQLite z
# `match_analysis` żyje na efemerycznym FS kontenera. Klucz = hash KARTY: zmiana
# liczb (kursy, Bzzoiro, forma) daje nowy opis, ta sama karta — wpis z cache.

_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
_blokada_cache = threading.Lock()


def _teraz() -> float:
    return time.monotonic()


def _klucz_karty(karta: dict[str, Any]) -> str:
    surowe = json.dumps(karta, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(surowe.encode("utf-8")).hexdigest()


def wyczysc_cache() -> None:
    with _blokada_cache:
        _cache.clear()


def rozmiar_cache() -> int:
    with _blokada_cache:
        return len(_cache)


def opisz_z_info(
    karta: dict[str, Any], zapytaj: Callable[..., str | None] = zapytaj_ai,
) -> tuple[str | None, bool]:
    """(opis, z_cache). Opis None, gdy LLM zawiódł lub zwrócił pustkę (nie cache'ujemy)."""
    klucz = _klucz_karty(karta)
    with _blokada_cache:
        wpis = _cache.get(klucz)
        if wpis is not None:
            if _teraz() - wpis[0] < _TTL_CACHE_S:
                return wpis[1], True
            del _cache[klucz]

    try:
        odpowiedz = zapytaj(prompt_opisu(karta), max_tokens=_MAX_TOKENS_OPISU)
    except Exception as e:  # noqa: BLE001 — Groq/Ollama/sieć: karta i tak wraca do GUI
        log.warning("opis_meczu: LLM nieudany: %s: %s", type(e).__name__, e)
        return None, False

    opis = (odpowiedz or "").strip()
    if not opis:
        log.warning("opis_meczu: LLM zwrócił pustą odpowiedź")
        return None, False

    with _blokada_cache:
        _cache[klucz] = (_teraz(), opis)
        _cache.move_to_end(klucz)
        while len(_cache) > _MAX_WPISOW_CACHE:
            _cache.popitem(last=False)
    return opis, False


def opisz(
    karta: dict[str, Any], zapytaj: Callable[..., str | None] = zapytaj_ai,
) -> str | None:
    """Opis karty od LLM (cache 6 h, max 200 wpisów) albo None, gdy LLM zawiódł."""
    return opisz_z_info(karta, zapytaj)[0]
