"""Testy spójności batch vs single dla RAG queries."""
from unittest.mock import MagicMock, patch


from footstats.ai.rag import pobierz_rag_kontekst, pobierz_rag_wzorce, wyciagnij_faktory


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_pred(
    pw: float = 60.0,
    pr: float = 25.0,
    pp: float = 15.0,
    patent: bool = False,
    fortress: bool = False,
) -> dict:
    return {
        "metoda": "POISSON",
        "p_wygrana": pw,
        "p_remis": pr,
        "p_przegrana": pp,
        "pred": {
            "p_wygrana": pw,
            "p_remis": pr,
            "p_przegrana": pp,
            "h2h_g": {"patent": patent, "zemsta": False, "n_h2h": 5},
            "h2h_a": {"patent": False, "zemsta": False, "n_h2h": 5},
            "fortress_g": {"fortress": fortress, "bonus_obrona": 1.0},
            "heur_g": {"rotacja": False, "zmeczenie": False, "mnoznik_atak": 1.0, "mnoznik_obr": 1.0},
            "heur_a": {"rotacja": False, "zmeczenie": False, "mnoznik_atak": 1.0, "mnoznik_obr": 1.0},
            "imp_g": {"bonus_atak": 1.0, "status": "NORMAL"},
            "imp_a": {"bonus_atak": 1.0, "status": "NORMAL"},
        },
    }


# ── wyciagnij_faktory ─────────────────────────────────────────────────────────

def test_wyciagnij_faktory_empty_pred():
    assert wyciagnij_faktory({}) == []


def test_wyciagnij_faktory_none_pred():
    assert wyciagnij_faktory(None) == []


def test_wyciagnij_faktory_patent():
    pred = _make_pred(patent=True)["pred"]
    faktory = wyciagnij_faktory(pred)
    assert "PATENT" in faktory


def test_wyciagnij_faktory_fortress():
    pred = _make_pred(fortress=True)["pred"]
    faktory = wyciagnij_faktory(pred)
    assert "TWIERDZA" in faktory


def test_wyciagnij_faktory_no_factors():
    pred = _make_pred()["pred"]
    assert wyciagnij_faktory(pred) == []


# ── pobierz_rag_wzorce ────────────────────────────────────────────────────────

def test_pobierz_rag_wzorce_empty_factors():
    assert pobierz_rag_wzorce([]) == ""


def test_pobierz_rag_wzorce_returns_string():
    with patch("footstats.ai.rag._connect") as mock_conn, \
         patch("footstats.ai.rag.init_db"):
        # Stub: zero results
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.execute.return_value.fetchall.return_value = [
            {"n": 0, "hits": 0}, {"n": 0, "hits": 0}
        ]
        mock_conn.return_value = mock_ctx

        result = pobierz_rag_wzorce(["PATENT", "TWIERDZA"], ai_tip="1")
        assert isinstance(result, str)


def test_pobierz_rag_wzorce_batch_single_db_call():
    """Wszystkie faktory powinny być odpytane jednym UNION ALL (1 execute)."""
    with patch("footstats.ai.rag._connect") as mock_conn, \
         patch("footstats.ai.rag.init_db"):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.execute.return_value.fetchall.return_value = [
            {"n": 5, "hits": 4}, {"n": 3, "hits": 2}, {"n": 8, "hits": 6}
        ]
        mock_conn.return_value = mock_ctx

        pobierz_rag_wzorce(["PATENT", "TWIERDZA", "ZEMSTA"], ai_tip="1")

        # Jeden execute call z UNION ALL, nie N osobnych
        assert mock_ctx.execute.call_count == 1
        sql_called = mock_ctx.execute.call_args[0][0]
        assert "UNION ALL" in sql_called


def test_pobierz_rag_wzorce_formats_output_correctly():
    """n >= min_n → wynik w formacie 'LABEL->TIP: hits/n(acc%)'."""
    with patch("footstats.ai.rag._connect") as mock_conn, \
         patch("footstats.ai.rag.init_db"):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        # combo: 8/10, single PATENT: 6/8
        mock_ctx.execute.return_value.fetchall.return_value = [
            {"n": 10, "hits": 8}, {"n": 8, "hits": 6}
        ]
        mock_conn.return_value = mock_ctx

        result = pobierz_rag_wzorce(["PATENT", "TWIERDZA"], ai_tip="1")
        assert "80%" in result or "75%" in result


def test_pobierz_rag_wzorce_skips_below_min_n():
    """n < min_n → wynik nie pojawia się w output."""
    with patch("footstats.ai.rag._connect") as mock_conn, \
         patch("footstats.ai.rag.init_db"):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.execute.return_value.fetchall.return_value = [
            {"n": 2, "hits": 2}, {"n": 1, "hits": 1}
        ]
        mock_conn.return_value = mock_ctx

        result = pobierz_rag_wzorce(["PATENT", "TWIERDZA"], ai_tip="1", min_n=3)
        assert result == ""


def test_pobierz_rag_wzorce_max_3_results():
    """Output zawiera max 3 wyniki oddzielone ' | '."""
    with patch("footstats.ai.rag._connect") as mock_conn, \
         patch("footstats.ai.rag.init_db"):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.execute.return_value.fetchall.return_value = [
            {"n": 10, "hits": 8}, {"n": 10, "hits": 7}, {"n": 10, "hits": 6},
            {"n": 10, "hits": 5}, {"n": 10, "hits": 4}
        ]
        mock_conn.return_value = mock_ctx

        result = pobierz_rag_wzorce(["A", "B", "C", "D"], ai_tip="1")
        if result:
            parts = result.split(" | ")
            assert len(parts) <= 3


# ── pobierz_rag_kontekst ──────────────────────────────────────────────────────

def test_pobierz_rag_kontekst_skips_non_poisson():
    w = {"metoda": "HEURYSTYKA"}
    assert pobierz_rag_kontekst(w) == ""


def test_pobierz_rag_kontekst_skips_no_factors():
    w = _make_pred()
    assert pobierz_rag_kontekst(w) == ""


def test_pobierz_rag_kontekst_tip_selection_home_win():
    """pw dominuje → tip='1'."""
    w = _make_pred(pw=70.0, pr=20.0, pp=10.0, patent=True)
    with patch("footstats.ai.rag.pobierz_rag_wzorce") as mock_wzorce:
        mock_wzorce.return_value = "PATENT->1: 5/6(83%)"
        pobierz_rag_kontekst(w)
        _, call_kwargs = mock_wzorce.call_args
        assert mock_wzorce.call_args[0][1] == "1"


def test_pobierz_rag_kontekst_tip_selection_away_win():
    """pp dominuje → tip='2'."""
    w = _make_pred(pw=15.0, pr=20.0, pp=65.0, patent=True)
    with patch("footstats.ai.rag.pobierz_rag_wzorce") as mock_wzorce:
        mock_wzorce.return_value = ""
        pobierz_rag_kontekst(w)
        assert mock_wzorce.call_args[0][1] == "2"
