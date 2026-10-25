"""Opisy meczów dla właściciela: karta liczb (deterministyczna) + opis LLM.

Spec: docs/superpowers/specs/2026-10-23-opisy-meczow-admin-design.md.

Testy bez sieci, bez bazy i bez Telegrama: zbiór historyczny to mała atrapa
`pd.DataFrame` (lokalne `.venv` nie ma pyarrow, więc nie czytamy parquetu),
Bzzoiro to słownik, a Groq (`zapytaj`) jest funkcją-atrapą.
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.core import opis_meczu
from footstats.core.opis_meczu import (
    dopasuj_event,
    forma,
    opisz,
    opisz_z_info,
    prompt_opisu,
    rynek_bez_marzy,
    zbuduj_karte,
)

# (data, gospodarz, goscie, gole_g, gole_a) — Alfa gra w 11 z 12 meczów.
_MECZE = [
    ("2026-08-01", "Alfa", "Beta", 2, 0),
    ("2026-08-08", "Gamma", "Alfa", 1, 1),
    ("2026-08-15", "Alfa", "Gamma", 3, 1),
    ("2026-08-22", "Beta", "Alfa", 0, 2),
    ("2026-08-29", "Alfa", "Beta", 1, 1),
    ("2026-09-05", "Gamma", "Alfa", 2, 0),
    ("2026-09-12", "Alfa", "Gamma", 2, 1),
    ("2026-09-19", "Beta", "Alfa", 1, 3),
    ("2026-09-26", "Alfa", "Beta", 0, 0),
    ("2026-10-03", "Gamma", "Alfa", 0, 1),
    ("2026-10-10", "Beta", "Gamma", 2, 2),
    ("2026-10-17", "Alfa", "Gamma", 2, 2),
]

_ODDS = {"home": 2.0, "draw": 3.5, "away": 4.0,
         "over_2_5": 1.9, "under_2_5": 1.95, "btts": 1.8}

_EVENT = {
    "gosp": "Alfa", "gosc": "Beta", "liga": "Test League", "data": "2026-10-25",
    "pred_ml": {"prob_home_win": 50, "prob_draw": 25, "prob_away_win": 25,
                "prob_over_25": 55, "prob_btts_yes": 60},
    "odds": _ODDS,
}


def _df() -> pd.DataFrame:
    """Schemat produkcyjny po `adapt_to_prod_schema` (gospodarz/goscie/gole_g/gole_a/data)."""
    return pd.DataFrame(
        [{"data": pd.Timestamp(d), "gospodarz": g, "goscie": a, "gole_g": hg, "gole_a": ag}
         for d, g, a, hg, ag in _MECZE]
    )


@pytest.fixture(autouse=True)
def _czysty_cache():
    opis_meczu.wyczysc_cache()
    yield
    opis_meczu.wyczysc_cache()


# ── forma ───────────────────────────────────────────────────────────────────

def test_forma_ostatnie_5_najnowsze_pierwsze():
    f = forma(_df(), "Alfa", n=5)

    assert f is not None
    assert [m["data"] for m in f["ostatnie"]] == [
        "2026-10-17", "2026-10-03", "2026-09-26", "2026-09-19", "2026-09-12"]
    pierwszy, drugi = f["ostatnie"][0], f["ostatnie"][1]
    assert pierwszy == {"data": "2026-10-17", "rywal": "Gamma", "wynik": "2:2",
                        "miejsce": "dom", "rezultat": "R"}
    # Wynik zawsze z perspektywy badanej drużyny: Gamma 0:1 Alfa -> Alfa 1:0 na wyjeździe.
    assert drugi == {"data": "2026-10-03", "rywal": "Gamma", "wynik": "1:0",
                     "miejsce": "wyjazd", "rezultat": "W"}


def test_forma_srednie_gole_z_ostatnich_10():
    f = forma(_df(), "Alfa", n=5)

    # Ostatnie 10 meczów Alfy: strzelone 15, stracone 9.
    assert f["mecze_w_sredniej"] == 10
    assert f["gole_strzelone_sr10"] == pytest.approx(1.5)
    assert f["gole_stracone_sr10"] == pytest.approx(0.9)


def test_forma_nieznana_druzyna_none():
    assert forma(_df(), "Nieistniejacy FC", n=5) is None


def test_forma_do_daty_nie_widzi_pozniejszych_wynikow():
    """Opis meczu z przeszłości nie może znać wyników rozegranych PO nim."""
    f = forma(_df(), "Alfa", n=5, do_daty="2026-09-12")

    # Mecz z 12.09 jest równą datą, więc też odpada (ostra nierówność): pierwszy to 05.09.
    assert [m["data"] for m in f["ostatnie"]] == [
        "2026-09-05", "2026-08-29", "2026-08-22", "2026-08-15", "2026-08-08"]
    assert f["mecze_w_sredniej"] == 6                  # w historii przed 12.09 jest 6 meczów Alfy
    # Średnie z tych 6 meczów: strzelone 9, stracone 5 (nie z całej historii).
    assert f["gole_strzelone_sr10"] == pytest.approx(1.5)
    assert f["gole_stracone_sr10"] == pytest.approx(5 / 6, abs=0.01)


def test_forma_do_daty_przed_pierwszym_meczem_none():
    assert forma(_df(), "Alfa", n=5, do_daty="2026-08-01") is None


def test_forma_do_daty_przyjmuje_znacznik_czasu_iso():
    f = forma(_df(), "Alfa", n=5, do_daty="2026-09-12T18:30:00+02:00")

    assert f["ostatnie"][0]["data"] == "2026-09-05"


def test_forma_nieczytelna_data_nie_obcina_historii():
    """Bzzoiro bywa bez daty/ze śmieciem — brak odcięcia, nie błąd."""
    pelna = forma(_df(), "Alfa", n=5)

    assert forma(_df(), "Alfa", n=5, do_daty="nie-data") == pelna
    assert forma(_df(), "Alfa", n=5, do_daty=None) == pelna


def test_forma_pomija_mecze_bez_wyniku():
    df = _df()
    df["gole_g"] = df["gole_g"].astype(float)
    df.loc[df.index[-1], "gole_g"] = float("nan")  # mecz nierozegrany / brak wyniku

    f = forma(df, "Alfa", n=5)

    assert f["ostatnie"][0]["data"] == "2026-10-03"


def test_forma_rozpoznaje_nazwe_z_innego_zrodla():
    """Bzzoiro pisze „Stoke City”, historia „Stoke” — ta sama reguła co w Poissonie."""
    df = pd.DataFrame([
        {"data": pd.Timestamp("2026-10-01"), "gospodarz": "Stoke", "goscie": "Norwich",
         "gole_g": 1, "gole_a": 0},
    ])

    f = forma(df, "Stoke City", n=5)

    assert f is not None and f["ostatnie"][0]["rywal"] == "Norwich"


# ── rynek bez marży ─────────────────────────────────────────────────────────

def test_rynek_bez_marzy_sumuje_sie_do_1():
    r = rynek_bez_marzy(_ODDS)

    assert r["p1"] + r["px"] + r["p2"] == pytest.approx(1.0)
    assert r["over25"] + r["under25"] == pytest.approx(1.0)
    # 1/2.0 = 0.5, 1/3.5, 1/4.0 -> suma 1.0357; p1 = 0.5 / 1.0357
    assert r["p1"] == pytest.approx(0.5 / (0.5 + 1 / 3.5 + 0.25))


@pytest.mark.parametrize("odds", [None, {}, {"home": None, "draw": None, "away": None}])
def test_rynek_bez_marzy_brak_kursow_none(odds):
    assert rynek_bez_marzy(odds) is None


def test_rynek_bez_marzy_niepelny_rynek_pomijany():
    """Brak kursu remisu -> nie liczymy 1X2 z dwóch kursów (zawyżyłoby p1 i p2)."""
    r = rynek_bez_marzy({"home": 2.0, "draw": None, "away": 4.0,
                         "over_2_5": 1.9, "under_2_5": 1.95})

    assert "p1" not in r and "px" not in r and "p2" not in r
    assert r["over25"] + r["under25"] == pytest.approx(1.0)


def test_rynek_bez_marzy_odrzuca_kursy_nielogiczne():
    assert rynek_bez_marzy({"home": 1.0, "draw": 3.0, "away": 4.0}) is None
    assert rynek_bez_marzy({"home": "x", "draw": 3.0, "away": 4.0}) is None
    assert rynek_bez_marzy({"home": float("nan"), "draw": 3.0, "away": 4.0}) is None


# ── dopasowanie eventu Bzzoiro ──────────────────────────────────────────────

def test_dopasuj_event_po_znormalizowanych_nazwach():
    zdarzenia = [
        {"gosp": "Beta", "gosc": "Alfa", "data": "2026-10-25"},   # odwrócona para
        _EVENT,
    ]

    assert dopasuj_event(zdarzenia, "  ALFA ", "beta", "2026-10-25") is _EVENT


def test_dopasuj_event_preferuje_te_sama_date():
    inny = {**_EVENT, "data": "2026-11-01"}

    assert dopasuj_event([inny, _EVENT], "Alfa", "Beta", "2026-10-25") is _EVENT
    # bez daty bierzemy pierwszy pasujący
    assert dopasuj_event([inny, _EVENT], "Alfa", "Beta", None) is inny


def test_dopasuj_event_brak_meczu_none():
    assert dopasuj_event([_EVENT], "Alfa", "Gamma", None) is None
    assert dopasuj_event([], "Alfa", "Beta", None) is None
    assert dopasuj_event(None, "Alfa", "Beta", None) is None


# ── karta liczb ─────────────────────────────────────────────────────────────

def test_karta_poisson_z_atrapy_df():
    k = zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", _df(), None)

    p = k["poisson"]
    assert k["poisson_powod"] is None
    assert p["lambda_home"] > 0 and p["lambda_away"] > 0
    assert p["p1"] + p["px"] + p["p2"] == pytest.approx(100.0, abs=0.3)
    assert list(p["linie"]) == ["0.5", "1.5", "2.5", "3.5", "4.5"]
    kolejne = list(p["linie"].values())
    assert kolejne == sorted(kolejne, reverse=True)       # wyższa linia = mniej prawdopodobna
    assert p["over25"] == p["linie"]["2.5"]
    assert 0.0 < p["btts"] < 100.0


def test_karta_linie_liczone_z_lambd_karty():
    """Linie muszą pochodzić z TEJ SAMEJ macierzy co 1X2 (`prob_linii_goli`)."""
    from footstats.core.poisson import prob_linii_goli

    p = zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", _df(), None)["poisson"]
    oczekiwane = prob_linii_goli(p["lambda_home"], p["lambda_away"])

    for linia, wartosc in oczekiwane.items():
        assert p["linie"][str(linia)] == pytest.approx(wartosc * 100, abs=0.06)


def test_karta_brak_zbioru_poisson_none_z_powodem():
    k = zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", None, _EVENT)

    assert k["poisson"] is None
    assert "zbior" in k["poisson_powod"].lower()
    assert k["forma"] is None


def test_karta_nieznana_para_poisson_none_z_powodem():
    k = zbuduj_karte("Delta", "Epsilon", "Test League", "2026-10-25", _df(), None)

    assert k["poisson"] is None
    assert k["poisson_powod"]                      # powód jest niepusty
    assert k["forma"] == {"home": None, "away": None}


def test_karta_wyjatek_w_poissonie_nie_wywraca_karty(monkeypatch):
    def _zepsute(*a, **k):
        raise ValueError("tajna tresc bledu")

    monkeypatch.setattr("footstats.core.poisson.predict_match", _zepsute)

    k = zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", _df(), _EVENT)

    assert k["poisson"] is None
    assert "ValueError" in k["poisson_powod"]
    assert "tajna tresc bledu" not in k["poisson_powod"]   # powód nie przecieka treści błędu
    assert k["bzzoiro"] is not None                        # reszta karty żyje


def test_karta_bzzoiro_i_rynek():
    k = zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", None, _EVENT)

    assert k["bzzoiro"] == {"p1": 50.0, "px": 25.0, "p2": 25.0, "over25": 55.0, "btts": 60.0}
    r = k["rynek"]
    assert r["p1"] + r["px"] + r["p2"] == pytest.approx(100.0, abs=0.2)
    assert r["over25"] + r["under25"] == pytest.approx(100.0, abs=0.1)


def test_karta_liga_i_data_z_eventu_gdy_brak_w_zadaniu():
    k = zbuduj_karte("Alfa", "Beta", None, None, None, _EVENT)

    assert k["liga"] == "Test League" and k["data"] == "2026-10-25"


def test_karta_bez_eventu_bzzoiro_i_rynek_none():
    k = zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", _df(), None)

    assert k["bzzoiro"] is None
    assert k["rynek"] is None


def test_karta_event_bez_kursow_rynek_none():
    ev = {**_EVENT, "odds": None}

    k = zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", None, ev)

    assert k["rynek"] is None
    assert k["bzzoiro"] is not None


def test_karta_zero_w_bzzoiro_to_brak_a_nie_zero_procent():
    """`predykcje_tygodnia` wstawia 0 za brakujące Over/BTTS — nie pokazujemy „0%”."""
    ev = {**_EVENT, "pred_ml": {"prob_home_win": 50, "prob_draw": 25, "prob_away_win": 25}}

    k = zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", None, ev)

    assert k["bzzoiro"]["over25"] is None and k["bzzoiro"]["btts"] is None
    assert k["bzzoiro"]["p1"] == 50.0


def test_karta_forma_obu_druzyn():
    k = zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", _df(), None)

    assert k["forma"]["home"]["ostatnie"][0]["rywal"] == "Gamma"
    assert k["forma"]["away"]["ostatnie"][0]["rywal"] == "Gamma"   # Beta 2:2 Gamma 10.10


def test_karta_forma_nie_widzi_meczow_po_dacie_meczu():
    """Karta meczu z 12.09 liczy formę tylko z wyników sprzed 12.09."""
    k = zbuduj_karte("Alfa", "Beta", "Test League", "2026-09-12", _df(), None)

    assert k["forma"]["home"]["ostatnie"][0]["data"] == "2026-09-05"
    assert k["forma"]["away"]["ostatnie"][0]["data"] == "2026-08-29"   # Beta: nic po 29.08 przed 12.09
    for druzyna in ("home", "away"):
        assert all(m["data"] < "2026-09-12" for m in k["forma"][druzyna]["ostatnie"])


def test_karta_uwagi_stale():
    k = zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", None, None)

    tekst = " ".join(k["uwagi"])
    assert "0,3" in tekst and "zaniża" in tekst                # Poisson z λ potoku zaniża gole
    assert "39" in tekst and "nie bije rynku" in tekst         # model nie bije rynku


def test_karta_nie_nazywa_poissona_czystym():
    """Liczby idą z `predict_match` z kalibracją λ, xG i limitem remisu, więc nie są „czyste”."""
    k = zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", _df(), _EVENT)

    widoczne = " ".join(k["uwagi"]) + " " + prompt_opisu(k)
    assert "czyst" not in widoczne.lower()
    # Definicja ramienia jest w uwagach stałych (LLM i właściciel widzą, co to za liczby).
    uwagi = " ".join(k["uwagi"])
    assert "bez mieszania z Bzzoiro" in uwagi
    assert "kalibracji" in uwagi and "xG" in uwagi and "40%" in uwagi
    assert "Model Poissona (osobny model, liczony bez Bzzoiro-ML)" in prompt_opisu(k)


def test_karta_statystyki_druzyn_gdy_dostepne():
    karta_druzyn = {
        "home_stats": {"team": "Alfa", "matches": 10, "gf_pg": 1.8, "ga_pg": 0.9, "rating": 7.1},
        "away_stats": {"team": "Beta", "matches": 10, "gf_pg": 1.1, "ga_pg": 1.4, "rating": 6.8},
        "top_scorers_home": [{"name": "Strzelec A", "goal_share": 0.31}],
        "top_scorers_away": [],
        "injuries_home": [{"name": "Kontuzjowany", "goal_share": 0.2}],   # NIE trafia do karty
    }

    k = zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", None, None,
                     karta_druzyn=karta_druzyn)

    s = k["statystyki"]
    assert s["home"]["gf_pg"] == 1.8 and s["away"]["rating"] == 6.8
    assert s["strzelcy_home"] == [{"name": "Strzelec A", "goal_share": 0.31}]
    assert "Kontuzjowany" not in repr(k)


def test_karta_statystyki_puste_to_none():
    puste = {"home_stats": {"team": "Alfa", "matches": None},
             "away_stats": {"team": "Beta", "matches": None},
             "top_scorers_home": [], "top_scorers_away": []}

    assert zbuduj_karte("Alfa", "Beta", "L", "2026-10-25", None, None,
                        karta_druzyn=puste)["statystyki"] is None
    assert zbuduj_karte("Alfa", "Beta", "L", "2026-10-25", None, None)["statystyki"] is None


# ── prompt ──────────────────────────────────────────────────────────────────

def _pelna_karta() -> dict:
    return zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", _df(), _EVENT)


def test_prompt_zawiera_liczby_z_karty():
    k = _pelna_karta()

    p = prompt_opisu(k)

    assert "Alfa" in p and "Beta" in p and "Test League" in p
    assert f"{k['poisson']['lambda_home']:.2f}" in p
    assert f"{k['poisson']['p1']:.1f}" in p
    assert f"{k['rynek']['p1']:.1f}" in p
    assert "60.0" in p                                   # BTTS Bzzoiro
    assert k["forma"]["home"]["ostatnie"][0]["wynik"] in p
    for linia in ("0.5", "1.5", "2.5", "3.5", "4.5"):
        assert linia in p
    assert k["uwagi"][0] in p


def test_prompt_zawiera_zakazy_i_piec_sekcji():
    p = prompt_opisu(_pelna_karta()).lower()

    for zakazane in ("kontuzj", "skład", "transfer", "wiadomo", "rekomendacj"):
        assert zakazane in p, f"prompt nie zakazuje: {zakazane}"
    assert "wyłącznie" in p
    for sekcja in ("siła i forma", "czego spodziewa się model",
                   "gdzie model różni się od rynku", "niepewność", "podsumowanie"):
        assert sekcja in p


def test_prompt_nie_zawiera_pol_spoza_karty():
    """Prompt czyta tylko pola schematu karty — obce klucze nie mogą przeciekać."""
    k = {**_pelna_karta(),
         "kontuzje_home": [{"name": "Zzyx Kontuzjowany"}],
         "lineups": "SKLAD-XYZ",
         "model": {"pw": 91.37}}

    p = prompt_opisu(k)

    assert "Zzyx" not in p and "SKLAD-XYZ" not in p and "91.37" not in p


def test_prompt_roznice_od_rynku_od_5pp():
    k = {**_pelna_karta(),
         "poisson": {"lambda_home": 1.5, "lambda_away": 1.1, "p1": 60.0, "px": 20.1,
                     "p2": 19.9, "btts": 50.0, "over25": 52.0,
                     "linie": {"0.5": 90.0, "1.5": 70.0, "2.5": 52.0, "3.5": 30.0, "4.5": 15.0}},
         "bzzoiro": {"p1": 50.0, "px": 25.0, "p2": 25.0, "over25": 55.0, "btts": 60.0},
         "rynek": {"p1": 50.0, "px": 25.0, "p2": 25.0, "over25": 50.0, "under25": 50.0}}

    p = prompt_opisu(k)

    assert "+10.0 pp" in p            # Poisson 1: 60 vs 50
    assert "-4.9 pp" not in p         # Poisson X: 20.1 vs 25 -> poniżej progu 5 pp
    assert "-5.1 pp" in p             # Poisson 2: 19.9 vs 25 -> powyżej progu
    assert "+5.0 pp" in p             # Bzzoiro Over 2.5: 55 vs 50 -> dokładnie na progu liczy się


def test_prompt_brak_roznic_gdy_brak_rynku():
    k = zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", _df(), None)

    p = prompt_opisu(k)

    assert "brak kursów rynkowych" in p.lower()


def test_prompt_sygnalizuje_brak_poissona_z_powodem():
    k = zbuduj_karte("Delta", "Epsilon", "L", "2026-10-25", _df(), _EVENT)

    p = prompt_opisu(k)

    assert k["poisson_powod"] in p


# ── opisz + cache ───────────────────────────────────────────────────────────

class _Zapytaj:
    """Atrapa Groqa: zlicza wywołania i zapamiętuje argumenty."""

    def __init__(self, odpowiedz="Opis testowy.", wyjatek=None):
        self.odpowiedz, self.wyjatek, self.wywolania = odpowiedz, wyjatek, []

    def __call__(self, prompt, max_tokens=600):
        self.wywolania.append((prompt, max_tokens))
        if self.wyjatek:
            raise self.wyjatek
        return self.odpowiedz


def test_opisz_wola_llm_z_promptem_karty_i_700_tokenami():
    k = _pelna_karta()
    z = _Zapytaj()

    assert opisz(k, zapytaj=z) == "Opis testowy."
    assert z.wywolania == [(prompt_opisu(k), 700)]


def test_opisz_drugi_raz_z_cache():
    k = _pelna_karta()
    z = _Zapytaj()

    pierwszy = opisz_z_info(k, zapytaj=z)
    drugi = opisz_z_info(k, zapytaj=z)

    assert pierwszy == ("Opis testowy.", False)
    assert drugi == ("Opis testowy.", True)
    assert len(z.wywolania) == 1


def test_opisz_inna_karta_to_inny_wpis():
    z = _Zapytaj()
    k1 = _pelna_karta()
    k2 = {**k1, "rynek": None}

    opisz(k1, zapytaj=z)
    opisz(k2, zapytaj=z)

    assert len(z.wywolania) == 2


def test_opisz_wyjatek_klienta_daje_none_i_nie_cache():
    k = _pelna_karta()

    assert opisz(k, zapytaj=_Zapytaj(wyjatek=RuntimeError("Groq i Ollama padly"))) is None

    z = _Zapytaj()
    assert opisz_z_info(k, zapytaj=z) == ("Opis testowy.", False)   # porażka nie zatruła cache


def test_opisz_blad_programisty_nie_jest_polykany():
    """Kontrakt `zapytaj_ai` to RuntimeError; KeyError z kodu ma być głośny, nie `None`."""
    with pytest.raises(KeyError):
        opisz(_pelna_karta(), zapytaj=_Zapytaj(wyjatek=KeyError("blad w kodzie")))


@pytest.mark.parametrize("odpowiedz", [None, "", "   "])
def test_opisz_pusta_odpowiedz_to_none(odpowiedz):
    assert opisz(_pelna_karta(), zapytaj=_Zapytaj(odpowiedz=odpowiedz)) is None


def test_opisz_cache_wygasa_po_6_godzinach(monkeypatch):
    zegar = {"t": 1000.0}
    monkeypatch.setattr(opis_meczu, "_teraz", lambda: zegar["t"])
    k = _pelna_karta()
    z = _Zapytaj()

    opisz(k, zapytaj=z)
    zegar["t"] += 6 * 3600 - 1
    assert opisz_z_info(k, zapytaj=z)[1] is True
    zegar["t"] += 2
    assert opisz_z_info(k, zapytaj=z)[1] is False
    assert len(z.wywolania) == 2


def test_opisz_cache_trzyma_najwyzej_200_wpisow():
    z = _Zapytaj()
    bazowa = _pelna_karta()
    karty = [{**bazowa, "home": f"Druzyna {i}"} for i in range(201)]

    for k in karty:
        opisz(k, zapytaj=z)

    assert opis_meczu.rozmiar_cache() == 200
    # Najstarszy wpis został wyparty, najnowszy został.
    assert opisz_z_info(karty[0], zapytaj=z)[1] is False
    assert opisz_z_info(karty[200], zapytaj=z)[1] is True


def test_prompt_nazywa_bzzoiro_osobnym_modelem_i_zakazuje_jezyka_wartosci():
    # 25.10: LLM pisał „Poisson jest jedynym modelem” mimo Bzzoiro w karcie
    # i „niedowartościowanie szans Śląska” — język value betu, sprzeczny z pomiarami.
    k = zbuduj_karte("Alfa", "Beta", "Test League", "2026-10-25", _df(), _EVENT)
    prompt = prompt_opisu(k)
    assert "Bzzoiro-ML (drugi, niezależny model)" in prompt
    assert "niedowartościowanie" in prompt and "Model nie bije rynku" in prompt
    assert "bez Markdownu" in prompt


def test_opis_bez_markdownu():
    tekst = "**Siła i forma**\nAlfa w formie.\n\n## Podsumowanie\nKrótko __tak__."
    opis, _ = opisz_z_info({"home": "MD", "away": "X"}, zapytaj=lambda *a, **k: tekst)
    assert opis == "Siła i forma\nAlfa w formie.\n\nPodsumowanie\nKrótko tak."
