import os

import pandas as pd
from footstats.utils.console import console
from footstats.utils.helpers import _s
from footstats.config import DOMWYJAZD_MIN_M, DOMWYJAZD_PODROZNIK, OSTATNIE_N
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich import box

# ================================================================
#  MODUL 8 - WAZONA FORMA
# ================================================================

def _wagi_mecze(df_mecze: pd.DataFrame) -> pd.Series:
    """
    Wagi czasowe: od najnowszego meczu:
      pozycja 0-2  (3 najnowsze): 1.5x
      pozycja 3-6               : 1.0x
      pozycja 7+                : 0.5x
    """
    n    = len(df_mecze)
    wagi = []
    for i in range(n):
        rev_i = n - 1 - i
        if rev_i < 3:
            wagi.append(1.5)
        elif rev_i < 7:
            wagi.append(1.0)
        else:
            wagi.append(0.5)
    return pd.Series(wagi, index=df_mecze.index)

# Ile ostatnich meczów drużyny (osobno u siebie i na wyjeździe) wchodzi do ratingu.
# 30 wybrane pomiarem: 15 jest za szumne, 60 zaczyna ciągnąć nieaktualną formę.
OKNO_LIGOWE = 30

# Poniżej tylu meczów rating jest szumem udającym wiedzę — drużyna wypada.
MIN_MECZOW_LIGOWYCH = 6


def _tabela_ratingow(df_liga: pd.DataFrame, kol_dom: str, kol_wyj: str,
                     okno: int) -> tuple[dict, float, float] | None:
    """Ratingi dom/wyjazd wobec średniej ligowej dla DOWOLNEJ pary kolumn.

    Ta sama arytmetyka służy golom i strzałom celnym — ilorazy są bezwymiarowe,
    więc λ zostaje w golach niezależnie od tego, czym mierzymy siłę.
    """
    dane = df_liga.dropna(subset=[kol_dom, kol_wyj])
    if dane.empty:
        return None
    sr_dom = float(dane[kol_dom].mean())
    sr_wyj = float(dane[kol_wyj].mean())
    if not (sr_dom > 0 and sr_wyj > 0):
        return None

    tabela: dict[str, dict] = {}
    for druzyna in set(dane["gospodarz"]) | set(dane["goscie"]):
        dom = dane[dane["gospodarz"] == druzyna].tail(okno)
        wyj = dane[dane["goscie"] == druzyna].tail(okno)
        if len(dom) + len(wyj) < MIN_MECZOW_LIGOWYCH:
            continue
        tabela[druzyna] = {
            "atak_dom":   float(dom[kol_dom].mean()) / sr_dom if len(dom) else 1.0,
            "atak_wyj":   float(wyj[kol_wyj].mean()) / sr_wyj if len(wyj) else 1.0,
            "obrona_dom": float(dom[kol_wyj].mean()) / sr_wyj if len(dom) else 1.0,
            "obrona_wyj": float(wyj[kol_dom].mean()) / sr_dom if len(wyj) else 1.0,
            "mecze":      len(dom) + len(wyj),
        }
    return (tabela, sr_dom, sr_wyj) if tabela else None


