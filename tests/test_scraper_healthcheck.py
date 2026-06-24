"""
test_scraper_healthcheck.py — health-check pobierania (dlug techniczny #2).

Sprawdza, ze _pobierz_kandydatow() w daily_agent.py woła health-check
(check_and_alert_source_down) gdy Bzzoiro zwroci 0 wydarzen / _valid=False,
i NIE woła go przy normalnych danych. Telegram zawsze zamockowany — patrz
Bug 1 (TODO): testy nie moga wysylac na prawdziwy Telegram.
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.unit
class TestPobierzKandydatowHealthCheck:
    def test_health_check_wolany_gdy_zero_wynikow(self, monkeypatch):
        """Bzzoiro OK, ale 0 kandydatów → health-check woła alert."""
        monkeypatch.setenv("BZZOIRO_KEY", "dummy")
        from footstats import daily_agent as da

        mock_client = MagicMock()
        mock_client.waliduj.return_value = (True, "OK")

        mock_alert = MagicMock(return_value=True)

        with patch("footstats.scrapers.bzzoiro.BzzoiroClient", return_value=mock_client), \
             patch("footstats.core.quick_picks.szybkie_pewniaczki_2dni", return_value=[]), \
             patch("footstats.utils.telegram_notify.check_and_alert_source_down", mock_alert):
            wyniki, indeks = da._pobierz_kandydatow(dni=2)

        assert wyniki == []
        mock_alert.assert_called_once()
        _, kwargs = mock_alert.call_args
        assert mock_alert.call_args[0][0] == "Bzzoiro" or kwargs.get("source_name") == "Bzzoiro"

    def test_health_check_wolany_gdy_niedostepny(self, monkeypatch):
        """Bzzoiro _valid=False (walidacja nieudana) → health-check woła alert, brak crasha."""
        monkeypatch.setenv("BZZOIRO_KEY", "dummy")
        from footstats import daily_agent as da

        mock_client = MagicMock()
        mock_client.waliduj.return_value = (False, "Nieprawidlowy klucz (401)")

        mock_alert = MagicMock(return_value=True)

        with patch("footstats.scrapers.bzzoiro.BzzoiroClient", return_value=mock_client), \
             patch("footstats.core.quick_picks.szybkie_pewniaczki_2dni") as mock_pewniaczki, \
             patch("footstats.utils.telegram_notify.check_and_alert_source_down", mock_alert):
            wyniki, indeks = da._pobierz_kandydatow(dni=2)

        # Graceful: brak crasha (sys.exit), wyniki = lista pusta, scraper niewolany.
        assert wyniki == []
        mock_pewniaczki.assert_not_called()
        mock_alert.assert_called_once()

    def test_health_check_niewolany_gdy_dane_normalne(self, monkeypatch):
        """Bzzoiro OK + kandydaci > 0 → health-check NIE woła alertu."""
        monkeypatch.setenv("BZZOIRO_KEY", "dummy")
        from footstats import daily_agent as da

        mock_client = MagicMock()
        mock_client.waliduj.return_value = (True, "OK")

        fake_wyniki = [{"gospodarz": "Bayern", "goscie": "Dortmund", "liga": "Bundesliga", "odds": {}}]
        mock_alert = MagicMock(return_value=False)

        with patch("footstats.scrapers.bzzoiro.BzzoiroClient", return_value=mock_client), \
             patch("footstats.core.quick_picks.szybkie_pewniaczki_2dni", return_value=fake_wyniki), \
             patch("footstats.utils.telegram_notify.check_and_alert_source_down", mock_alert):
            wyniki, indeks = da._pobierz_kandydatow(dni=2)

        assert len(wyniki) == 1
        mock_alert.assert_called_once()
        # Wywolany z n_wyniki=1 i ok=True — funkcja sama zdecyduje, ze nie alertuje (testowane osobno w test_telegram.py).
