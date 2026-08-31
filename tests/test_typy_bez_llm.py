"""A1 — typy muszą powstawać z modelu, nawet gdy warstwa LLM nic nie zwróci.

DLACZEGO: Poisson/ensemble liczy prawdopodobieństwa i wybiera typ CAŁKOWICIE bez
Groqa — a mimo to cały dzienny przebieg zapisywał zero predykcji, jeśli model
językowy nie wypisał listy `top3`. Jedna zależność opisowa decydowała o tym, czy
produkt w ogóle powstanie.

Zmierzone na produkcji dwa razy w ciągu tygodnia:
  * 15.08 — JSON od Groqa nie sparsował się → 0 predykcji przy 7 meczach po filtrach,
  * 16-22.08 — Groq wycofał `llama-3.1-8b-instant` (404) → 6 dni ciszy, `exit=0`.

Oba przebiegi miały komplet danych modelu. Brakowało wyłącznie tego, żeby ktoś
przepisał je do bazy.

Selekcja awaryjna celowo NIE jest nowym algorytmem — używa `najlepszy_typ()`,
tego samego, którym od Fazy 19 wybierane są kupony System paper-trading. Dzięki
temu typ zapisany bez LLM-a jest tym samym typem, który system i tak by postawił,
a nie trzecim wariantem selekcji do osobnego pomiaru.
"""
from __future__ import annotations

import pytest

import footstats.ai.analyzer as an
from footstats.ai.analyzer_helpers import _auto_zapisz_backtest, zbuduj_typy_z_modelu


def _mecz(gosp="Legia", gosc="Lech", **nadpisz) -> dict:
    w = {
        "gospodarz": gosp, "goscie": gosc, "liga": "Ekstraklasa",
        "data": "2026-08-23",
        "pw": 70.0, "pr": 20.0, "pp": 10.0, "o25": 30.0, "bt": 30.0,
        "pred": {"p_wygrana": 70.0, "p_remis": 20.0, "p_przegrana": 10.0,
                 "over25": 30.0, "btts": 30.0},
        "odds": {"home": 1.5, "draw": 4.2, "away": 6.0},
        "model_source": "poisson-dc",
    }
    w.update(nadpisz)
    return w


# ── budowanie typów z samego modelu ─────────────────────────────────────────

def test_typ_powstaje_z_modelu_bez_zadnego_udzialu_llm():
    """Sedno A1: mając wyłącznie liczby modelu i kursy — typ ma powstać."""
    legi = zbuduj_typy_z_modelu([_mecz()])

    assert len(legi) == 1
    assert legi[0]["mecz"] == "Legia vs Lech"
    assert legi[0]["typ"] == "1"
    assert legi[0]["kurs"] == 1.5


def test_noga_jest_oznaczona_jako_modelowa():
    """Bez znacznika nie da się później odsiać tych typów od typów z LLM-em."""
    legi = zbuduj_typy_z_modelu([_mecz()])

    assert legi[0]["_z_modelu"] is True


def test_pewnosc_to_prawdopodobienstwo_modelu():
    """Nie ma tu deklaracji LLM-a do przepisania — pewność musi być modelu."""
    legi = zbuduj_typy_z_modelu([_mecz()])

    assert legi[0]["pewnosc_pct"] == 70


def test_ev_liczone_po_podatku_i_w_procentach():
    """Format zgodny ze ścieżką Groqa (`ev_netto: 6.8`), inaczej wydruk i Telegram
    pokazałyby wartość 100x za małą."""
    legi = zbuduj_typy_z_modelu([_mecz(odds={"home": 1.9})])

    # 0.70 * 1.9 * 0.88 - 1 = +0.1704
    assert legi[0]["ev_netto"] == pytest.approx(17.0, abs=0.1)


def test_najlepszy_rynek_wygrywa_nie_pierwszy_z_brzegu():
    """Wybór to argmax po prawdopodobieństwie modelu wśród legalnych rynków."""
    w = _mecz(o25=85.0, pred={"p_wygrana": 70.0, "over25": 85.0},
              odds={"home": 1.5, "over_2_5": 1.8})

    legi = zbuduj_typy_z_modelu([w])

    assert legi[0]["typ"] == "Over 2.5"
    assert legi[0]["kurs"] == 1.8


def test_kolejnosc_od_najpewniejszego():
    slabszy = _mecz("A", "B", pw=55.0, pred={"p_wygrana": 55.0})
    mocniejszy = _mecz("C", "D", pw=82.0, pred={"p_wygrana": 82.0})

    legi = zbuduj_typy_z_modelu([slabszy, mocniejszy])

    assert [lg["mecz"] for lg in legi] == ["C vs D", "A vs B"]