def sily_ligowe(
    df_liga: pd.DataFrame,
    okno: int = OKNO_LIGOWE,
    waga_strzalow: float | None = None,
) -> tuple[dict, float, float] | None:
    """Siła każdej drużyny WOBEC LIGI: {atak_dom, atak_wyj, obrona_dom, obrona_wyj}.

    Zwraca `(tabela, srednia_goli_gospodarzy, srednia_goli_gosci)` albo None,
    gdy z ramki nie da się nic policzyć.

    DLACZEGO wobec ligi, a nie wobec własnej próbki: `_oblicz_sile_wazona`
    liczy `atak = gole / srednia`, gdzie `srednia` pochodzi z TEJ SAMEJ garstki
    meczów, którą dostała. Drużyna dużo strzelająca dzieli więc swoje gole przez
    średnią, którą sama zawyżyła — sygnał się kasuje i ratingi ściągają do 1.0.
    To jest źródło braku rozdzielczości modelu: predykcje różnią się od siebie
    mniej, niż różnią się drużyny.

    DLACZEGO osobno dom i wyjazd: średnia goli gospodarzy już zawiera atut
    własnego boiska. Mnożenie wyniku jeszcze raz przez `BONUS_DOMOWY` liczyłoby
    go drugi raz.

    Zmierzone walk-forwardem na dwóch niezależnych próbach — Brier 0.6557→0.6089
    (4 ligi top) i 0.6639→0.6142 (6 innych lig), przy 0.6001/0.5924 dla rynku.

    STRZAŁY CELNE (`waga_strzalow`): gol pada ~1,4 razy na drużynę, strzał celny
    4-5 razy częściej — ta sama próbka daje więc stabilniejszą ocenę siły. Ratingi
    ze strzałów mieszają się z golowymi; ilorazy są bezwymiarowe, więc λ zostaje
    w golach. Zmierzone na dwóch próbach: Brier 0.6062→0.6032 (top-4) i
    0.6290→0.6180 (6 innych lig). Brak kolumn albo pustych strzałów cicho wraca
    do samych goli — połowa datasetu ich nie ma i to jest normalny stan.
    """
    wymagane = {"gospodarz", "goscie", "gole_g", "gole_a"}
    if df_liga is None or df_liga.empty or not wymagane.issubset(df_liga.columns):
        return None

    z_goli = _tabela_ratingow(df_liga, "gole_g", "gole_a", okno)
    if not z_goli:
        return None  # liga bez goli — każdy iloraz byłby dzieleniem przez zero
    tabela, sr_dom, sr_wyj = z_goli

    if waga_strzalow is None:
        from footstats.config import WAGA_STRZALOW
        waga_strzalow = WAGA_STRZALOW

    if waga_strzalow > 0 and {"hst", "ast"} <= set(df_liga.columns):
        ze_strzalow = _tabela_ratingow(df_liga, "hst", "ast", okno)
        if ze_strzalow:
            tab_s = ze_strzalow[0]
            w = waga_strzalow
            for druzyna, wpis in tabela.items():
                s = tab_s.get(druzyna)
                if not s:
                    continue  # ta drużyna nie ma strzałów — zostaje na golach
                for klucz in ("atak_dom", "atak_wyj", "obrona_dom", "obrona_wyj"):
                    wpis[klucz] = w * s[klucz] + (1 - w) * wpis[klucz]

    return (tabela, sr_dom, sr_wyj)


def _oblicz_sile_wazona(df_mecze: pd.DataFrame) -> tuple:
    sr_g    = df_mecze["gole_g"].mean()
    sr_a    = df_mecze["gole_a"].mean()
    srednia = (sr_g + sr_a) / 2 or 1.0
    sily    = {}

    for d in set(df_mecze["gospodarz"]) | set(df_mecze["goscie"]):
        dom = df_mecze[df_mecze["gospodarz"] == d].copy()
        wyj = df_mecze[df_mecze["goscie"]    == d].copy()

        if not dom.empty:
            w_d   = _wagi_mecze(dom)
            str_d = (dom["gole_g"] * w_d).sum() / w_d.sum()
            st_d  = (dom["gole_a"] * w_d).sum() / w_d.sum()
        else:
            str_d = st_d = srednia

        if not wyj.empty:
            w_w   = _wagi_mecze(wyj)
            str_w = (wyj["gole_a"] * w_w).sum() / w_w.sum()
            st_w  = (wyj["gole_g"] * w_w).sum() / w_w.sum()
        else:
            str_w = st_w = srednia

        nd, nw = len(dom), len(wyj)
        nt     = nd + nw or 1
        strzal = (str_d * nd + str_w * nw) / nt
        strata = (st_d  * nd + st_w  * nw) / nt

        df_all = pd.concat([
            dom.assign(wynik_d=dom.apply(
                lambda r: "W" if r.gole_g>r.gole_a else("R" if r.gole_g==r.gole_a else "P"), axis=1)),
            wyj.assign(wynik_d=wyj.apply(
                lambda r: "W" if r.gole_a>r.gole_g else("R" if r.gole_a==r.gole_g else "P"), axis=1)),
        ]).sort_values("data").tail(OSTATNIE_N)

        forma_pkt = 0.0
        if not df_all.empty:
            w_all = _wagi_mecze(df_all)
            mapa  = {"W": 3, "R": 1, "P": 0}
            forma_pkt = sum(
                mapa.get(row.get("wynik_d", "P"), 0) * w_all[idx]
                for idx, row in df_all.iterrows()
            ) / (w_all.sum() or 1)

        sily[d] = {
            "atak":      strzal  / srednia,
            "obrona":    strata  / srednia,
            "mecze":     nt,
            "gole_sr":   round(strzal,  2),
            "strac_sr":  round(strata,  2),
            "forma_pkt": round(forma_pkt, 2),
        }

    # M1 lever #5 — schedule-adjusted ratings (opponent-adjusted, jedna iteracja).
    # Default OFF (env SCHEDULE_ADJUSTED_RATINGS) = zero zmiany prod. Flip dopiero po
    # walidacji offline (walk-forward A/B). Drużyna strzelająca silnym obronom dostaje
    # wyższy atak; tracąca słabym atakom — gorszą obronę.
    if _schedule_adj_on():
        sily = _opponent_adjust(df_mecze, sily, srednia)

    return sily, srednia


