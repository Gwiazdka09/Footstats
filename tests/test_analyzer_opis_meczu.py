"""test_analyzer_opis_meczu.py — _buduj_opis_meczu: kontekst meczu dla Groqa.

PO CO: `ai/analyzer.py` mial 7% pokrycia, a ta jedna funkcja to ~200 instrukcji
czystego skladania stringa, ktory LECI DO PROMPTU. Kazde zgubione pole = model
podejmuje decyzje bez tej informacji i nikt tego nie zauwazy — prompt zawsze
"wyglada dobrze".

Funkcja obsluguje DWA formaty wejsciowe:
  * quick_picks  — plaskie pw/pr/pp/bt/o25 (metoda ML),
  * weekly_picks — zagniezdzone `pred` z lambdami (metoda POISSON).
Rozjazd miedzy nimi juz raz kosztowal projekt cala galaz Poissona
(patrz [[project-cel-b-rootcause]] bug 3), wiec oba sa tu sprawdzone.
"""
from __future__ import annotations

import pytest

from footstats.ai.analyzer import _buduj_opis_meczu


@pytest.fixture(autouse=True)
def bez_rag(monkeypatch):
    """RAG dobija do bazy — domyslnie wylaczony, ma wlasny test."""
    import footstats.ai.rag as rag
    monkeypatch.setattr(rag, "pobierz_rag_kontekst", lambda w: "")


def _mecz(**nadpisz) -> dict:
    baza = {"gospodarz": "Legia", "goscie": "Lech", "liga": "Ekstraklasa",
            "data": "2026-08-02", "godzina": "14:45",
            "pw": 45.0, "pr": 27.0, "pp": 28.0, "bt": 52.0, "o25": 48.0}
    baza.update(nadpisz)
    return baza


def _poisson(**pred_extra) -> dict:
    pred = {"p_wygrana": 60.0, "p_remis": 22.0, "p_przegrana": 18.0,
            "btts": 50.0, "over25": 55.0, "pewnosc": 70}
    pred.update(pred_extra)
    return _mecz(metoda="POISSON", pred=pred)


# ── naglowek i podstawy ─────────────────────────────────────────────────────

def test_naglowek_ma_druzyny_lige_date_i_metode():
    linia = _buduj_opis_meczu(_mecz()).splitlines()[0]
    assert "Legia vs Lech" in linia
    assert "[Ekstraklasa]" in linia
    assert "2026-08-02" in linia and "14:45" in linia
    assert "[metoda:ML]" in linia


def test_brakujace_pola_daja_znaki_zapytania_nie_crash():
    linia = _buduj_opis_meczu({}).splitlines()[0]
    assert "? vs ?" in linia


def test_linia_ml_ma_wszystkie_rynki():
    opis = _buduj_opis_meczu(_mecz())
    assert "ML: 1=45% X=27% 2=28%" in opis
    assert "BTTS=52%" in opis
    assert "Over2.5=48%" in opis


def test_poisson_czyta_prawdopodobienstwa_z_pred_nie_z_plaskich():
    """Sedno rozjazdu formatow: przy metoda=POISSON liczby ida z `pred`."""
    opis = _buduj_opis_meczu(_poisson())
    assert "1=60% X=22% 2=18%" in opis, "wzieto plaskie pola zamiast pred"


def test_ml_spada_na_pred_gdy_plaskie_puste():
    w = {"gospodarz": "A", "goscie": "B", "pred": {"p_wygrana": 33.0}}
    assert "1=33%" in _buduj_opis_meczu(w)


# ── lambdy i dominacja ──────────────────────────────────────────────────────

def test_dominacja_gospodarza():
    opis = _buduj_opis_meczu(_poisson(lambda_g=2.4, lambda_a=1.0))
    assert "λg=2.4 λa=1.0" in opis
    assert "Legia dominuje (2.4x)" in opis


def test_dominacja_gosci():
    opis = _buduj_opis_meczu(_poisson(lambda_g=0.8, lambda_a=2.0))
    assert "Lech dominuje" in opis


def test_wyrownane_gdy_lambdy_zblizone():
    assert "wyrównane" in _buduj_opis_meczu(_poisson(lambda_g=1.3, lambda_a=1.2))


