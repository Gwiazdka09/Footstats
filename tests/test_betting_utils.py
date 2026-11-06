"""Unit tests for utils/betting.py — oblicz_tip_correct and typy_zaklady."""
from footstats.core.rynki_dziennika import czy_rozliczalny
from footstats.utils.betting import oblicz_tip_correct


class TestObliczTipCorrect:
    # ── 1/X/2 from score strings ──────────────────────────────────────────────

    def test_home_win_tip1_correct(self):
        assert oblicz_tip_correct("1", "2-1") == 1

    def test_home_win_tip1_wrong(self):
        assert oblicz_tip_correct("2", "2-1") == 0

    def test_draw_tipX_correct(self):
        assert oblicz_tip_correct("X", "1-1") == 1

    def test_draw_tipX_wrong(self):
        assert oblicz_tip_correct("1", "1-1") == 0

    def test_away_win_tip2_correct(self):
        assert oblicz_tip_correct("2", "0-1") == 1

    # ── Double chance ─────────────────────────────────────────────────────────

    def test_1x_home_win(self):
        assert oblicz_tip_correct("1X", "2-0") == 1

    def test_1x_draw(self):
        assert oblicz_tip_correct("1X", "0-0") == 1

    def test_1x_away_loss(self):
        assert oblicz_tip_correct("1X", "0-2") == 0

    def test_x2_draw(self):
        assert oblicz_tip_correct("X2", "0-0") == 1

    def test_x2_away_win(self):
        assert oblicz_tip_correct("X2", "1-2") == 1

    def test_x2_home_win(self):
        assert oblicz_tip_correct("X2", "2-0") == 0

    def test_12_home_win(self):
        assert oblicz_tip_correct("12", "2-1") == 1

    def test_12_draw(self):
        assert oblicz_tip_correct("12", "0-0") == 0

    # ── Over / Under ──────────────────────────────────────────────────────────

    def test_over25_correct(self):
        assert oblicz_tip_correct("OVER 2.5", "2-1") == 1  # 3 goals

    def test_over25_wrong(self):
        assert oblicz_tip_correct("OVER 2.5", "1-1") == 0  # 2 goals

    def test_under25_correct(self):
        assert oblicz_tip_correct("UNDER 2.5", "1-0") == 1  # 1 goal

    def test_under25_wrong(self):
        assert oblicz_tip_correct("UNDER 2.5", "2-1") == 0  # 3 goals

    # ── BTTS ──────────────────────────────────────────────────────────────────

    def test_btts_both_score(self):
        assert oblicz_tip_correct("BTTS", "1-1") == 1

    def test_btts_one_nil(self):
        assert oblicz_tip_correct("BTTS", "2-0") == 0

    def test_btts_no(self):
        assert oblicz_tip_correct("BTTS NO", "2-0") == 1

    def test_no_btts_both_score(self):
        assert oblicz_tip_correct("NO BTTS", "1-1") == 0

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_no_result_returns_none(self):
        assert oblicz_tip_correct("1", None) is None

    def test_empty_result_returns_none(self):
        assert oblicz_tip_correct("1", "") is None

    def test_tuple_result(self):
        assert oblicz_tip_correct("1", (2, 1)) == 1

    def test_list_result(self):
        assert oblicz_tip_correct("2", [0, 1]) == 1

    def test_aet_nie_jest_rozliczany(self):
        """ZMIANA INTENCJI 17.08. Wczesniej sufiks (AET) byl OBCINANY i typ
        rozliczany po dogrywce — ale rynki 90-minutowe tak sie nie rozliczaja,
        a wyniku regulaminowego w tym zapisie NIE MA.

        Stare zachowanie bylo tez niespojne: "2-1 (AET)" rozliczalo sie jako
        wygrana gospodarza, a "2-1aet" (bez nawiasu) zwracalo None. Ten sam mecz,
        dwa werdykty, zaleznie od zapisu zrodla. Szczegoly i uzasadnienie:
        `tests/test_wynik_dogrywka.py`.
        """
        assert oblicz_tip_correct("1", "2-1 (AET)") is None

    def test_unknown_tip_returns_none(self):
        assert oblicz_tip_correct("UNKNOWN", "2-1") is None

    def test_invalid_score_returns_none(self):
        assert oblicz_tip_correct("1", "bad-score") is None

    def test_raw_result_1(self):
        assert oblicz_tip_correct("1", "1") == 1

    def test_raw_result_X(self):
        assert oblicz_tip_correct("X", "X") == 1

    def test_case_insensitive_tip(self):
        assert oblicz_tip_correct("over 2.5", "2-1") == 1

    # ── Handicap europejski (FAZA 20) ─────────────────────────────────────────

    def test_handicap_home_minus15_hit(self):
        assert oblicz_tip_correct("1 (-1.5)", "3-1") == 1   # margin 2

    def test_handicap_home_minus15_miss(self):
        assert oblicz_tip_correct("1 (-1.5)", "2-1") == 0   # margin 1

    def test_handicap_away_plus15_hit(self):
        assert oblicz_tip_correct("2 (+1.5)", "2-1") == 1   # przegrał o 1, +1.5 ratuje

    def test_handicap_away_plus15_miss(self):
        assert oblicz_tip_correct("2 (+1.5)", "3-1") == 0

    def test_handicap_home_minus05_equiv_win(self):
        assert oblicz_tip_correct("1 (-0.5)", "1-0") == 1
        assert oblicz_tip_correct("1 (-0.5)", "1-1") == 0

    def test_handicap_brak_wyniku_none(self):
        assert oblicz_tip_correct("1 (-1.5)", "1") is None  # brak bramek

    # ── Parzyste / nieparzyste (FAZA 20) ──────────────────────────────────────

    def test_parzyste_hit(self):
        assert oblicz_tip_correct("PARZYSTE", "1-1") == 1   # 2 gole

    def test_parzyste_zero_to_parzyste(self):
        assert oblicz_tip_correct("PARZYSTE", "0-0") == 1   # 0 = parzyste

    def test_nieparzyste_hit(self):
        assert oblicz_tip_correct("NIEPARZYSTE", "2-1") == 1  # 3 gole

    def test_parzyste_miss(self):
        assert oblicz_tip_correct("PARZYSTE", "2-1") == 0

    # ── BetBuilder combo = koniunkcja członów (krytyczny fix) ─────────────────

    def test_bb_combo_oba_trafione(self):
        assert oblicz_tip_correct("BB: 1 + Over 1.5", "3-1") == 1

    def test_bb_combo_pierwszy_czlon_przegral(self):
        # gospodarz PRZEGRAL (1-3) → combo przegrane mimo Over
        assert oblicz_tip_correct("BB: 1 + Over 1.5", "1-3") == 0

    def test_bb_combo_drugi_czlon_przegral(self):
        # 1 wygral (3-0) ale Under 3.5 też trafione (total 3) → wygrane
        assert oblicz_tip_correct("BB: 1 + Under 3.5", "3-0") == 1
        # 1 wygral ale total 4 > 3.5 → Under nietrafione → przegrane
        assert oblicz_tip_correct("BB: 1 + Under 3.5", "3-1") == 0

    def test_bb_combo_btts(self):
        assert oblicz_tip_correct("BB: 2 + BTTS", "1-2") == 1   # gość wygrał + oba strzeliły
        assert oblicz_tip_correct("BB: 2 + BTTS", "2-1") == 0   # gość przegrał

    def test_bb_combo_czlon_nierozliczalny_none(self):
        # nieznany człon → całość None (nie zgaduj)
        assert oblicz_tip_correct("BB: 1 + Zawodnik gola", "2-1") is None

    # ── Nazwane rynki BetBuilder (betbuilder_rules) — muszą się rozliczać ──────

    # ── Rozwlekly zapis 1X2 z opisem w nawiasie (typ #249 z produkcji) ────────

    def test_wariant_rozwlekly_2_wygrana_goscia(self):
        # dokladny wiersz #249 z produkcji: "2 (wygrana gościa)" + "0-3"
        assert oblicz_tip_correct("2 (wygrana gościa)", "0-3") == 1

    def test_wariant_rozwlekly_1_wygrana_gospodarza(self):
        assert oblicz_tip_correct("1 (wygrana gospodarza)", "2-1") == 1
        assert oblicz_tip_correct("1 (wygrana gospodarza)", "0-3") == 0

    def test_wariant_rozwlekly_x_remis(self):
        assert oblicz_tip_correct("X (remis)", "1-1") == 1
        assert oblicz_tip_correct("X (remis)", "2-1") == 0

    def test_regula_nawiasowa_nie_przechwytuje_innych_rynkow(self):
        """Antyregresja: nawias w typie 1X2 nie moze rozszerzyc sie na rynki,
        ktore nawiasu w ogole nie uzywaja jako czesci typu — musza rozliczac
        sie DOKLADNIE tak jak przed dodaniem rodziny "N (opis)"."""
        assert oblicz_tip_correct("OVER 2.5", "2-1") == 1
        assert oblicz_tip_correct("BTTS", "1-1") == 1
        assert oblicz_tip_correct("Handicap +1 Gość", "1-1") == 1
        assert oblicz_tip_correct("Handicap +1 Gość", "2-0") == 0

    def test_nawias_w_typie_nie_rozbraja_kontroli_nawiasu_w_wyniku(self):
        # "1-1 (Pen- 4-5)" jest nierozliczalne (karne) niezaleznie od tego,
        # ze sam TYP tez ma nawias — kontrola wyniku ma pierwszenstwo.
        assert oblicz_tip_correct("2 (wygrana gościa)", "1-1 (Pen- 4-5)") is None

    def test_gospodarz_over_05_liczy_gole_gospodarza_nie_total(self):
        # 0-1: total=1 (>0.5) ale gospodarz=0 → NIE trafione (regresja: łapało total)
        assert oblicz_tip_correct("Gospodarz Over 0.5", "0-1") == 0
        assert oblicz_tip_correct("Gospodarz Over 0.5", "1-0") == 1

    def test_gosc_over_15_liczy_gole_goscia(self):
        assert oblicz_tip_correct("Gość Over 1.5", "0-2") == 1
        assert oblicz_tip_correct("Gość Over 1.5", "2-1") == 0

    def test_handicap_minus1_gospodarz(self):
        assert oblicz_tip_correct("Handicap -1 Gospodarz", "3-1") == 1   # margin 2
        assert oblicz_tip_correct("Handicap -1 Gospodarz", "2-1") == 0   # margin 1

    def test_handicap_plus1_gosc(self):
        assert oblicz_tip_correct("Handicap +1 Gość", "1-1") == 1   # h-a=0 <=1
        assert oblicz_tip_correct("Handicap +1 Gość", "2-0") == 0   # h-a=2 >1

    def test_bb_combo_z_nazwanym_handicapem(self):
        assert oblicz_tip_correct("BB: 1 + Handicap -1 Gospodarz", "3-0") == 1
        assert oblicz_tip_correct("BB: 1 + Handicap -1 Gospodarz", "2-1") == 0  # handicap nietraf

    # ── HT suffix — backward compat: FT-rynki rozliczają się identycznie ──────

    def test_ht_suffix_nie_psuje_1x2(self):
        assert oblicz_tip_correct("1", "2-1;HT:1-0") == 1

    def test_ht_suffix_nie_psuje_over(self):
        assert oblicz_tip_correct("Over 2.5", "3-0;HT:1-0") == 1

    def test_ht_suffix_nie_psuje_btts(self):
        assert oblicz_tip_correct("BTTS", "1-1;HT:0-0") == 1

    # ── "[wynik] & gol w każdej połowie" (GG2H) — wymaga HT ────────────────────

    def test_gg2h_1_won_gol_w_kazdej_polowie(self):
        # 4-0, HT 2-0 → dom wygrał, 2 gole w 1.poł, 2 w 2.poł → WON
        assert oblicz_tip_correct("1 & GG2H", "4-0;HT:2-0") == 1

    def test_gg2h_2_won(self):
        # 0-4, HT 0-2 → gość wygrał, gole w obu połowach → WON
        assert oblicz_tip_correct("2 & GG2H", "0-4;HT:0-2") == 1

    def test_gg2h_brak_gola_w_2_polowie(self):
        # 1-0, HT 1-0 → cały gol w 1. połowie, brak w 2. → LOSE
        assert oblicz_tip_correct("1 & GG2H", "1-0;HT:1-0") == 0

    def test_gg2h_brak_gola_w_1_polowie(self):
        # 1-0, HT 0-0 → gol dopiero w 2. połowie, brak w 1. → LOSE
        assert oblicz_tip_correct("1 & GG2H", "1-0;HT:0-0") == 0

    def test_gg2h_wynik_1x2_nietrafiony(self):
        # X & GG2H, ale wynik to "1" (dom wygrał) → LOSE niezależnie od goli w połowach
        assert oblicz_tip_correct("X & GG2H", "2-1;HT:1-0") == 0

    def test_gg2h_brak_ht_zwraca_none(self):
        # brak danych HT → nierozliczalne
        assert oblicz_tip_correct("1 & GG2H", "2-1") is None

    def test_gg2h_case_insensitive(self):
        assert oblicz_tip_correct("1 & gg2h", "4-0;HT:2-0") == 1

    def test_bb_combo_z_gg2h(self):
        assert oblicz_tip_correct("BB: 1 & GG2H + Over 1.5", "4-0;HT:2-0") == 1
        assert oblicz_tip_correct("BB: 1 & GG2H + Over 1.5", "1-0;HT:1-0") == 0


