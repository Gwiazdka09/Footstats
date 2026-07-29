"""Backfill kont użytkowników ze starego Neona do Supabase (prod) — 1:1 login+hasło.

Kontekst: 2026-07-20 prod DB zmigrowane Neon → Supabase. Konta zarejestrowane
przed migracją (poza re-seedowanym Admin_JG) przepadły w Supabase. bcrypt jest
jednokierunkowy → jedyne źródło loginów+haseł to stary Neon. Neon = quota-block
do resetu ~1.08 → ten skrypt uruchamiamy PO odblokowaniu Neona.

Bezpieczeństwo:
  * TYLKO INSERT do public.users. Zero UPDATE/DELETE, zero innych tabel.
  * Domyślnie DRY-RUN (nic nie zapisuje). Zapis dopiero z flagą --apply.
  * ON CONFLICT (username) DO NOTHING + per-row guard na UNIQUE(email) →
    istniejące konta (Admin_JG, System) NIE są ruszane.
  * id NIE jest przenoszone (serial przydziela nowe) — brak kolizji PK z
    rekordami już w Supabase. Późniejszy backfill kuponów mapuje po username.
  * Po zapisie weryfikuje, że password_hash w Supabase == hash z Neona (login 1:1).

Użycie:
  python scripts/backfill_users_from_neon.py            # dry-run (podgląd)
  python scripts/backfill_users_from_neon.py --apply    # faktyczny zapis
Wymaga w .env: DATABASE_URL_NEON (źródło), DATABASE_URL_SUPABASE (cel).
UWAGA: od 2026-07-29 `DATABASE_URL` wskazuje PRODUKCJĘ (Supabase), nie Neona —
źródło trzymamy pod osobną nazwą, a skrypt przerywa gdy źródło == cel.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg2
import psycopg2.errors
from dotenv import dotenv_values

# Kolumny public.users kopiowane 1:1 (bez `id` — serial nada nowe).
_COPY_COLS = (
    "username",
    "password_hash",
    "email",
    "created_at",
    "is_active",
    "is_admin",
    "telegram_chat_id",
    "telegram_link_nonce",
    "telegram_link_nonce_exp",
)


def _mask_email(email: str | None) -> str:
    if not email:
        return "—"
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}" if domain else "***"


def _connect(url: str | None, label: str):
    if not url:
        sys.exit(f"BŁĄD: brak connection stringa dla {label} w .env")
    try:
        return psycopg2.connect(url, connect_timeout=15)
    except psycopg2.OperationalError as e:
        msg = str(e)
        if "quota" in msg.lower():
            sys.exit(
                f"[{label}] Neon nadal ZABLOKOWANY (quota). Poczekaj na reset "
                f"(~1.08) i odpal ponownie.\n  {msg.strip()[:160]}"
            )
        sys.exit(f"[{label}] CONNECT FAIL: {type(e).__name__}: {msg.strip()[:200]}")


def _cols_intersection(src_con, dst_con) -> list[str]:
    """Kopiujemy tylko kolumny obecne w OBU public.users (odporność na schema-drift)."""
    def cols(con) -> set[str]:
        cur = con.cursor()
        cur.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name='users' AND table_schema='public'"
        )
        return {r[0] for r in cur.fetchall()}

    common = cols(src_con) & cols(dst_con)
    chosen = [c for c in _COPY_COLS if c in common]
    if "username" not in chosen or "password_hash" not in chosen:
        sys.exit("BŁĄD: brak username/password_hash we wspólnych kolumnach — przerwane.")
    return chosen


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill users Neon → Supabase (1:1).")
    ap.add_argument("--apply", action="store_true", help="Faktyczny zapis (domyślnie dry-run).")
    args = ap.parse_args()

    env = dotenv_values(Path(__file__).resolve().parents[1] / ".env")

    # Źródło bierzemy z DATABASE_URL_NEON. Fallback na DATABASE_URL jest wyłącznie
    # wsteczny: od 2026-07-29 DATABASE_URL wskazuje PRODUKCJĘ (Supabase), bo inaczej
    # cała reszta narzędzi i testów integracyjnych celowała w martwego Neona.
    url_src = env.get("DATABASE_URL_NEON") or env.get("DATABASE_URL")
    url_dst = env.get("DATABASE_URL_SUPABASE")

    # Guard: bez tego po podmianie DATABASE_URL skrypt kopiowałby Supabase → Supabase
    # i „udanie" nie zrobiłby nic, maskując brak backfillu.
    if url_src and url_dst and url_src.strip() == url_dst.strip():
        sys.exit(
            "BŁĄD: źródło i cel to ta sama baza. Ustaw DATABASE_URL_NEON na URL Neona "
            "(DATABASE_URL wskazuje teraz Supabase) — przerwane, żeby nie udawać backfillu."
        )

    src = _connect(url_src, "NEON (źródło)")
    dst = _connect(url_dst, "SUPABASE (cel)")

    cols = _cols_intersection(src, dst)
    col_list = ", ".join(cols)

    # Źródło: wszyscy userzy z Neona.
    scur = src.cursor()
    scur.execute(f"SELECT {col_list} FROM public.users ORDER BY username")
    src_rows = scur.fetchall()
    src_by_user = {r[cols.index("username")]: r for r in src_rows}

    # Cel: istniejące loginy + e-maile (do wykrycia kolizji).
    dcur = dst.cursor()
    dcur.execute("SELECT username, email FROM public.users")
    dst_users, dst_emails = set(), set()
    for u, e in dcur.fetchall():
        dst_users.add(u)
        if e:
            dst_emails.add(e)

    to_insert = [u for u in src_by_user if u not in dst_users]
    email_idx = cols.index("email") if "email" in cols else None
    hash_idx = cols.index("password_hash")

    print("=" * 66)
    print(f"Neon users: {len(src_rows)} | Supabase users: {len(dst_users)} "
          f"| do wstawienia: {len(to_insert)}")
    print(f"Kolumny kopiowane: {col_list}")
    print("=" * 66)
    if not to_insert:
        print("Nic do zrobienia — wszystkie konta z Neona już są w Supabase.")
        return
    print(f"{'LOGIN':22} {'EMAIL':22} {'ADMIN':6} {'bcrypt':7} EMAIL_KOLIZJA")
    for u in to_insert:
        r = src_by_user[u]
        email = r[email_idx] if email_idx is not None else None
        h = (r[hash_idx] or "")
        clash = "TAK(skip)" if email and email in dst_emails else ""
        adm = r[cols.index("is_admin")] if "is_admin" in cols else "?"
        print(f"{u:22} {_mask_email(email):22} {str(adm):6} "
              f"{str(h.startswith('$2')):7} {clash}")

    if not args.apply:
        print("\nDRY-RUN — nic nie zapisano. Zapis: dodaj --apply")
        return

    # ── APPLY ──────────────────────────────────────────────────────────────
    placeholders = ", ".join(["%s"] * len(cols))
    insert_sql = (
        f"INSERT INTO public.users ({col_list}) VALUES ({placeholders})"
        f" ON CONFLICT (username) DO NOTHING"
    )
    inserted, skipped = 0, []
    wcur = dst.cursor()
    for u in to_insert:
        row = src_by_user[u]
        try:
            wcur.execute("SAVEPOINT sp")
            wcur.execute(insert_sql, row)
            if wcur.rowcount == 1:
                inserted += 1
            else:
                skipped.append((u, "username już istnieje"))
            wcur.execute("RELEASE SAVEPOINT sp")
        except psycopg2.errors.UniqueViolation:
            wcur.execute("ROLLBACK TO SAVEPOINT sp")
            skipped.append((u, "UNIQUE(email) kolizja"))
    dst.commit()

    # ── WERYFIKACJA 1:1 (hash w Supabase == hash z Neona) ──────────────────
    vcur = dst.cursor()
    vcur.execute(
        "SELECT username, password_hash FROM public.users WHERE username = ANY(%s)",
        (to_insert,),
    )
    dst_hashes = dict(vcur.fetchall())
    mismatches = [
        u for u in to_insert
        if u in dst_hashes and dst_hashes[u] != src_by_user[u][hash_idx]
    ]

    print("\n" + "=" * 66)
    print(f"WSTAWIONO: {inserted} | POMINIĘTO: {len(skipped)}")
    for u, why in skipped:
        print(f"  skip {u}: {why}")
    if mismatches:
        print(f"⚠️ HASH MISMATCH (login NIE 1:1) dla: {mismatches}")
    else:
        print("✅ Wszystkie wstawione konta mają hash 1:1 — stare hasła zadziałają.")
    print("=" * 66)


if __name__ == "__main__":
    main()
