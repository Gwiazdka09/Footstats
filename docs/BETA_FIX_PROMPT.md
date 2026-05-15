# Prompt do dokończenia Bety i naprawy błędu Migracji

Wklej poniższą treść do Claude, aby naprawić bazę i zamknąć checklistę:

---

## CONTEXT
FootStats (SaaS do analizy meczów). Backend FastAPI, Baza PostgreSQL (Neon). System Multi-User z JWT.

## ISSUE: Migration Failure
Podczas `python manage.py migrate` otrzymuję: `psycopg2.errors.ForeignKeyViolation`. 
Tabela `coupons` próbuje ustawić `user_id = 1` (w migracji v2), ale tabela `users` jest pusta, bo seedowanie admina następuje po wszystkich migracjach.

## TASKS:
1. **Fix migrations.py**: Zmień kolejność tak, aby `seed_admin_user` był wywoływany wewnątrz `run_migrations` zaraz po stworzeniu tabeli `users` (wersja 1), ale PRZED dodaniem kluczy obcych (wersja 2).
2. **Sanity Check**: Stwórz `src/footstats/utils/sanity_check.py` (sprawdzanie API keys i DB).
3. **Postponed Matches**: Logika zwrotów (kurs 1.0) w `coupon_tracker.py`.
4. **Telegram Bot**: Wysyłanie powiadomień o nowych kuponach.
5. **QuickStart Guide**: Instrukcja `docs/QUICKSTART_TESTER.md` dla nietechnicznych znajomych.

## CONSTRAINTS:
- Używaj `psycopg2` i istniejącego `footstats.utils.db.connect`.
- Zachowaj multi-tenancy (zawsze używaj `user_id` z tokena).

---
