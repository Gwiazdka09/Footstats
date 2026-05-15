"""FootStats Management CLI.

Użycie:
    python manage.py add-user <username> [--email EMAIL]
    python manage.py list-users
    python manage.py migrate
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()


def cmd_add_user(args: argparse.Namespace) -> None:
    import bcrypt
    from footstats.utils.db import connect

    password = args.password or ""
    if not password:
        password = getpass.getpass("Hasło: ")
        password2 = getpass.getpass("Powtórz hasło: ")
        if password != password2:
            print("Hasła nie pasują.", file=sys.stderr)
            sys.exit(1)

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    with connect() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
            (args.username, password_hash, args.email),
        )
    print(f"Użytkownik '{args.username}' utworzony.")


def cmd_list_users(args: argparse.Namespace) -> None:
    from footstats.utils.db import connect

    with connect() as conn:
        rows = conn.execute(
            "SELECT id, username, email, created_at, is_active FROM users ORDER BY id"
        ).fetchall()

    print(f"{'ID':>4}  {'Username':<20}  {'Email':<30}  {'Aktywny':<7}  Utworzono")
    print("-" * 80)
    for r in rows:
        print(
            f"{r['id']:>4}  {r['username']:<20}  {str(r['email'] or ''):<30}"
            f"  {str(r['is_active']):<7}  {str(r['created_at'])[:19]}"
        )


def cmd_migrate(args: argparse.Namespace) -> None:
    from footstats.db.migrations import run_migrations, seed_admin_user

    run_migrations()
    seed_admin_user()
    print("Migracje zakończone.")


def main() -> None:
    parser = argparse.ArgumentParser(description="FootStats Management CLI")
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add-user", help="Dodaj nowego użytkownika")
    p_add.add_argument("username", help="Nazwa użytkownika")
    p_add.add_argument("--password", default="", help="Hasło (lub podaj interaktywnie)")
    p_add.add_argument("--email", default=None, help="E-mail (opcjonalny)")
    p_add.set_defaults(func=cmd_add_user)

    p_list = sub.add_parser("list-users", help="Wyświetl użytkowników")
    p_list.set_defaults(func=cmd_list_users)

    p_migrate = sub.add_parser("migrate", help="Uruchom migracje bazy danych")
    p_migrate.set_defaults(func=cmd_migrate)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