def test_najwyzej_trzy_typy():
    """Ta sama pojemność co `top3` — awaryjna ścieżka nie może zalać bazy."""
    wyniki = [_mecz(f"G{i}", f"A{i}") for i in range(8)]

    assert len(zbuduj_typy_z_modelu(wyniki)) == 3


# ── filtry produkcyjne obowiązują tak samo ──────────────────────────────────

def test_mecz_bez_kursu_odpada():
    """Bez kursu nie da się ani rozliczyć, ani policzyć EV."""
    assert zbuduj_typy_z_modelu([_mecz(odds={})]) == []


def test_longshot_odpada():
    """Filtr Fazy 17.2 (kurs > 4.0) obowiązuje też bez LLM-a."""
    w = _mecz(pw=41.0, pred={"p_wygrana": 41.0}, odds={"home": 5.5})

    assert zbuduj_typy_z_modelu([w]) == []


def test_slaby_model_nie_typuje():
    """Poniżej progu selekcji (domyślnie 40%) nie ma typu — cisza jest poprawna."""
    w = _mecz(pw=30.0, pr=35.0, pp=35.0, o25=20.0, bt=20.0,
              pred={"p_wygrana": 30.0}, odds={"home": 3.0, "draw": 3.2, "away": 3.4})

    assert zbuduj_typy_z_modelu([w]) == []


def test_pusta_lista_nie_wybucha():
    assert zbuduj_typy_z_modelu([]) == []


# ── zapis do bazy ───────────────────────────────────────────────────────────

def test_typ_modelowy_ma_wlasny_kupon_type(monkeypatch):
    """Rozdzielone od `top3`, żeby dało się zmierzyć osobno: typy bez LLM-a mogą
    zachowywać się inaczej niż te, które przeszły przez opis modelu językowego."""
    zapisane = []
    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "save_prediction", lambda **kw: zapisane.append(kw) or 1)

    dane = {"top3": zbuduj_typy_z_modelu([_mecz()])}
    _auto_zapisz_backtest(dane, [_mecz()])

    assert len(zapisane) == 1
    assert zapisane[0]["kupon_type"] == "model"
    assert zapisane[0]["ai_tip"] == "1"
    assert zapisane[0]["model_source"] == "poisson-dc"
    # Zaden prompt nie powstal — "v5_json" bylby falszywym tropem przy analizie
    # wersji promptow.
    assert zapisane[0]["prompt_version"] == "model_bez_llm"


def test_typ_od_groqa_dalej_zapisuje_sie_jako_top3(monkeypatch):
    """Kontrola: znacznik nie może przekwalifikować zwykłej ścieżki."""
    zapisane = []
    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "save_prediction", lambda **kw: zapisane.append(kw) or 1)

    dane = {"top3": [{"mecz": "Legia vs Lech", "typ": "1", "kurs": 1.5}]}
    _auto_zapisz_backtest(dane, [_mecz()])

    assert zapisane[0]["kupon_type"] == "top3"
    assert zapisane[0]["prompt_version"] == "v5_json"


# ── wpięcie w `ai_analiza_pewniaczki` ───────────────────────────────────────

@pytest.fixture
def rura(monkeypatch):
    """Podstawia otoczenie analizy; notuje, co poszło do bazy."""
    stan = {"odpowiedz": '{"top3": []}', "zapisane": []}

    monkeypatch.setattr(an, "_zapytaj_typera",
                        lambda prompt, max_tokens=1500, **kw: stan["odpowiedz"])
    monkeypatch.setattr(an, "_sygnaly_summary", lambda w: "sygnaly")
    monkeypatch.setattr(an, "_buduj_opis_meczu", lambda w: f"OPIS:{w.get('gospodarz')}")
    monkeypatch.setattr(an, "_pobierz_podobne_mecze", lambda h, a, n=3: "")

    # RAG laduje sentence-transformers (~7 s na test) i nie ma wplywu na to,
    # co ta suita sprawdza — podstawiamy, zeby plik nie zdominowal czasu CI.
    import footstats.ai.rag as rag
    monkeypatch.setattr(rag, "retrieve_relevant_lessons",
                        lambda *a, **kw: [], raising=False)

    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "save_prediction",
                        lambda **kw: stan["zapisane"].append(kw) or 1)
    return stan


