"""J1 — połowa handlerów `except` milczy: bez logu, bez `raise`, bez śladu.

Strażnik `test_broad_except_audit.py` pilnuje SZEROKOŚCI łapania (`except Exception`,
gołe `except:`). To jest drugie, brakujące kryterium: **czy handler w ogóle coś mówi**.
Wąskie `except (OSError, ValueError): pass` przechodzi tamten audyt bez mrugnięcia,
a ukrywa awarię równie skutecznie.

DLACZEGO TO NIE JEST HIGIENA, TYLKO AWARIE: 2026-08-24 w ciągu jednego dnia wyszło
pięć usterek wyglądających jak zdrowy system — kupony stały osiem dni przy `exit=0`,
próg selekcji nigdy nie działał (0,55 na skali procentowej), football-data nigdy nie
odpowiadało (`return []` bez zapytania), CI świeciło czerwono aż przestało cokolwiek
znaczyć, a alarm o rozliczaniu miał wyć codziennie bez powodu. Przy tym audycie doszły
kolejne dwie: `check_and_alert_agent_down` i `check_and_alert_accuracy` kończyły się
`except (...): pass`, czyli **czujnik dymu meldował „wszystko gra", gdy sam się palił**.

CZYM JEST „MILCZĄCY": handler bez `raise`, bez wywołania logu/alertu i bez ani jednego
odwołania do złapanego wyjątku. `except X as e: return {"error": str(e)}` NIE jest
milczący — błąd idzie do wołającego. `except X: return None` jest.

MILCZENIE BYWA POPRAWNE. `except FileNotFoundError: return {}` przy pierwszym
uruchomieniu to stan normalny; log przy każdym przebiegu byłby szumem, a szum niszczy
alarmy tak samo skutecznie jak cisza. Dlatego twardego zera wymagamy wyłącznie tam,
gdzie cisza znaczy „wszystko gra" — w funkcjach alarmowych.

BASELINE, NIE ZERO: 255 z 555 handlerów milczy. Naprawa wszystkich naraz byłaby
większym ryzykiem niż problem. Ten test zatrzymuje PRZYROST i pozwala schodzić w dół
plik po pliku, tak samo jak audyt szerokości. Nowy plik musi mieć zero.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "footstats"

# Nazwy wywołań, które znaczą „robimy z tym błędem coś widocznego".
GLOSNE = frozenset({"debug", "info", "warning", "warn", "error", "exception",
                    "critical", "print", "send_alert", "capture_exception", "log"})


def _mowi(handler: ast.ExceptHandler) -> bool:
    """Czy handler komunikuje błąd: log, `raise` albo przekazanie go dalej."""
    for w in ast.walk(handler):
        if isinstance(w, ast.Raise):
            return True
        if isinstance(w, ast.Call):
            f = w.func
            nazwa = f.attr if isinstance(f, ast.Attribute) else (
                f.id if isinstance(f, ast.Name) else "")
            if nazwa in GLOSNE:
                return True
        # `except X as e: return {"error": str(e)}` — błąd trafia do wołającego.
        if handler.name and isinstance(w, ast.Name) and w.id == handler.name:
            return True
    return False


def _drzewo(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return None


def _licz_ciche(path: Path) -> int:
    drzewo = _drzewo(path)
    if drzewo is None:
        return 0
    return sum(1 for h in ast.walk(drzewo)
               if isinstance(h, ast.ExceptHandler) and not _mowi(h))


def _ciche_w_funkcjach(path: Path, prefiksy: tuple[str, ...]) -> dict[str, int]:
    """Milczące handlery w funkcjach, których nazwa zaczyna się od któregoś prefiksu."""
    drzewo = _drzewo(path)
    if drzewo is None:
        return {}
    wynik: dict[str, int] = {}
    for w in ast.walk(drzewo):
        if not isinstance(w, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not w.name.startswith(prefiksy):
            continue
        ile = sum(1 for h in ast.walk(w)
                  if isinstance(h, ast.ExceptHandler) and not _mowi(h))
        if ile:
            wynik[w.name] = ile
    return wynik


def _pliki() -> list[Path]:
    return [p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts]


# Zmierzone 2026-08-24. Obniżać przy naprawianiu, nigdy nie podnosić bez uzasadnienia.
BASELINE: dict[str, int] = {
    # 12 -> 1 (2026-08-28, J1). Naprawione: `_get_kalibracja_blok` i
    # `_get_liga_statystyki_blok` (kazdy blad importu/atrybutu cicho zdejmowal
    # cala sekcje z KAZDEGO promptu do Groqa przez cala sesje), `_zapytaj_typera`
    # (except Exception polykajacy DOKLADNIE ten typ awarii, ktory 22.08 zatrzymal
    # potok na 6 dni: Groq wycofal model, 404 znikaly bez sladu), reszta w petlach
    # na debug/warning wg konsekwencji. Zostaje 1: parsowanie kursu do EV w petli
    # 5 rynkow x N meczow (`_buduj_opis_meczu`) - brak kursu na BTTS/O2.5 to norma,
    # log zalalby logi szumem.
    "ai/analyzer.py": 1,
    "ai/analyzer_helpers.py": 6,
    "ai/client.py": 1,
    "ai/rag.py": 2,
    "ai/trainer.py": 2,
    # 4 -> 0 (2026-08-26, J1). Naprawione: `_verify_password` (uszkodzony hash
    # w bazie), `konto_zablokowane` (nieparsowalny `locked_until` cicho gasil
    # blokade B7), oba `except` w `register` (bankroll_state i mail powitalny).
    # Kontekst: 27.07 zgubiony JWT_SECRET udawal "zle haslo" — cisza tu ma inna
    # wage niz gdzie indziej.
    "api/auth.py": 0,
    "api/main.py": 4,
    "api/routes/coupons.py": 1,
    "api/routes/status.py": 1,
    # 15 -> 9 (2026-08-28, J1). Naprawione: import modulow AI (`except ImportError`
    # wylaczajacy opcje I/J na cala sesje bez sladu) i 5 handlerow w petli po
    # kolejce meczow (nazwa druzyny nieodczytywalna, kursy niedostepne, forma
    # nieobliczalna) - wszystkie na debug, bo pojedynczy element w petli po
    # kolejce to norma. Zostaje 9: pojedyncze interaktywne prompty (float/int)
    # z natychmiastowym fallbackiem na wartosc domyslna i 2 petle retry, ktore
    # od razu drukuja "Zly numer." - blad widoczny w tej samej sekundzie,
    # nie kumuluje sie i nie ucieka dalej niz jeden wybor w menu.
    "cli.py": 9,
    "cli_commands.py": 3,
    "core/async_utils.py": 2,
    "core/backtest.py": 5,
    "core/bankroll.py": 2,
    "core/calibration.py": 3,
    "core/checkpoint.py": 1,
    "core/classifier.py": 2,
    "core/cloud_draft.py": 1,
    "core/clv_tracker.py": 1,
    "core/coupon_settlement.py": 4,
    # 9 -> 5 (2026-08-25). Naprawione w `_dodaj_kelly`: ciche wyjscie przy braku
    # modulow (kupon bez stawek), podmiana kalibracji na tozsamosc i dwie awaryjne
    # stawki 1.0 PLN udajace decyzje modelu.
    # 28.08: 5 -> 1. Cztery to byly `except ImportError` wokol CALYCH podsystemow
    # (lambda reprezentacji, BetBuilder, ensemble) plus polkniete dane SofaScore —
    # ten sam ksztalt co bug `quick_picks.py` z tego samego dnia. Zostaje JEDEN:
    # petla probujaca formaty dat, gdzie cisza jest poprawna i jest udokumentowana.
    "core/daily_phases.py": 1,
    "core/draft_health.py": 1,
    "core/ensemble.py": 1,
    "core/ensemble_optimizer.py": 1,
    "core/kelly.py": 1,
    "core/lambda_optimizer.py": 3,
    "core/logging_config.py": 1,
    "core/match_analysis.py": 2,
    "core/match_linker.py": 1,
    "core/ml_features.py": 1,
    "core/player_db.py": 5,
    "core/poisson.py": 2,
    "core/probability_calibrator.py": 2,
    "core/processing.py": 1,
    # 10 -> 8 (2026-08-25). Naprawione: brak danych historycznych (Poisson padal
    # dla CALEGO przebiegu w ciszy) i handler blendu, ktory ukrywal, ze 90% stawki
    # liczy fallback Bzzoiro-ML. Plik nie mial wczesniej nawet loggera.
    "core/quick_picks.py": 7,
    "core/response_cache.py": 2,
    "core/system_paper.py": 2,
    "core/weekly_picks.py": 5,
    # 28.08: 8 -> 0. Cztery to byly SCIEZKI ALARMOWE (`send_alert`,
    # `send_stop_loss_alert`, `check_and_alert_accuracy`) — nieudana wysylka
    # alarmu byla cicha, czyli stop-loss mogl zadzialac bez powiadomienia.
    # Wyciagniete do `daily_agent._wyslij_alarm`. Pozostale cztery gubily
    # arbitraz kursow, prefetch xG (per liga i caly podsystem) oraz korekte
    # sedziowska. Testy: `tests/test_alarmy_nie_milcza.py`.
    "daily_agent.py": 0,
    "dashboard.py": 4,
    "data/context_scraper.py": 1,
    "data/historical_loader.py": 3,
    "data_fetcher.py": 1,
    "db/migrations.py": 3,
    "evening_agent.py": 3,
    "export/pdf_font.py": 1,
    "operator/review.py": 1,
    "operator/workflow.py": 1,
    "operator_agent.py": 1,
    "scrapers/__init__.py": 1,
    "scrapers/api_football.py": 5,
    "scrapers/base_playwright.py": 7,
    "scrapers/browser_fetch.py": 1,
    "scrapers/bzzoiro.py": 3,
    "scrapers/closing_odds.py": 2,
    "scrapers/clubelo.py": 3,
    "scrapers/enriched.py": 1,
    "scrapers/fixtures_fallback.py": 2,
    "scrapers/flashscore_match.py": 1,
    "scrapers/flashscore_results.py": 1,
    "scrapers/form_scraper.py": 3,
    "scrapers/kursy.py": 3,
    "scrapers/lineup_scraper.py": 1,
    "scrapers/odds_api.py": 2,
    "scrapers/results_updater.py": 3,
    "scrapers/sofascore_odds.py": 3,
    "scrapers/sources/af_source.py": 1,
    "scrapers/sources/aggregator.py": 1,
    "scrapers/sources/footballdata_source.py": 3,
    "scrapers/sources/thesportsdb_source.py": 1,
    "scrapers/sts_inspiracje.py": 1,
    "scrapers/sts_kursy.py": 2,
    "scrapers/superbet.py": 14,
    "scrapers/superbet_bb.py": 1,
    "scrapers/superbet_parsing.py": 8,
    "scrapers/terminarz.py": 4,
    "scrapers/understat_xg.py": 5,
    "scrapers/zawodtyper_referees.py": 2,
    "telegram_bot.py": 2,
    "utils/betting.py": 4,
    "utils/cache.py": 4,
    "utils/console.py": 1,
    "utils/db.py": 3,
    "utils/helpers.py": 2,
    "utils/logging.py": 2,
    "utils/normalize.py": 1,
    # 5 -> 1 (2026-08-24, J1). Zostaje wyłącznie `except FileNotFoundError` przy
    # pierwszym odczycie pliku dedup — brak pliku to stan normalny, log przy każdym
    # przebiegu byłby szumem. Uszkodzony plik ma już własny handler z ostrzeżeniem.
    "utils/telegram_notify.py": 1,
    "weekly_report.py": 1,
}


@pytest.mark.parametrize("rel,limit", sorted(BASELINE.items()))
def test_baseline_cichych_nie_rosnie(rel: str, limit: int) -> None:
    sciezka = SRC / rel
    if not sciezka.exists():
        pytest.skip(f"{rel} nie istnieje")
    ile = _licz_ciche(sciezka)

    assert ile <= limit, (
        f"{rel}: {ile} milczących handlerów, baseline={limit}. "
        "Dodaj log albo `raise`, potem obniż baseline."
    )


def test_nowy_plik_nie_moze_miec_cichych_handlerow() -> None:
    """Dług zamrożony, ale nie powiększany."""
    naruszenia = []
    for p in _pliki():
        rel = p.relative_to(SRC).as_posix()
        if rel in BASELINE:
            continue
        ile = _licz_ciche(p)
        if ile:
            naruszenia.append(f"{rel}: {ile}")

    assert not naruszenia, (
        "nowe pliki z milczącymi `except` — dodaj log/`raise` albo wpisz do BASELINE:\n"
        + "\n".join(f"  {n}" for n in naruszenia)
    )


def test_funkcje_alarmowe_nie_moga_milczec() -> None:
    """Twarde zero tam, gdzie cisza znaczy „wszystko gra".

    `check_and_alert_*` zwracają `False` = „nie wysłano alertu". Jeśli ich własne
    sprawdzenie padnie po cichu, brak alarmu jest nieodróżnialny od zdrowego stanu.
    To nie jest hipoteza — 24.08 obie te funkcje tak właśnie wyglądały.

    Zakres celowo wąski (nazwy funkcji, nie cały plik): w tym samym module milczy
    świadomie `except FileNotFoundError` przy pierwszym odczycie dedup i nie ma
    powodu, żeby to blokowało.
    """
    winne = _ciche_w_funkcjach(
        SRC / "utils" / "telegram_notify.py",
        ("check_and_alert", "send_message_to_user"),
    )

    assert not winne, (
        f"funkcje alarmowe z milczącym `except`: {winne} — "
        "cisza w czujniku znaczy 'wszystko gra'"
    )