def _schedule_adj_on() -> bool:
    """Czy schedule-adjusted ratings włączone (env SCHEDULE_ADJUSTED_RATINGS, default OFF)."""
    return os.getenv("SCHEDULE_ADJUSTED_RATINGS", "0").strip().lower() in ("1", "true", "yes")


def _opponent_adjust(df_mecze: pd.DataFrame, sily: dict, srednia: float) -> dict:
    """
    Jedna iteracja korekty siły o trudność terminarza (opponent-adjusted ratings).

    Dla każdej drużyny przelicza atak/obronę ważąc gole siłą rywala z `sily` (raw):
      atak    = ważona średnia (gole_strzelone / obrona_rywala) / średnia,
      obrona  = ważona średnia (gole_stracone  / atak_rywala)   / średnia.
    Rywale spoza `sily` → neutralne 1.0. Zwraca NOWY dict (bez mutacji wejścia).
    """
    raw = sily
    out = {d: dict(v) for d, v in sily.items()}

    for d in raw:
        scored_vals: list[float] = []
        scored_w:    list[float] = []
        conc_vals:   list[float] = []
        conc_w:      list[float] = []

        dom = df_mecze[df_mecze["gospodarz"] == d]
        if not dom.empty:
            wd = _wagi_mecze(dom).to_numpy()
            for r, w in zip(dom.to_dict("records"), wd):
                opp = raw.get(r["goscie"], {})
                opp_obr = opp.get("obrona", 1.0) or 1.0
                opp_atk = opp.get("atak", 1.0) or 1.0
                scored_vals.append(r["gole_g"] / opp_obr); scored_w.append(w)
                conc_vals.append(r["gole_a"] / opp_atk);   conc_w.append(w)

        wyj = df_mecze[df_mecze["goscie"] == d]
        if not wyj.empty:
            ww = _wagi_mecze(wyj).to_numpy()
            for r, w in zip(wyj.to_dict("records"), ww):
                opp = raw.get(r["gospodarz"], {})
                opp_obr = opp.get("obrona", 1.0) or 1.0
                opp_atk = opp.get("atak", 1.0) or 1.0
                scored_vals.append(r["gole_a"] / opp_obr); scored_w.append(w)
                conc_vals.append(r["gole_g"] / opp_atk);   conc_w.append(w)

        if scored_w and sum(scored_w) > 0:
            out[d]["atak"] = (sum(v * w for v, w in zip(scored_vals, scored_w))
                              / sum(scored_w)) / srednia
        if conc_w and sum(conc_w) > 0:
            out[d]["obrona"] = (sum(v * w for v, w in zip(conc_vals, conc_w))
                                / sum(conc_w)) / srednia

    return out