def test_odpowiedz_nie_do_sparsowania_i_tak_daje_predykcje(rura):
    """Awaria 15.08: JSON nie sparsował się → zero typów mimo gotowych liczb."""
    rura["odpowiedz"] = "Model napisał esej zamiast JSON-a"

    dane = an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert [z["ai_tip"] for z in rura["zapisane"]] == ["1"]
    assert dane["top3"][0]["_z_modelu"] is True


def test_surowy_tekst_zostaje_mimo_awaryjnych_typow(rura):
    """Ślad po nieudanej odpowiedzi musi przetrwać — inaczej diagnoza znika."""
    rura["odpowiedz"] = "nie-json"

    dane = an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert dane["_raw"] == "nie-json"


def test_pusty_top3_tez_uruchamia_model(rura):
    """Awaria 16-22.08 przez wycofany model dawała dokładnie pustą listę."""
    rura["odpowiedz"] = '{"top3": [], "kupon_a": {}}'

    dane = an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert len(dane["top3"]) == 1
    assert rura["zapisane"]


def test_dzien_bez_llm_jest_oznaczony(rura):
    """Bez oznaczenia nie da się odróżnić dnia z analizą od dnia awaryjnego."""
    rura["odpowiedz"] = "nie-json"

    dane = an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert dane["_top3_z_modelu"] is True
    assert "model" in (dane.get("ostrzezenia") or "").lower()


def test_dobra_odpowiedz_nie_jest_podmieniana(rura):
    """Gdy LLM zwrócił listę, awaryjna ścieżka ma milczeć.

    Kurs 9.9 jest tu znacznikiem pochodzenia: model wystawiłby 1.5 z `odds`,
    więc zachowana wartość dowodzi, że to nadal wiersz od LLM-a.
    """
    rura["odpowiedz"] = ('{"top3": [{"mecz": "Legia vs Lech", "typ": "1",'
                         ' "kurs": 9.9, "pewnosc_pct": 55}]}')

    dane = an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert dane["top3"][0]["kurs"] == 9.9
    assert "_top3_z_modelu" not in dane
    assert dane["top3"][0].get("_z_modelu") is None


def test_brak_kursow_to_dalej_brak_typow(rura):
    """Model bez kursu nie ma czego zapisać — nie wymyślamy typu na siłę."""
    rura["odpowiedz"] = "nie-json"

    dane = an.ai_analiza_pewniaczki([_mecz(odds={})], pobierz_forme=False)

    assert not dane.get("top3")
    assert rura["zapisane"] == []


def test_flaga_wylacza_sciezke_awaryjna(rura, monkeypatch):
    """Odwracalne bez redeploya — zapis do prod DB musi dać się cofnąć flagą."""
    import footstats.config as cfg
    monkeypatch.setattr(cfg, "TYPY_BEZ_LLM", False)
    rura["odpowiedz"] = "nie-json"

    dane = an.ai_analiza_pewniaczki([_mecz()], pobierz_forme=False)

    assert not dane.get("top3")
    assert rura["zapisane"] == []


# ── awarie PRZED analizą (potok dzienny) ────────────────────────────────────

@pytest.fixture
def bez_zapisu_do_bazy(monkeypatch):
    """Notuje wiersze, które poszłyby do `predictions`."""
    zapisane: list[dict] = []
    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "save_prediction", lambda **kw: zapisane.append(kw) or 1)
    return zapisane


def test_brak_klucza_api_nie_zabija_przebiegu(bez_zapisu_do_bazy, monkeypatch):
    """Brak GROQ_API_KEY kończył proces przez `sys.exit(1)` — razem z typami,
    które model policzył wcześniej i którym Groq nie jest do niczego potrzebny.

    ZMIANA UMOWY (A2/A3, 23.08): typy tu POWSTAJĄ, ale do bazy jeszcze nie idą.
    Zapis przeniesiony za weryfikację kursów (KROK 4a), żeby do `predictions` nie
    trafiały nogi bez pokrycia. Sam zapis pilnuje `test_zapis_po_weryfikacji.py`.
    """
    import footstats.daily_agent as da
    monkeypatch.setattr(an, "ai_groq_dostepny", lambda: False)

    dane = da._analizuj_groq([_mecz()])

    assert len(dane["top3"]) == 1
    assert dane["top3"][0]["_z_modelu"] is True
    assert bez_zapisu_do_bazy == [], "zapis idzie dopiero po weryfikacji"


