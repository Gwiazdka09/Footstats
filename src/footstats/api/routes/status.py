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
from footstats.core.draft_health import PROG_STALE_DNI, ocena_swiezosci
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

    Trzy wymiary, wszystkie po SKUTKU (co jest w bazie), nie po procesie:
      1. wiek najnowszej predykcji — czy analiza i typowanie żyją;
      2. zaległości w rozliczeniach — czy pobieranie wyników żyje;
      3. wiek najnowszego kuponu System — czy draft żyje.

    Trzeci doszedł 24.08 i to nie jest kosmetyka: bez niego monitor przespał
    OSIEM DNI bez kuponów (awaria I7), bo predykcje płynęły i dwa pierwsze
    warunki były spełnione.

    Cisza przy zdrowym stanie jest celowa — alarm wysyłany codziennie
    "wszystko gra" przestaje być czytany po tygodniu.
    """
    _sprawdz_cron_secret(x_cron_secret)

    powody: list[str] = []
    wiek_h: float | None = None
    nierozliczone = 0
    wiek_kuponu_dni: int | None = None

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
            from footstats.core.coupon_settlement import HORYZONT_ZRODEL_DNI
            from footstats.scrapers.results_updater import MAX_PROB_ROZLICZENIA

            # DOLNA granica okna, dodana 24.08 — bez niej alarm NIGDY nie gasł.
            #
            # ZMIERZONE NA PRODUKCJI: monitor liczył 25 zaległości przy progu 10,
            # a z tych 25 **ZERO** było w zasięgu źródeł — najstarsze to mecze
            # z MAJA 2026. Wykluczenie po liczbie prób ich nie łapało, bo pętla
            # nadrabiania sięga tylko po świeże, więc utknęły z `settle_attempts`
            # poniżej limitu: za stare, żeby się rozliczyć, za mało prób, żeby
            # przestać się liczyć.
            #
            # Właściwym kryterium nie jest liczba prób, tylko OSIĄGALNOŚĆ ŹRÓDŁA —
            # ta sama granica `HORYZONT_ZRODEL_DNI`, którą wprowadziło D6.
            # Starszy mecz to nie zaległość, tylko trup. Alarm, który świeci
            # zawsze, uczy go ignorować — a przy ignorowanym alarmie awaria
            # kuponów (I7) przeleżała osiem dni.
            row2 = conn.execute(
                "SELECT COUNT(*) AS n FROM predictions"
                " WHERE tip_correct IS NULL AND match_date < ?"
                "   AND match_date >= ?"
                "   AND COALESCE(settle_attempts, 0) < ?",
                ((datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
                 (datetime.now() - timedelta(days=HORYZONT_ZRODEL_DNI)).strftime("%Y-%m-%d"),
                 MAX_PROB_ROZLICZENIA),
            ).fetchone()
            nierozliczone = (row2["n"] if row2 else 0) or 0
            if nierozliczone > max_zaleglosci:
                powody.append(
                    f"{nierozliczone} predykcji bez rozliczenia starszych niż 2 dni"
                    f" (próg {max_zaleglosci}) — pobieranie wyników mogło paść"
                )

            # TRZECI WYMIAR, dodany 24.08 po awarii I7.
            #
            # 15-23.08 kupony nie powstawały przez OSIEM DNI, a ten monitor świecił
            # zielono. Sprawdzał wyłącznie predykcje i zaległości — a predykcje
            # płynęły, bo pisze je job. Kupony robi `/api/cron/draft` na serwisie API,
            # który padał na limicie 512 MiB i oddawał 503.
            #
            # Sygnał `stale_days` ISTNIAŁ, ale mieszkał WEWNĄTRZ draftu, czyli wewnątrz
            # tego, co było zepsute. Endpoint, który umiera, nie zgłosi, że umarł —
            # dokładnie ten sam błąd architektoniczny, przed którym ostrzega komentarz
            # na górze tego pliku, tylko o poziom wyżej. Dlatego pytamy o kupony SAMI
            # i znów po SKUTKU: „czy w bazie przybywa kuponów System".
            row3 = conn.execute(
                "SELECT MAX(cu.created_at) AS ostatni_kupon FROM coupons cu"
                " JOIN users u ON u.id = cu.user_id WHERE u.username = 'System'"
            ).fetchone()
            ostatni_kupon = row3["ostatni_kupon"] if row3 else None
            ocena = ocena_swiezosci(ostatni_kupon)
            wiek_kuponu_dni = ocena["stale_days"]
            if ocena["stale"]:
                ile = ("nigdy" if wiek_kuponu_dni is None
                       else f"od {wiek_kuponu_dni} dni")
                powody.append(
                    f"brak nowego kuponu System {ile} (próg {PROG_STALE_DNI} dni)"
                    " — draft mógł paść, choć predykcje dalej przybywają"
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
        # Liczba w odpowiedzi, nie tylko w alarmie — inaczej nie da się śledzić
        # trendu ani sprawdzić stanu bez czekania, aż coś się zepsuje.
        "wiek_kuponu_dni": wiek_kuponu_dni,
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


@router.post("/cron/raport-dzienny")
def raport_dzienny(x_cron_secret: str = Header(default="")) -> dict:
    """Codzienne potwierdzenie, że przebieg poszedł. Wysyłane ZAWSZE, też gdy dobrze.

    CZYM SIĘ RÓŻNI OD `pipeline-health`: alarm odpowiada na pytanie „czy coś jest
    zepsute" i milczy, gdy jest dobrze — słusznie, bo codzienne „wszystko gra"
    przestaje być czytane. Ale cisza nie odróżnia „poszło dobrze" od „monitor też
    padł", a przy awarii I7 (kupony stanęły na osiem dni) znaczyła to drugie.

    Raport odpowiada na pytanie „ile dziś powstało". Spadek z 14 kuponów na 2 nie
    jest awarią i alarmu nie wywoła, ale jest sygnałem — i właśnie po to są liczby.

    DLACZEGO TU, A NIE Z AGENTA W CHMURZE: agent startuje z czystym checkoutem, bez
    `gcloud`, bez `DATABASE_URL` i bez `CRON_SECRET`, a każdy endpoint mówiący coś
    o stanie wymaga uwierzytelnienia. Żeby działał, trzeba by wkleić sekret do
    przechowywanej konfiguracji rutyny — ten sam błąd, przez który 14.08 `CRON_SECRET`
    wyciekł i wymagał rotacji. Raport liczy tam, gdzie poświadczenia już są.
    """
    _sprawdz_cron_secret(x_cron_secret)

    kupony = predykcje = rozliczone = 0
    problemy: list[str] = []

    try:
        with _connect() as conn:
            kupony = _licz(conn,
                           "SELECT COUNT(*) AS n FROM coupons cu"
                           " JOIN users u ON u.id = cu.user_id"
                           " WHERE u.username = 'System'"
                           "   AND cu.created_at > NOW() - INTERVAL '24 hours'")
            predykcje = _licz(conn,
                              "SELECT COUNT(*) AS n FROM predictions"
                              " WHERE created_at > NOW() - INTERVAL '24 hours'")
            rozliczone = _licz(conn,
                               "SELECT COUNT(*) AS n FROM predictions"
                               " WHERE tip_correct IS NOT NULL"
                               "   AND created_at > NOW() - INTERVAL '7 days'")
    # Raport milczący przy własnej awarii wygląda identycznie jak zdrowy dzień,
    # więc problem musi trafić do treści zamiast wywalić endpoint.
    # Węziej niż `Exception` świadomie: awaria bazy (psycopg2) i brak konfiguracji
    # (RuntimeError z `_get_pool`) mają być połknięte, a błąd w NASZYM kodzie ma krzyczeć.
    except (psycopg2.Error, RuntimeError) as e:
        problemy.append(f"nie udało się odpytać bazy: {e}")
        _log.error("raport-dzienny: baza niedostępna: %s", e)

    # Zero kuponów to DOKŁADNIE obraz awarii I7 — dzień bez kuponów nie jest zdrowy,
    # nawet jeśli predykcje powstały (wtedy właśnie powstawały).
    if not problemy and kupony == 0:
        problemy.append("ZERO kuponów w ostatniej dobie — draft mógł paść")

    ok = not problemy
    wyslany = _wyslij_raport(ok, kupony, predykcje, rozliczone, problemy)

    return {
        "ok": ok,
        "kupony": kupony,
        "predykcje": predykcje,
        "rozliczone": rozliczone,
        "problemy": problemy,
        "wyslany": wyslany,
    }


def _licz(conn, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int((row["n"] if row else 0) or 0)


def _wyslij_raport(ok: bool, kupony: int, predykcje: int, rozliczone: int,
                   problemy: list[str]) -> bool:
    """Jedna wiadomość dziennie. Trzy osobne uczą wyciszać powiadomienia."""
    try:
        from footstats.utils.telegram_notify import _send

        naglowek = ("✅ <b>FootStats: przebieg dzienny</b>" if ok
                    else "⚠️ <b>FootStats: przebieg dzienny — uwaga</b>")
        tresc = (
            f"{naglowek}\n\n"
            f"kupony (24h): <b>{kupony}</b>\n"
            f"predykcje (24h): <b>{predykcje}</b>\n"
            f"rozliczone (7 dni): <b>{rozliczone}</b>"
        )
        if problemy:
            tresc += "\n\n" + "\n".join(f"• {p}" for p in problemy)
        return bool(_send(tresc))
    # Brak Telegrama nie może wywalić endpointu: Scheduler dostający 500 zapętla
    # retry, a i tak nie ma komu wysłać. `OSError` pokrywa awarie sieci (requests
    # dziedziczy z niego), `ImportError` brak zależności, `ValueError` złą odpowiedź.
    except (OSError, ImportError, ValueError) as e:
        _log.error("raport-dzienny: wiadomosc niewyslana: %s", e)
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