# ================================================================
#  MODUL 13 - ANALIZA FORMY
# ================================================================

def pobierz_forme(druzyna: str, df_mecze: pd.DataFrame, n: int = 8) -> pd.DataFrame:
    dom = df_mecze[df_mecze["gospodarz"] == druzyna].copy()
    wyj = df_mecze[df_mecze["goscie"]    == druzyna].copy()
    dom["wynik"]     = dom.apply(lambda r: "W" if r.gole_g>r.gole_a else("R" if r.gole_g==r.gole_a else "P"), axis=1)
    dom["strzelone"] = dom["gole_g"]; dom["stracone"] = dom["gole_a"]; dom["miejsce"] = "Dom"
    wyj["wynik"]     = wyj.apply(lambda r: "W" if r.gole_a>r.gole_g else("R" if r.gole_a==r.gole_g else "P"), axis=1)
    wyj["strzelone"] = wyj["gole_a"]; wyj["stracone"] = wyj["gole_g"]; wyj["miejsce"] = "Wyjazd"
    kols = ["data","gospodarz","goscie","gole_g","gole_a","wynik","strzelone","stracone","miejsce"]
    return pd.concat([dom[kols], wyj[kols]]).sort_values("data").tail(n)

def wyswietl_forme(druzyna: str, df_mecze: pd.DataFrame, n: int = 8):
    df = pobierz_forme(druzyna, df_mecze, n)
    if df.empty:
        console.print(f"[red]Brak danych dla: {druzyna}[/red]"); return
    t = Table(title=f"[bold cyan]Forma: {druzyna}[/bold cyan]",
              box=box.MINIMAL_DOUBLE_HEAD, border_style="cyan", header_style="bold cyan")
    t.add_column("Data",   style="dim",        justify="center", width=11)
    t.add_column("Gosp.",  style="bold white",  justify="right",  width=14)
    t.add_column("Wynik",  style="bold yellow", justify="center", width=7)
    t.add_column("Goscie", style="bold white",  justify="left",   width=14)
    t.add_column("Gdzie",  style="dim",         justify="center", width=8)
    t.add_column("W/R/P",  style="bold",        justify="center", width=5)
    for _, r in df.iloc[::-1].iterrows():
        k = "bold green" if r["wynik"]=="W" else("bold yellow" if r["wynik"]=="R" else "bold red")
        t.add_row(_s(r["data"]), _s(r["gospodarz"]), f"{r['gole_g']}-{r['gole_a']}",
                  _s(r["goscie"]), _s(r["miejsce"]), f"[{k}]{r['wynik']}[/{k}]")
    console.print(t)
    pasek = Text()
    for w in df["wynik"]:
        if w=="W":   pasek.append(" W ", style="bold white on green")
        elif w=="R": pasek.append(" R ", style="bold black on yellow")
        else:        pasek.append(" P ", style="bold white on red")
        pasek.append(" ")
    console.print(Align.center(pasek))
    console.print(Align.center(Text(
        f"  Sr. strzelon: {df['strzelone'].mean():.2f}  |  Sr. stracon: {df['stracone'].mean():.2f}  ",
        style="dim")))
    console.print()