def test_wyjatek_groqa_zostawia_czesc_modelowa(bez_zapisu_do_bazy, monkeypatch):
    """Awaria 16-22.08: Groq wycofał model → 404 na każdym przebiegu. Komunikat
    mówił „degraduje do części modelowej", ale zwracał pusty słownik."""
    import footstats.daily_agent as da
    monkeypatch.setattr(an, "ai_groq_dostepny", lambda: True)

    def wybucha(*a, **kw):
        raise RuntimeError("404 model_decommissioned")

    monkeypatch.setattr(an, "ai_analiza_pewniaczki", wybucha)

    dane = da._analizuj_groq([_mecz()])

    assert len(dane["top3"]) == 1
    assert dane["_top3_z_modelu"] is True
    # Jak wyżej: typy są, zapis czeka na weryfikację kursów.
    assert bez_zapisu_do_bazy == []


def test_awaria_groqa_bez_kursow_nie_zapisuje_nic(bez_zapisu_do_bazy, monkeypatch):
    """Degradacja nie może oznaczać typowania meczów bez kursu — nawet w pamięci."""
    import footstats.daily_agent as da
    monkeypatch.setattr(an, "ai_groq_dostepny", lambda: False)

    dane = da._analizuj_groq([_mecz(odds={})])

    assert dane == {}
    assert bez_zapisu_do_bazy == []


def test_detektor_cichej_awarii_widzi_typy_z_modelu(monkeypatch):
    """`wykryj_anomalie_runu` alarmowało „ZERO predykcji" — po A1 dzień z typami
    z modelu jest dniem udanym, nie awarią."""
    import footstats.daily_agent as da

    dane = {"top3": zbuduj_typy_z_modelu([_mecz()])}

    assert da.wykryj_anomalie_runu(42, 7, 0, ma_typy=bool(dane["top3"])) is None


# ── ostatnie ciche miejsce w scieżce zapisu ─────────────────────────────────

def test_nieudany_zapis_jest_glosny_ale_nie_zabija_reszty(monkeypatch, caplog):
    """`predictions` to nie telemetria — to jedyny zapis tego, co system wytypował.

    Blok `except Exception: pass` wokół `save_prediction` był ostatnim miejscem,
    w którym cały dzień mógł zniknąć bez śladu: awaria bazy dawała ten sam obraz
    co dzień bez okazji. Przebiegu nadal nie przerywamy — kolejne nogi mają się
    zapisać — ale awaria trafia do logu jako ERROR.
    """
    import logging

    import footstats.core.backtest as bt

    zapisane = []

    def kaprysny(**kw):
        if kw["team_home"] == "A":
            raise RuntimeError("baza padla")
        zapisane.append(kw["team_home"])
        return 1

    monkeypatch.setattr(bt, "save_prediction", kaprysny)

    dane = {"top3": [{"mecz": "A vs B", "typ": "1", "kurs": 1.5},
                     {"mecz": "C vs D", "typ": "1", "kurs": 1.5}]}
    with caplog.at_level(logging.ERROR, logger="footstats.ai.analyzer_helpers"):
        _auto_zapisz_backtest(dane, [_mecz("A", "B"), _mecz("C", "D")])

    assert zapisane == ["C"], "awaria jednej nogi nie moze zabic pozostalych"
    assert any("baza padla" in r.getMessage() for r in caplog.records),         "awaria zapisu musi byc widoczna w logach"


# ── dalsza droga typu przez potok ───────────────────────────────────────────

def test_typ_z_modelu_przechodzi_weryfikacje_kursow():
    """Typ awaryjny musi przeżyć KROK 4, inaczej zapis w bazie zostaje z kursem
    sprzed weryfikacji, a noga i tak nie trafi do uzgodnienia."""
    import footstats.daily_agent as da

    w = _mecz()
    indeks = {(da._norm("Legia"), da._norm("Lech")): w}
    dane = {"top3": zbuduj_typy_z_modelu([w])}

    da._weryfikuj_kupony(dane, indeks)

    assert len(dane["top3"]) == 1
    assert dane["top3"][0]["_verified"] is True
    assert dane["top3"][0]["kurs"] == 1.5


def test_zweryfikowany_typ_z_modelu_idzie_do_uzgodnienia():
    """`_uzgodnij_predykcje` dosyła realny kurs do `predictions` — noga bez
    poprawnego kształtu wypadłaby z tego kroku po cichu."""
    import footstats.daily_agent as da

    w = _mecz()
    indeks = {(da._norm("Legia"), da._norm("Lech")): w}
    dane = {"top3": zbuduj_typy_z_modelu([w])}
    da._weryfikuj_kupony(dane, indeks)

    nogi = da._zbierz_ocalale_nogi(dane)

    assert nogi == [{"team_home": "Legia", "team_away": "Lech",
                     "match_date": "2026-08-23", "ai_tip": "1", "odds": 1.5}]