class TestParserTypowFailClosed:
    """Przecinek dziesietny, typy zlozone i rynki polowy — nie zgadujemy, None zamiast bledu."""

    # ── przecinek dziesietny w progu linii ─────────────────────────────────────

    def test_under_25_z_przecinkiem_przy_1_1_wygrana(self):
        # Regresja: regex bral "2" jako prog -> 2 < 2 = LOST zamiast WON.
        assert oblicz_tip_correct("Under 2,5", "1-1") == 1

    def test_over_25_z_przecinkiem_przy_3_golach_wygrana(self):
        assert oblicz_tip_correct("Over 2,5", "2-1") == 1

    def test_over_25_z_przecinkiem_przy_2_golach_przegrana(self):
        assert oblicz_tip_correct("Over 2,5", "1-1") == 0

    def test_przecinek_i_kropka_daja_ten_sam_wynik(self):
        for tip in ("Over 1.5", "Under 1.5", "Over 3.5", "Under 3.5"):
            for wynik in ("0-0", "1-0", "1-1", "2-1", "3-1", "0-4"):
                assert oblicz_tip_correct(tip.replace(".", ","), wynik) == \
                    oblicz_tip_correct(tip, wynik)

    def test_gole_druzyny_z_przecinkiem(self):
        assert oblicz_tip_correct("1 OVER 0,5", "0-2") == 0
        assert oblicz_tip_correct("2 OVER 1,5", "0-2") == 1
        assert oblicz_tip_correct("GOSPODARZ OVER 1,5", "1-0") == 0

    # ── typy zlozone: koniunkcja ────────────────────────────────────────────────

    def test_btts_i_over_przy_3_0_przegrana(self):
        # BTTS przegrane (gosc nie strzelil) — ocena samego Over dawala WON.
        assert oblicz_tip_correct("BTTS & OVER 2.5", "3-0") == 0

    def test_btts_i_over_przy_2_1_wygrana(self):
        assert oblicz_tip_correct("BTTS & OVER 2.5", "2-1") == 1

    def test_1_i_over_przy_3_0_wygrana(self):
        assert oblicz_tip_correct("1 & OVER 2.5", "3-0") == 1

    def test_1_i_over_przy_0_3_przegrana(self):
        # Czlon "1" byl ignorowany — wygrana goscia przy 3 golach dawala WON.
        assert oblicz_tip_correct("1 & OVER 2.5", "0-3") == 0

    def test_separatory_plus_i_przecinek_i_slowo_i(self):
        assert oblicz_tip_correct("1 + Over 2.5", "0-3") == 0
        assert oblicz_tip_correct("1 + Over 2.5", "3-0") == 1
        assert oblicz_tip_correct("BTTS, Over 2.5", "3-0") == 0
        assert oblicz_tip_correct("BTTS i Over 2.5", "2-1") == 1
        assert oblicz_tip_correct("Over 2,5, BTTS", "2-1") == 1
        assert oblicz_tip_correct("Over 2,5, BTTS", "3-0") == 0

    def test_przecinek_dziesietny_to_jeden_czlon_nie_separator(self):
        assert oblicz_tip_correct("Over 2,5", "2-1") == 1
        assert oblicz_tip_correct("Under 3,5", "2-1") == 1

    def test_koniunkcja_z_nieznanym_czlonem_blokuje_nawet_przy_pewnym_zerze(self):
        # Nierozpoznany czlon blokuje cala noge — 0 od drugiego czlonu nie wygrywa.
        assert oblicz_tip_correct("1 & Strzelec Kowalski", "0-3") is None

    def test_czy_rozliczalny_false_przy_nieznanym_czlonie_koniunkcji(self):
        assert czy_rozliczalny("1 & NIEZNANY RYNEK") is False

    def test_koniunkcja_z_nieznanym_czlonem_i_reszta_trafiona_to_none(self):
        assert oblicz_tip_correct("1 & Strzelec Kowalski", "3-0") is None

    def test_prefiks_bb_z_separatorem_ampersand_w_czlonie(self):
        assert oblicz_tip_correct("BB: BTTS & Over 2.5", "3-0") == 0
        assert oblicz_tip_correct("BB: BTTS & Over 2.5 + 1", "2-1") == 1

    def test_gg2h_nadal_jest_jednym_czlonem(self):
        assert oblicz_tip_correct("1 & GG2H & Over 3.5", "4-0;HT:2-0") == 1
        assert oblicz_tip_correct("1 & GG2H & Over 3.5", "2-0;HT:1-0") == 0

    def test_plus_na_koncu_progu_druzyny_to_nie_separator(self):
        assert oblicz_tip_correct("GOSPODARZ STRZELI 0.5+", "1-0") == 1
        assert oblicz_tip_correct("GOŚĆ STRZELI 1.5+ (Szansa: 78%)", "1-1") == 0

    def test_przecinek_w_nawiasie_opisu_nie_rozbija_typu(self):
        assert oblicz_tip_correct("2 (wygrana gościa, pewniak)", "0-3") == 1

    # ── rynki polowy: nie zgadujemy ──────────────────────────────────────────────

    def test_polowa_nie_robi_z_numeru_progu(self):
        # "1H OVER 0.5" przy 3-0;HT:0-0: "1" nie moze byc progiem.
        assert oblicz_tip_correct("1H OVER 0.5", "3-0;HT:0-0") is None

    def test_rynki_polowy_w_roznych_zapisach_to_none(self):
        for tip in ("1H Over 0.5", "2H Over 0.5", "Over 0.5 1. połowa",
                    "Powyżej 0.5 1.połowa", "HT Over 0.5", "Over 1.5 2. połowa",
                    "1ST HALF OVER 0.5"):
            assert oblicz_tip_correct(tip, "3-0;HT:0-0") is None, tip

    def test_polowa_w_koniunkcji_blokuje_noge_nawet_przy_przegranej_reszcie(self):
        # Nierozpoznana polowa blokuje cala noge, takze gdy reszta jest pewnie przegrana.
        assert oblicz_tip_correct("2 & 1H Over 0.5", "3-0;HT:1-0") is None
        assert oblicz_tip_correct("1 & 1H Over 0.5", "3-0;HT:1-0") is None

    # ── kontrolne: dotychczasowe zachowanie bez zmian ────────────────────────────

    def test_kontrolne_over_under_btts_dc(self):
        assert oblicz_tip_correct("Over 2.5", "2-1") == 1
        assert oblicz_tip_correct("Over 2.5", "1-1") == 0
        assert oblicz_tip_correct("Under 1.5", "1-0") == 1
        assert oblicz_tip_correct("Under 1.5", "1-1") == 0
        assert oblicz_tip_correct("BTTS", "1-1") == 1
        assert oblicz_tip_correct("BTTS", "1-0") == 0
        assert oblicz_tip_correct("BTTS NO", "1-0") == 1
        assert oblicz_tip_correct("BTTS nie", "2-2") == 0
        assert oblicz_tip_correct("1X", "0-1") == 0
        assert oblicz_tip_correct("X2", "0-1") == 1
        assert oblicz_tip_correct("12", "1-1") == 0
        assert oblicz_tip_correct("12", "2-1") == 1

    def test_kontrolne_1x2_przy_kilku_wynikach(self):
        for wynik, wygrywa in (("2-0", "1"), ("1-1", "X"), ("0-2", "2")):
            for tip in ("1", "X", "2"):
                assert oblicz_tip_correct(tip, wynik) == (1 if tip == wygrywa else 0)

    def test_kontrolne_bb_plus_bez_zmian(self):
        assert oblicz_tip_correct("BB: 2 + Over 1.5", "0-2") == 1
        assert oblicz_tip_correct("BB: 2 + Over 2.5 + BTTS NIE + Under 3.5", "0-3") == 1
        assert oblicz_tip_correct("BB: 2 + Over 2.5 + BTTS NIE + Under 3.5", "1-3") == 0

    def test_znak_plus_handicapu_to_nie_separator(self):
        assert oblicz_tip_correct("Handicap +1 Gość", "1-1") == 1
        assert oblicz_tip_correct("BB: 1 + Handicap +1 Gość", "1-0") == 1
        assert oblicz_tip_correct("BB: 1 + Handicap +1 Gość", "3-0") == 0