def porownaj_forme(g: str, a: str, df_mecze: pd.DataFrame, n: int = 8):
    console.rule(f"[bold cyan]{g}  vs  {a}[/bold cyan]")
    wyswietl_forme(g, df_mecze, n)
    wyswietl_forme(a, df_mecze, n)
    maska = ((df_mecze["gospodarz"]==g)|(df_mecze["goscie"]==g)|
             (df_mecze["gospodarz"]==a)|(df_mecze["goscie"]==a))
    df_f  = df_mecze[maska].tail(OSTATNIE_N)
    if len(df_f) < 4: return
    sily, _ = _oblicz_sile_wazona(df_f)
    if g not in sily or a not in sily: return
    sg, sa = sily[g], sily[a]

    def lepsza(v1, v2, wyzej=True):
        s1 = "bold green" if (v1>=v2 if wyzej else v1<=v2) else "dim"
        s2 = "bold green" if (v2>v1  if wyzej else v2<v1)  else "dim"
        return f"[{s1}]{v1}[/{s1}]", f"[{s2}]{v2}[/{s2}]"

    tc = Table(title="[bold magenta]Porownanie Wskaznikow[/bold magenta]",
               box=box.ROUNDED, border_style="magenta", header_style="bold magenta")
    tc.add_column("Wskaznik", style="dim",       justify="right",  width=28)
    tc.add_column(g[:16],     style="bold green", justify="center", width=10)
    tc.add_column(a[:16],     style="bold red",   justify="center", width=10)
    for label, v1, v2, w2 in [
        ("Wspolczynnik ataku (wazony)",  sg["atak"],     sa["atak"],     True),
        ("Wspolczynnik obrony (wazony)", sg["obrona"],   sa["obrona"],   False),
        ("Sr. goli strzelonych",         sg["gole_sr"],  sa["gole_sr"],  True),
        ("Sr. goli straconych",          sg["strac_sr"], sa["strac_sr"], False),
        ("Forma pkt/mecz (wazony)",      sg["forma_pkt"],sa["forma_pkt"],True),
    ]:
        r1, r2 = lepsza(round(v1,2), round(v2,2), w2)
        tc.add_row(label, r1, r2)
    console.print(tc)

    h2h = df_mecze[
        ((df_mecze["gospodarz"]==g)&(df_mecze["goscie"]==a)) |
        ((df_mecze["gospodarz"]==a)&(df_mecze["goscie"]==g))
    ].tail(5)
    if not h2h.empty:
        th = Table(title=f"[bold yellow]H2H: {g} vs {a}[/bold yellow]",
                   box=box.MINIMAL, border_style="yellow", header_style="bold yellow")
        th.add_column("Data",  style="dim",        justify="center")
        th.add_column("Gosp.", style="bold white",  justify="right")
        th.add_column("Wynik", style="bold yellow", justify="center")
        th.add_column("Gosc",  style="bold white",  justify="left")
        for _, r in h2h.iloc[::-1].iterrows():
            gg, ga = r["gole_g"], r["gole_a"]
            kg = "bold green" if gg>ga else("yellow" if gg==ga else "dim red")
            ka = "bold red"   if gg>ga else("yellow" if gg==ga else "bold green")
            th.add_row(_s(r["data"]), f"[{kg}]{r['gospodarz']}[/{kg}]",
                       f"{gg}-{ga}", f"[{ka}]{r['goscie']}[/{ka}]")
        console.print(th)


# ================================================================
#  MODUL 13b - ANALIZA DOM/WYJAZD (v2.7)
# ================================================================