def test_brak_linii_poisson_bez_lambd():
    assert "POISSON:" not in _buduj_opis_meczu(_poisson())


def test_lambda_zero_nie_dzieli_przez_zero():
    _buduj_opis_meczu(_poisson(lambda_g=1.5, lambda_a=0))   # nie rzuca


# ── cross-walidacja z Bzzoiro ───────────────────────────────────────────────

def test_porownanie_poisson_vs_bzzoiro():
    w = _poisson()
    w["bzz_info"] = {"cross": {"ml_1": 45.0}}
    opis = _buduj_opis_meczu(w)
    assert "PORÓWNANIE: Poisson=60% vs Bzz=45%" in opis
    assert "+15% Poisson wyżej" in opis


def test_alert_rozbieznosci():
    w = _poisson()
    w["bzz_info"] = {"cross": {"ml_1": 20.0, "alert": True}}
    assert "ROZBIEŻNOŚĆ" in _buduj_opis_meczu(w)


def test_brak_porownania_dla_ml():
    w = _mecz()
    w["bzz_info"] = {"cross": {"ml_1": 45.0}}
    assert "PORÓWNANIE" not in _buduj_opis_meczu(w)


# ── czynniki analityczne ────────────────────────────────────────────────────

@pytest.mark.parametrize("klucz,podklucz,oczekiwane", [
    ("h2h_g", "patent", "PATENT"),
    ("h2h_g", "zemsta", "ZEMSTA"),
    ("fortress_g", "fortress", "TWIERDZA"),
    ("heur_g", "rotacja", "ROTACJA"),
    ("heur_g", "zmeczenie", "ZMECZENIE"),
    ("heur_a", "rotacja", "ROTACJA"),
    ("heur_a", "zmeczenie", "ZMECZENIE"),
])
def test_kazdy_czynnik_trafia_do_opisu(klucz, podklucz, oczekiwane):
    opis = _buduj_opis_meczu(_poisson(**{klucz: {podklucz: True}}))
    assert oczekiwane in opis


def test_brak_linii_czynnikow_gdy_zadnego_nie_ma():
    assert "CZYNNIKI:" not in _buduj_opis_meczu(_poisson())


def test_waznosc_pomija_status_normal():
    """NORMAL to szum — ma nie zasmiecac promptu."""
    opis = _buduj_opis_meczu(_poisson(imp_g={"status": "NORMAL"},
                                      imp_a={"status": "NORMAL"}))
    assert "WAŻNOŚĆ" not in opis


def test_waznosc_pokazuje_niestandardowy_status_z_komentarzem():
    opis = _buduj_opis_meczu(_poisson(
        imp_g={"status": "FINAL", "komentarz": "walka o tytuł – ostatnia kolejka"}))
    assert "WAŻNOŚĆ" in opis
    assert "FINAL" in opis
    assert "ostatnia kolejka" in opis, "komentarz ma być przycięty po myślniku"


def test_forma_i_pewnosc():
    opis = _buduj_opis_meczu(_poisson(forma_g=2.1, forma_a=1.4, h2h_g={"n_h2h": 6}))
    assert "FORMA(pkt/m)" in opis and "2.10" in opis
    assert "PEWNOŚĆ: 70% (n_h2h=6)" in opis


# ── konteksty zewnetrzne ────────────────────────────────────────────────────

def test_forma_sofascore():
    assert "FORMA_SOFA" in _buduj_opis_meczu(_mecz(sofa_forma_g="WWDLW"))


def test_match_context_xg_tabela_absencje():
    opis = _buduj_opis_meczu(_mecz(match_context={
        "home_xg_last3": [1.8, 2.1, 0.9], "away_xg_last3": [1.1],
        "home_table_pos": 2, "away_table_pos": 7,
        "home_absences": ["Kowalski"], "away_absences": [],
    }))
    assert "xG_LAST3" in opis
    assert "TABELA: Legia=#2" in opis
    assert "KONTEKST_ABSENCJE" in opis and "Kowalski" in opis


def test_kontuzje_i_absencje_flashscore():
    opis = _buduj_opis_meczu(_mecz(sofa_kontuzje_g="Nowak (uraz)",
                                   fs_absencje_a="Zieliński"))
    assert "KONTUZJE" in opis and "Nowak" in opis
    assert "ABSENCJE_FS" in opis and "Zieliński" in opis


