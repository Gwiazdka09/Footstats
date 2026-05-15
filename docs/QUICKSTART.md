# FootStats — Instrukcja dla Testerów Beta

## Wymagania

- Python 3.11+
- Node.js 18+ (tylko przy lokalnym buildzie frontendu)
- Konto na [Neon.tech](https://neon.tech) (darmowy PostgreSQL w chmurze)
- Klucze API: Groq (obowiązkowy), pozostałe opcjonalne

---

## 1. Klonowanie i instalacja

```bash
git clone <repo_url>
cd bot
python -m venv .venv
source .venv/Scripts/activate   # Windows
# source .venv/bin/activate     # Linux/Mac

pip install -e .
```

---

## 2. Konfiguracja `.env`

```bash
cp .env.example .env
```

Uzupełnij `.env` minimalnymi wartościami:

| Zmienna | Skąd | Wymagana |
|---------|------|----------|
| `DATABASE_URL` | Neon.tech → Connection String | ✅ |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | ✅ |
| `JWT_SECRET` | `python -c "import secrets; print(secrets.token_hex(32))"` | ✅ |
| `SECRET_KEY` | jak wyżej | ✅ |
| `BZZOIRO_KEY` | [sports.bzzoiro.com](https://sports.bzzoiro.com) | zalecany |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) | opcjonalny |
| `TELEGRAM_CHAT_ID` | Twoje user ID w Telegram | opcjonalny |

---

## 3. Sprawdzenie konfiguracji

```bash
python scripts/sanity_check.py
```

Powinno wyświetlić `PASS`. Jeśli nie — uzupełnij brakujące zmienne z komunikatu.

---

## 4. Migracje bazy danych

```bash
python manage.py migrate
```

Tworzy tabele i domyślnego admina (id=1).

---

## 5. Dodanie użytkownika

```bash
python manage.py add-user jakub --email jakub@example.com
```

Hasło zostanie zapytane interaktywnie.

---

## 6. Uruchomienie API

```bash
python -m uvicorn footstats.api.main:app --host 0.0.0.0 --port 8000
```

Dashboard dostępny pod: `http://localhost:8000`

---

## 7. Generowanie kuponów (ręcznie)

```bash
python -m footstats.daily_agent --stawka 10 --dni 3
```

Kupony pojawią się w `logs/kupon_YYYY-MM-DD.txt` i (jeśli skonfigurowany) na Telegramie.

---

## 8. Sprawdzenie wyników wieczorem

```bash
python -m footstats.evening_agent
```

Aktualizuje status kuponów na podstawie API-Football.

---

## 9. Docker (alternatywa)

```bash
docker build -t footstats .
docker run -p 8000:8000 --env-file .env footstats
```

---

## Codzienny harmonogram (automatyczny)

| Czas | Skrypt |
|------|--------|
| 08:00 | `daily_agent` — generuje kupony |
| 23:00 | `evening_agent` — rozlicza wyniki |

Konfiguracja przez Task Scheduler (Windows) lub cron (Linux): `scripts/run_daily.bat`

---

## Zgłaszanie błędów

Opisz:
1. Co robiłeś
2. Pełny komunikat błędu (log z terminala)
3. Wynik `python scripts/sanity_check.py`
