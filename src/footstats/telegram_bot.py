"""
telegram_bot.py – Interaktywny bot Telegram dla FootStats.

Komendy:
    /status  – aktualny bankroll, drawdown, status agenta
    /kupon   – ostatni aktywny kupon
    /void <id> – void kuponu po ID
    /stats   – accuracy, P&L, ROI (ostatnie 20)

Uruchomienie:
    python -m footstats.telegram_bot

Wymagania .env:
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHAT_ID=...     (tylko dozwolone chat_id)
"""

import json
import logging
import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org/bot{token}/{method}"
POLL_TIMEOUT = 30


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _allowed_chat() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "").strip()


def _get_updates(offset: int | None = None) -> list[dict]:
    params: dict = {"timeout": POLL_TIMEOUT, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    try:
        r = requests.get(
            API_BASE.format(token=_token(), method="getUpdates"),
            params=params,
            timeout=POLL_TIMEOUT + 5,
        )
        data = r.json()
        return data.get("result", []) if data.get("ok") else []
    except (requests.RequestException, ValueError):
        return []


def _reply(chat_id: int | str, text: str) -> None:
    try:
        requests.post(
            API_BASE.format(token=_token(), method="sendMessage"),
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except requests.RequestException as e:
        logger.warning("Telegram reply failed: %s", e)


# ── Command handlers ──────────────────────────────────────────────────────────

def _cmd_status() -> str:
    try:
        from footstats.core.bankroll import (
            get_current_bankroll, get_weekly_drawdown,
            is_agent_paused, get_loss_streak,
        )
        from footstats.utils.admin_user import resolve_admin_user_id
        uid = resolve_admin_user_id()
        bankroll = get_current_bankroll(uid)
        dd = get_weekly_drawdown(uid)
        paused = is_agent_paused()
        streak = get_loss_streak(uid)
        status = "⛔ PAUZOWANY" if paused else "✅ AKTYWNY"
        return (
            f"<b>FootStats Status</b> — {datetime.now():%Y-%m-%d %H:%M}\n"
            f"💰 Bankroll: <b>{bankroll:.0f} PLN</b>\n"
            f"📉 Drawdown 7d: <b>{dd:+.1%}</b>\n"
            f"🔴 Streak strat: <b>{streak}</b>\n"
            f"🤖 Agent: <b>{status}</b>"
        )
    except (ImportError, RuntimeError, OSError) as e:
        return f"Błąd: {e}"


def _cmd_kupon() -> str:
    try:
        from footstats.utils.db import connect
        with connect() as conn:
            row = conn.execute(
                "SELECT id, status, total_odds, stake_pln, legs_json, created_at"
                " FROM coupons ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return "Brak kuponów w bazie."
        legs = json.loads(row["legs_json"] or "[]")
        legs_txt = "\n".join(
            f"  • {l.get('home','?')} vs {l.get('away','?')} — {l.get('tip','?')} @ {l.get('odds',0):.2f}"
            for l in legs[:6]
        )
        return (
            f"<b>Kupon #{row['id']}</b> [{row['status']}]\n"
            f"Kurs łączny: {row['total_odds']:.2f}x  |  Stawka: {row['stake_pln']:.0f} PLN\n"
            f"Data: {str(row['created_at'])[:10]}\n"
            f"{legs_txt}"
        )
    except (ImportError, RuntimeError, OSError) as e:
        return f"Błąd: {e}"


def _cmd_void(coupon_id: str) -> str:
    try:
        cid = int(coupon_id.strip())
    except ValueError:
        return "Użycie: /void <id>"
    try:
        from footstats.utils.db import connect
        with connect() as conn:
            conn.execute("UPDATE coupons SET status='VOID' WHERE id=%s", (cid,))
        return f"✅ Kupon #{cid} → VOID"
    except (ImportError, RuntimeError, OSError) as e:
        return f"Błąd: {e}"


def _cmd_stats() -> str:
    try:
        from footstats.utils.db import connect
        with connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt,"
                " SUM(CASE WHEN tip_correct=1 THEN 1 ELSE 0 END) AS won,"
                " SUM(CASE WHEN tip_correct=1 THEN (odds-1)*10 ELSE -10 END) AS pnl"
                " FROM (SELECT tip_correct, odds FROM predictions"
                "       WHERE tip_correct IS NOT NULL ORDER BY created_at DESC LIMIT 20) sub"
            ).fetchone()
        if not row or not row["cnt"]:
            return "Brak danych (< 1 settled)."
        cnt = row["cnt"]
        won = row["won"] or 0
        pnl = float(row["pnl"] or 0)
        acc = won / cnt * 100
        return (
            f"<b>Stats — ostatnie {cnt} zakładów</b>\n"
            f"✅ Accuracy: <b>{acc:.1f}%</b>\n"
            f"💵 P&L (10 PLN flat): <b>{pnl:+.1f} PLN</b>\n"
            f"📊 ROI: <b>{pnl / (cnt * 10) * 100:+.1f}%</b>"
        )
    except (ImportError, RuntimeError, OSError) as e:
        return f"Błąd: {e}"


# ── Dispatcher ────────────────────────────────────────────────────────────────

def _handle(message: dict) -> None:
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "").strip()

    allowed = _allowed_chat()
    if allowed and chat_id != allowed:
        logger.warning("Odrzucono wiadomość z nieautoryzowanego chat_id: %s", chat_id)
        return

    if not text.startswith("/"):
        return

    parts = text.split(None, 1)
    cmd = parts[0].lower().split("@")[0]
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/status":
        _reply(chat_id, _cmd_status())
    elif cmd == "/kupon":
        _reply(chat_id, _cmd_kupon())
    elif cmd == "/void":
        _reply(chat_id, _cmd_void(arg))
    elif cmd == "/stats":
        _reply(chat_id, _cmd_stats())
    elif cmd == "/help":
        _reply(chat_id, (
            "<b>FootStats Bot</b>\n"
            "/status — bankroll, drawdown, streak\n"
            "/kupon  — ostatni kupon\n"
            "/void &lt;id&gt; — void kuponu\n"
            "/stats  — accuracy + P&amp;L ostatnie 20"
        ))
    else:
        _reply(chat_id, f"Nieznana komenda: {cmd}. Użyj /help")


def run_polling() -> None:
    """Długi polling — uruchom jako daemon (Windows Task Scheduler lub nssm)."""
    if not _token():
        raise RuntimeError("TELEGRAM_BOT_TOKEN nie ustawiony w .env")
    logger.info("FootStats Telegram bot — start polling")
    offset: int | None = None
    while True:
        updates = _get_updates(offset)
        for upd in updates:
            offset = upd["update_id"] + 1
            msg = upd.get("message")
            if msg:
                try:
                    _handle(msg)
                except (RuntimeError, KeyError, ValueError) as e:
                    logger.error("handle error: %s", e)
        if not updates:
            time.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_polling()