def test_sedzia_i_stadion():
    opis = _buduj_opis_meczu(_mecz(referee_name="Marciniak", referee_avg_y=4.2,
                                   referee_signal="KARTKOWY", stadium="Łazienkowska"))
    assert "SĘDZIA: Marciniak (avg: 4.2) [KARTKOWY]" in opis
    assert "STADION: Łazienkowska" in opis


# ── kursy i EV ──────────────────────────────────────────────────────────────

def test_kursy_trafiaja_do_opisu():
    opis = _buduj_opis_meczu(_mecz(odds={"home": 2.1, "draw": 3.4, "away": 3.6}))
    assert "KURSY: 1=2.1 X=3.4 2=3.6" in opis


def test_ev_liczone_tylko_dla_dodatnich():
    """pw=45% przy kursie 3.0 → EV +35%; pp=28% przy 2.0 → EV ujemne, pomijane."""
    opis = _buduj_opis_meczu(_mecz(odds={"home": 3.0, "away": 2.0}))
    assert "EV(brutto)" in opis
    assert "1=+35%" in opis
    assert "2=" not in opis.split("EV(brutto)")[1]


def test_kurs_z_przecinkiem_dziesietnym():
    """Zrodla europejskie oddaja '3,00' — ma byc sparsowane, nie pominiete."""
    assert "1=+35%" in _buduj_opis_meczu(_mecz(odds={"home": "3,00"}))


def test_niepoprawny_kurs_nie_wywala_opisu():
    opis = _buduj_opis_meczu(_mecz(odds={"home": "brak", "draw": None}))
    assert "EV(brutto)" not in opis


def test_kursy_z_bzz_info_gdy_brak_na_wierzchu():
    w = _mecz()
    w["bzz_info"] = {"odds": {"home": 1.9}}
    assert "KURSY: 1=1.9" in _buduj_opis_meczu(w)


# ── bet builder i scout ─────────────────────────────────────────────────────

def test_bet_builder_sugestie():
    assert "bet_builder_sugestie" in _buduj_opis_meczu(
        _mecz(bet_builder=["1 + Over 1.5", "BTTS"]))


def test_bb_z_kursem_przycina_do_szesciu():
    opis = _buduj_opis_meczu(_mecz(bet_builder_kombinacje=[f"k{i}" for i in range(10)]))
    assert "bb_z_kursem" in opis
    assert "k6" not in opis, "lista ma być przycięta do 6 pozycji"


def test_scout_bierze_tylko_ev_powyzej_progu_i_sortuje():
    opis = _buduj_opis_meczu(_mecz(scout={"oceny": [
        {"typ": "Over 2.5", "ev": 0.02},     # poniżej progu 0.03
        {"typ": "BTTS",     "ev": 0.12},
        {"typ": "1X",       "ev": 0.30},
    ]}))
    assert "SCOUT_EV" in opis
    linia = [ln for ln in opis.splitlines() if "SCOUT_EV" in ln][0]
    assert linia.index("1X") < linia.index("BTTS"), "brak sortowania malejąco po EV"
    assert "Over 2.5" not in linia


def test_scout_bez_wartosciowych_nie_dodaje_linii():
    assert "SCOUT_EV" not in _buduj_opis_meczu(
        _mecz(scout={"oceny": [{"typ": "X", "ev": 0.01}]}))


# ── RAG ─────────────────────────────────────────────────────────────────────

def test_rag_dopisuje_historie(monkeypatch):
    import footstats.ai.rag as rag
    monkeypatch.setattr(rag, "pobierz_rag_kontekst",
                        lambda w: "3 podobne mecze: 2x Over trafione")
    assert "HISTORIA: 3 podobne mecze" in _buduj_opis_meczu(_mecz())


def test_awaria_rag_nie_psuje_opisu(monkeypatch):
    import footstats.ai.rag as rag

    def _wybuch(w):
        raise KeyError("brak klucza")

    monkeypatch.setattr(rag, "pobierz_rag_kontekst", _wybuch)
    assert "Legia vs Lech" in _buduj_opis_meczu(_mecz())