class AnalizaDomWyjazd:
    """
    Osobne statystyki domowe i wyjazdowe druzyny.
    Wykrywa 'Podroznika' - druzyne lepsza na wyjezdzie niz u siebie.
    """

    def __init__(self, df_mecze):
        self.df = df_mecze.copy() if df_mecze is not None else pd.DataFrame()

    def analiza(self, druzyna, n=10):
        wynik = {
            "druzyna": druzyna, "dom_pkt": 0.0, "wyjazd_pkt": 0.0,
            "dom_gole_str": 0.0, "dom_gole_strac": 0.0,
            "wyj_gole_str": 0.0, "wyj_gole_strac": 0.0,
            "dom_seria": "", "wyj_seria": "", "dom_m": 0, "wyj_m": 0,
            "podroznik": False, "bonus_wyjazd": 1.0, "opis": "", "ikona": "",
        }
        if self.df.empty:
            return wynik

        dom = self.df[self.df["gospodarz"] == druzyna].sort_values("data").tail(n)
        wyj = self.df[self.df["goscie"] == druzyna].sort_values("data").tail(n)

        def _stats(df_sub, is_dom):
            if df_sub.empty:
                return 0.0, 0.0, 0.0, ""
            pkt = 0; seria = []
            for _, r in df_sub.iterrows():
                gg, ga = int(r["gole_g"]), int(r["gole_a"])
                w = gg > ga if is_dom else ga > gg
                re = gg == ga
                if w:     pkt += 3; seria.append("W")
                elif re:  pkt += 1; seria.append("R")
                else:     seria.append("P")
            n_m = len(df_sub)
            avg_g = float(df_sub["gole_g"].mean() if is_dom else df_sub["gole_a"].mean())
            avg_s = float(df_sub["gole_a"].mean() if is_dom else df_sub["gole_g"].mean())
            return round(pkt/n_m, 2), round(avg_g, 2), round(avg_s, 2), " ".join(seria[-5:])

        d_pkt, d_str, d_strac, d_ser = _stats(dom, True)
        w_pkt, w_str, w_strac, w_ser = _stats(wyj, False)

        wynik.update({
            "dom_pkt": d_pkt, "wyjazd_pkt": w_pkt,
            "dom_gole_str": d_str, "dom_gole_strac": d_strac,
            "wyj_gole_str": w_str, "wyj_gole_strac": w_strac,
            "dom_seria": d_ser, "wyj_seria": w_ser,
            "dom_m": len(dom), "wyj_m": len(wyj),
        })

        roznica = w_pkt - d_pkt
        if len(wyj) >= DOMWYJAZD_MIN_M and roznica >= DOMWYJAZD_PODROZNIK:
            wynik.update({
                "podroznik": True, "bonus_wyjazd": 1.10, "ikona": "✈️",
                "opis": (f"✈️ Podroznik: {druzyna} lepszy na wyjezdzie "
                         f"({w_pkt:.2f} pkt/m) niz u siebie ({d_pkt:.2f} pkt/m). "
                         f"Lambda ataku goscia +10%.")
            })
        elif d_pkt > w_pkt + 0.3:
            wynik["opis"] = (f"🏠 Bastion: {druzyna} silniejszy u siebie "
                             f"({d_pkt:.2f} vs {w_pkt:.2f} pkt/mecz wyjazd).")
        else:
            wynik["opis"] = (f"~= Wyrownany: {druzyna} dom {d_pkt:.2f} / "
                             f"wyjazd {w_pkt:.2f} pkt/mecz.")
        return wynik

    def wyswietl(self, druzyna, n=10):
        w = self.analiza(druzyna, n)
        console.rule(f"[bold cyan]Analiza Dom/Wyjazd: {druzyna}[/bold cyan]")
        t = Table(box=box.ROUNDED, border_style="cyan", header_style="bold cyan")
        t.add_column("Metryka", style="dim", justify="right", width=24)
        t.add_column("🏠 DOM", style="bold green", justify="center", width=14)
        t.add_column("✈️ WYJAZD", style="bold yellow", justify="center", width=14)
        t.add_column("Delta", style="bold", justify="center", width=10)

        def delta(d, wy, im_wyzej=True):
            r = round(wy - d, 2)
            k = ("bold green" if (r>0) == im_wyzej else "bold red") if r != 0 else "dim"
            return f"[{k}]{'+' if r>0 else ''}{r}[/{k}]"

        t.add_row("Mecze (ostatnie)", str(w["dom_m"]), str(w["wyj_m"]), "")
        t.add_row("Pkt/mecz", f"[bold]{w['dom_pkt']}[/bold]",
                  f"[bold]{w['wyjazd_pkt']}[/bold]",
                  delta(w["dom_pkt"], w["wyjazd_pkt"]))
        t.add_row("Gole str./mecz", str(w["dom_gole_str"]), str(w["wyj_gole_str"]),
                  delta(w["dom_gole_str"], w["wyj_gole_str"]))
        t.add_row("Gole strac./mecz", str(w["dom_gole_strac"]), str(w["wyj_gole_strac"]),
                  delta(w["dom_gole_strac"], w["wyj_gole_strac"], False))
        t.add_row("Forma (5 ost.)", w["dom_seria"] or "–", w["wyj_seria"] or "–", "")
        console.print(t)
        styl = "green" if w["podroznik"] else "dim"
        from rich.panel import Panel
        console.print(Panel(w["opis"], border_style=styl, padding=(0, 2)))
        console.print()
