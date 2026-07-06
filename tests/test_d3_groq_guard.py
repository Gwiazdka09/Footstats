"""D3 / Cel B bug 2 — guard selekcji Groq (koryguj_tip_wg_modelu).

Groq wybierał wyjazdy/remisy przeciw faworytom (tip=2 12.5% trafność). Guard: gdy Groq tip
1X2 ma prob modelu skrajnie niski (<15%) → override na argmax modelu. Konserwatywny.
"""
from footstats.ai.analyzer_helpers import koryguj_tip_wg_modelu


def test_override_gdy_groq_wyjazd_przy_faworycie_gospodarzu():
    # Groq tip=2 (wyjazd), model: dom 70 / remis 22 / wyjazd 8 → override na "1".
    tip, ov = koryguj_tip_wg_modelu("2", pw=70.0, pr=22.0, pp=8.0)
    assert tip == "1" and ov is True


def test_brak_override_gdy_tip_zgodny_z_modelem():
    # Groq tip=2, model wyjazd 40% (akceptowalne) → bez zmian.
    tip, ov = koryguj_tip_wg_modelu("2", pw=30.0, pr=30.0, pp=40.0)
    assert tip == "2" and ov is False


def test_brak_override_gdy_tip_jest_argmax():
    # Groq tip=1 = argmax modelu → bez zmian (nawet jakby <15, ale tu nie jest).
    tip, ov = koryguj_tip_wg_modelu("1", pw=55.0, pr=25.0, pp=20.0)
    assert tip == "1" and ov is False


def test_nie_rusza_nie_1x2():
    # Over/BTTS poza zakresem guardu.
    for t in ("Over 2.5", "BTTS", "Under 2.5"):
        tip, ov = koryguj_tip_wg_modelu(t, pw=10.0, pr=10.0, pp=80.0)
        assert tip == t and ov is False


def test_nie_rusza_gdy_brak_prob_modelu():
    # Mecz spoza coverage (brak pw/pr/pp) → nie ruszamy (None).
    tip, ov = koryguj_tip_wg_modelu("2", pw=None, pr=None, pp=None)
    assert tip == "2" and ov is False


def test_remis_skrajny_tez_override():
    # Groq tip=X przy remis 9% i dom 60% → override na "1".
    tip, ov = koryguj_tip_wg_modelu("X", pw=60.0, pr=9.0, pp=31.0)
    assert tip == "1" and ov is True


def test_default_prog_33_lapie_umiarkowany_rozjazd():
    # Audyt 07-06: default 33 (nie 15) łapie umiarkowane rozjazdy. Groq tip=2 przy
    # wyjazd 25% (25<33), dom 45% → override na "1". Przy starym 15 NIE ruszał.
    tip, ov = koryguj_tip_wg_modelu("2", pw=45.0, pr=30.0, pp=25.0)
    assert tip == "1" and ov is True
    # a przy prog_min=15 (stare) — bez zmian
    tip2, ov2 = koryguj_tip_wg_modelu("2", pw=45.0, pr=30.0, pp=25.0, prog_min=15.0)
    assert tip2 == "2" and ov2 is False
