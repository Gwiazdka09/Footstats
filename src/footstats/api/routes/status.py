"""Status and config endpoints."""
import hmac
import json

import psycopg2
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import footstats.config as cfg
from fastapi import APIRouter, Depends, Header, HTTPException

from footstats.api.auth import require_auth
from footstats.utils.db import connect as _connect

router = APIRouter(prefix="/api", tags=["status"])
_log = logging.getLogger(__name__)


@router.get("/status")
def get_status(user_id: int = Depends(require_auth)):
    try:
        with _connect() as conn:
            bankroll = conn.execute(
                "SELECT balance, updated_at FROM bankroll_state WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            stats = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status IN ('WON','WIN') THEN 1 ELSE 0 END) as wins,
                    SUM(payout_pln) as total_payout,
                    SUM(stake_pln) as total_stake
                FROM coupons
                WHERE status IN ('WON','WIN','LOSE','LOST') AND user_id = ?
                """,
                (user_id,),
            ).fetchone()
            cutoff_30d = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            wins_30d = conn.execute(
                "SELECT COUNT(*) as n FROM coupons"
                " WHERE status IN ('WON','WIN') AND created_at >= ? AND user_id = ?",
                (cutoff_30d, user_id),
            ).fetchone()
        roi = 0
        if stats and stats["total_stake"]:
            roi = round(
                ((stats["total_payout"] or 0) - stats["total_stake"]) / stats["total_stake"] * 100, 1
            )
        return {
            "bankroll": bankroll["balance"] if bankroll else 0,
            "last_update": str(bankroll["updated_at"]) if bankroll else None,
            "stats": {
                "total_finished": stats["total"] if stats else 0,
                "wins": stats["wins"] if stats else 0,
                "wins_last_30d": wins_30d["n"] if wins_30d else 0,
                "roi_pct": roi,
            },
        }
    except (ValueError, KeyError, AttributeError, TypeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


_CALIBRATION_PATH = Path(__file__).parent.parent.parent.parent.parent / "data" / "model_calibration.json"


@router.get("/calibration")
def get_calibration(user_id: int = Depends(require_auth)):
    try:
        data = json.loads(_CALIBRATION_PATH.read_text(encoding="utf-8"))
        return data
    except FileNotFoundError:
        return {"updated_at": None, "factor_home": None, "factor_away": None, "n_matches": 0}
    except (ValueError, KeyError, AttributeError, TypeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
def get_bot_config(user_id: int = Depends(require_auth)):
    return {
        "version": cfg.VERSION,
        "kelly_fraction": cfg.AGENT_KELLY_FRACTION,
        "bankroll_start": cfg.AGENT_BANKROLL,
        "min_confidence": cfg.AGENT_KANDYDAT_PROG,
        "pewniaczek_prog": cfg.PEWNIACZEK_PROG,
        "ostatnie_n": cfg.OSTATNIE_N,
    }


# ── Monitor pipeline'u ────────────────────────────────────────────────────
#
# DLACZEGO TUTAJ, A NIE W JOBIE: 30.07-02.08 joby Cloud Run stały na uszkodzonym
# obrazie i nikt nie zauważył tego przez TRZY DNI — wykonania raportowały
# "Completed" bez liczników, bo kontener w ogóle nie wstawał. Monitor wpięty
# w job, który monitoruje, milczałby dokładnie wtedy, gdy jest potrzebny.
#
# Ten endpoint żyje na serwisie API (osobny kontener, zdrowy przez całą awarię)
# i pyta o SKUTEK, nie o proces: "czy w bazie przybywa predykcji". Dzięki temu
# łapie każdą przyczynę naraz — obraz, klucz, limit API, sieć, błąd kodu.

# Doba + 2h marginesu na opóźniony start joba (final 11:00, evening 23:00).
_MAX_WIEK_PREDYKCJI_H = 26.0

# Predykcje bez wyniku starsze niż okno `update_pending` (2 dni) NIGDY nie
# rozliczą się same. Rosnąca sterta = pobieranie wyników padło.
_MAX_ZALEGLOSCI = 10


def _sprawdz_cron_secret(podany: str) -> None:
    """Wspólna bramka dla endpointów /cron/*.

    `not oczekiwany` jest tu krytyczne: `hmac.compare_digest("", "")` zwraca True,
    więc deploy bez zmiennej CRON_SECRET otwierałby endpoint dla każdego, kto
    wyśle pusty nagłówek.
    """
    oczekiwany = os.getenv("CRON_SECRET", "")
    if not oczekiwany or not hmac.compare_digest(podany, oczekiwany):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/cron/pipeline-health")
def pipeline_health(
    x_cron_secret: str = Header(default=""),
    max_wiek_h: float = _MAX_WIEK_PREDYKCJI_H,
    max_zaleglosci: int = _MAX_ZALEGLOSCI,
) -> dict:
    """Sprawdza, czy pipeline nadal produkuje. Alarm na Telegram tylko gdy ŹLE.

    Cisza przy zdrowym stanie jest celowa — alarm wysyłany codziennie
    "wszystko gra" przestaje być czytany po tygodniu.
    """
    _sprawdz_cron_secret(x_cron_secret)

    powody: list[str] = []
    wiek_h: float | None = None
    nierozliczone = 0

    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT MAX(created_at) AS ostatnia FROM predictions"
            ).fetchone()
            ostatnia = row["ostatnia"] if row else None

            if ostatnia is None:
                powody.append("brak jakichkolwiek predykcji w bazie")
            else:
                wiek_h = round((datetime.now() - ostatnia).total_seconds() / 3600, 1)
                if wiek_h > max_wiek_h:
                    powody.append(
                        f"brak nowych predykcji od {wiek_h:.0f}h (próg {max_wiek_h:.0f}h)"
                    )

            # `settle_attempts >= MAX_PROB_ROZLICZENIA` = predykcje SWIADOMIE
            # porzucone: zadne zrodlo nie ma juz ich wyniku, wiec nadrabianie
            # przestalo je probowac (patrz `_wybierz_do_rozliczenia`). Liczenie
            # ich tutaj czynilo alarm WIECZNYM — 22.08 bylo takich 49 z 95, wiec
            # alert palil sie niezaleznie od stanu potoku i zagluszyl prawdziwa
            # awarie (wycofany model Groqa). Alarm, ktory nigdy nie gasnie, uczy
            # go ignorowac.
            from footstats.scrapers.results_updater import MAX_PROB_ROZLICZENIA

            row2 = conn.execute(
                "SELECT COUNT(*) AS n FROM predictions"
                " WHERE tip_correct IS NULL AND match_date < ?"
                "   AND COALESCE(settle_attempts, 0) < ?",
                ((datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
                 MAX_PROB_ROZLICZENIA),
            ).fetchone()
            nierozliczone = (row2["n"] if row2 else 0) or 0
            if nierozliczone > max_zaleglosci:
                powody.append(
                    f"{nierozliczone} predykcji bez rozliczenia starszych niż 2 dni"
                    f" (próg {max_zaleglosci}) — pobieranie wyników mogło paść"
                )
    except Exception as e:  # noqa: BLE001 — monitor milczący przy własnej awarii
        # jest gorszy niż jego brak: sygnalizujemy problem zamiast zwracać 500,
        # bo 500 uruchamia retry Schedulera i zapętla alarm.
        powody.append(f"nie udało się odpytać bazy: {e}")

    ok = not powody
    alarm_wyslany = False
    if not ok:
        alarm_wyslany = _wyslij_alarm(powody, wiek_h, nierozliczone)
        _log.error("pipeline-health NIEZDROWY: %s", "; ".join(powody))

    return {
        "ok": ok,
        "wiek_predykcji_h": wiek_h,
        "nierozliczone": nierozliczone,
        "powody": powody,
        "alarm_wyslany": alarm_wyslany,
    }


def _wyslij_alarm(powody: list[str], wiek_h: float | None, nierozliczone: int) -> bool:
    """Jedna wiadomość ze WSZYSTKIMI powodami — nie osobna na każdy."""
    try:
        from footstats.utils.telegram_notify import _send

        lista = "\n".join(f"• {p}" for p in powody)
        tekst = (
            "<b>⚠️ FootStats: pipeline nie produkuje</b>\n\n"
            f"{lista}\n\n"
            f"<i>wiek najnowszej predykcji: "
            f"{f'{wiek_h:.0f}h' if wiek_h is not None else 'brak danych'} | "
            f"nierozliczonych: {nierozliczone}</i>"
        )
        return bool(_send(tekst))
    except Exception as e:  # noqa: BLE001 — brak Telegrama nie może ukryć wyniku
        _log.error("pipeline-health: alarm niewyslany: %s", e)
        return False


@router.post("/cron/kalibracja-rozlicz")
def cron_kalibracja_rozlicz(
    x_cron_secret: str = Header(default=""),
    dni_wstecz: int = 14,
    dry_run: bool = False,
) -> dict:
    """Dopisuje wyniki do dziennika kalibracji (`model_log`).

    Osobny trigger od rozliczania kuponow: kupony scigaja sie z czasem i maja
    okno 2-3 dni, dziennik nadrabia zaleglosci szerszym oknem. Patrz
    `core/kalibracja_rozlicz.py`.
    """
    _sprawdz_cron_secret(x_cron_secret)
    try:
        from footstats.core.kalibracja_rozlicz import rozlicz_dziennik
        raport = rozlicz_dziennik(dni_wstecz=dni_wstecz, dry_run=dry_run)
        _log.info("cron_kalibracja_rozlicz: %s", raport)
        return {"ok": True, **raport}
    except (ValueError, KeyError, RuntimeError, OSError, psycopg2.Error) as e:
        # Scheduler musi zobaczyc blad — HTTP 200 ukrylby awarie. `psycopg2.Error`
        # w krotce, bo bez niej brak tabeli konczyl sie golym tracebackiem
        # zamiast czytelnego komunikatu (2026-08-06).
        _log.error("cron_kalibracja_rozlicz blad: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
