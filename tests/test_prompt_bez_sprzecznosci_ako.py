"""Prompt nie moze zadac naraz singla i akumulatora.

ZMIERZONE 01.09 — odtworzenie KROKU 3 na PRAWDZIWYCH kandydatach (Torino/Monza,
Stoke/Norwich, Birmingham/Southampton, Londrina/Juventude). Model oddal komplet
pustych kuponow i napisal wprost dlaczego:

    "Zaden z podanych meczow nie spelnia wymogow minimalnej pewnosci (>=50%)
     oraz minimalnego kursu (>=1.80) dla pojedynczego zakladu."

Progu 1.80 nie ma w ZAKAZACH — tam stoi `Leg odds < 1.20: NEVER`. Wchodzil przez
`_buduj_cel_kuponow`, ktory zostal z ery AKO i mowil doslownie:

    Zbuduj 2 kupony AKO z podanymi celami.
    Zasada singla: pojedyncza noga tylko gdy kurs >= 1.80. Kurs 1.35-1.80 tylko jako noga AKO.
    Min 3 nogi, max 6 nog na kupon.
    WAZNE: aby osiagnac wysoki kurs, musisz zebrac 4-6 nog — nie buduj singla ani 2-noznego kuponu!

a blok ZAKAZOW dodany 31.08 mowil dokladnie odwrotnie:

    One slip = EXACTLY 1 leg (single). No accumulators (AKO).

Model rozstrzygnal sprzecznosc na korzysc surowszej reguly i odrzucil KAZDY mecz
z kursem 1.31-1.79 — czyli caly nasz material. `phase='final'` nie powstal.

To TRZECIA kopia tej samej reguly. Docstring `test_wyjscie_llm_nie_urywa_sie`
ostrzegal po drugiej: "Dwie kopie tej samej reguly rozjezdzaja sie po cichu".
Dlatego ponizej nie sprawdzamy juz obecnosci konkretnych zdan, tylko ZGODNOSC:
prog kursu wymieniony gdziekolwiek w promptcie musi byc ten sam.
"""
from __future__ import annotations

import re

import pytest

from footstats.ai.analyzer_helpers import _buduj_cel_kuponow
from footstats.ai.prompts import build_pewniaczki_prompt


def _prompt(cel_a=50.0, cel_b=25.0, stawka=10.0, n_mecze=4) -> str:
    return build_pewniaczki_prompt(
        n_mecze=n_mecze, sygnaly="", kalibracja_str="", feedback_str="",
        mecze_opisy_text="<MECZE>",
        cel_kuponow_text=_buduj_cel_kuponow(cel_a, cel_b, stawka),
    )


# ── sedno: zero sprzecznosci singiel vs AKO ─────────────────────────────────

@pytest.mark.parametrize("cel_a,cel_b", [(50.0, 25.0), (None, None), (50.0, None)])
@pytest.mark.parametrize("fraza", [
    "kupony AKO", "4-6 nóg", "Min 3 nogi", "nie buduj singla", "noga AKO",
])
def test_zadna_wersja_promptu_nie_zada_akumulatora(cel_a, cel_b, fraza):
    """Kazda galaz `_buduj_cel_kuponow` musi byc zgodna z zakazem AKO."""
    tekst = _prompt(cel_a=cel_a, cel_b=cel_b)

    assert fraza.lower() not in tekst.lower(), (
        f"prompt zada akumulatora ({fraza!r}), a ZAKAZY mowia 'No accumulators (AKO)'"
    )


@pytest.mark.parametrize("cel_a,cel_b", [(50.0, 25.0), (None, None)])
def test_zakaz_akumulatorow_dalej_stoi(cel_a, cel_b):
    """Kontrola negatywna: usuwamy sprzecznosc, nie sam zakaz."""
    tekst = _prompt(cel_a=cel_a, cel_b=cel_b)

    assert "EXACTLY 1 leg" in tekst
    assert "No accumulators" in tekst


# ── prog kursu: jedna liczba, nie dwie ──────────────────────────────────────

# Prog = liczba przy OPERATORZE POROWNANIA, nie kazda liczba obok slowa "kurs".
# Bez tego warunku wzorzec lapal takze przyklady ze schematu JSON (`"kurs": 1.48`)
# i test mierzylby ksztalt kontraktu zamiast regul selekcji.
_PROG_KURSU = re.compile(
    r"(?:kurs|odds)[^.\n]{0,30}?(?:>=|<=|>|<|min\.?|minimum|NEVER|tylko gdy)"
    r"[^.\n]{0,20}?(\d[.,]\d{1,2})",
    re.IGNORECASE,
)


@pytest.mark.parametrize("cel_a,cel_b", [(50.0, 25.0), (None, None)])
def test_prompt_podaje_JEDEN_prog_kursu_nogi(cel_a, cel_b):
    """Dwa rozne progi w jednym promptcie = model wybiera surowszy i odrzuca wszystko."""
    tekst = _prompt(cel_a=cel_a, cel_b=cel_b)

    progi = {m.group(1) for m in _PROG_KURSU.finditer(tekst)}
    # 1.20 to jedyny prog nogi; 2.00 z reguly "pewnosc>=75% i kurs>2.00" to
    # sufit sprzecznosci, nie prog dopuszczenia — dlatego wolno mu zostac.
    zabronione = progi - {"1.20", "2.00"}
    assert not zabronione, (
        f"prompt niesie dodatkowe progi kursu {sorted(zabronione)} obok 1.20 — "
        f"model 01.09 wybral 1.80 i odrzucil kazdy mecz ponizej"
    )


def test_prog_1_80_zniknal_z_generatora_celu():
    """Bezposrednio na zrodle, zeby awaria wskazywala plik do poprawy."""
    for cel_a, cel_b in [(50.0, 25.0), (None, None)]:
        tekst = _buduj_cel_kuponow(cel_a, cel_b, 10.0)
        assert "1.80" not in tekst, f"cel_a={cel_a}: prog 1.80 dalej w sekcji celow"


# ── slownictwo: model nie ma wymyslac wlasnych kluczy ───────────────────────
#
# Ten sam przebieg 01.09 zwrocil `{"ostrzezenia": ..., "slips": [...]}`.
# Klucza `slips` nie ma w schemacie — parser szuka `top3`, wiec nawet gdyby
# model cos wytypowal, wynik i tak zostalby odrzucony. Zrodlo: ZAKAZY mowily
# o "slip", a schemat o "kupon_a". Model wybral slownictwo zakazow.

def test_prompt_nie_uzywa_nazwy_spoza_schematu():
    tekst = _prompt()

    assert "slip" not in tekst.lower(), (
        "prompt uzywa slowa 'slip', ktorego nie ma w schemacie JSON — 01.09 model "
        "odpowiedzial kluczem `slips` zamiast `top3`/`kupon_a` i parser to odrzucil"
    )


@pytest.mark.parametrize("klucz", ["top3", "kupon_a", "zdarzenia", "ostrzezenia"])
def test_schemat_dalej_kompletny(klucz):
    assert klucz in _prompt()
