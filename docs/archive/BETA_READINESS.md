# FootStats — Beta Readiness Roadmap

Ten dokument określa kroki niezbędne do udostępnienia projektu pierwszym zewnętrznym testerom (Beta).

## 🎯 Cel
Przejście z systemu "localhost-only" do bezpiecznego, stabilnego środowiska, które znajomi mogą uruchomić u siebie lub do którego mogą dostać dostęp przez centralny Dashboard.

---

## 🛠️ CHECKLISTA BETA

### 1. Bezpieczeństwo i Konfiguracja
- [x] **`.env.example`**: Stworzenie kompletnego szablonu zmiennych środowiskowych.
- [x] **Sanity Check**: Skrypt sprawdzający przed uruchomieniem, czy wszystkie klucze API są poprawne.
- [x] **Brak Hardcodowania**: Ścieżki bazują na `Pathlib` i relatywnych odniesieniach.

### 2. Multi-User & Izolacja (ZREALIZOWANE ✅)
- [x] **Database Scoping**: Każdy użytkownik ma własne `user_id` w tabelach `coupons`, `bankroll` i `settings`.
- [x] **Profesjonalny Auth System**: Logowanie oparte o JWT i tabelę `users` (z hashowaniem bcrypt).
- [x] **Bezpieczeństwo Dashboardu**: React Dashboard wymaga autoryzacji (Bearer Token) przed dostępem do danych.
- [x] **Instancjonowanie**: Model centralnego serwera (Cloud Run) z separacją danych w Postgresie.

### 3. Stabilność Operacyjna
- [ ] **Graceful Failover**: Automatyczne przełączanie scraperów (Superbet -> Flashscore).
- [ ] **Postponed Matches**: Automatyczna obsługa meczów przełożonych.
- [x] **Docker**: Wieloetapowy build (React + Python) gotowy do wdrożenia.

### 4. User Experience (UX)
- [x] **QuickStart Guide**: Instrukcja dla testerów.
- [x] **Notification Bot (V1)**: Wysyłanie kuponów na Telegram.
- [x] **Calibration Status**: Data ostatniej kalibracji modelu Poisson na UI.

---

## 🚀 PROJEKTOWY "DONE DEFINITION" DLA BETY
1. [x] System działa w kontenerze Docker (Multi-stage build).
2. [x] Nowy użytkownik może zostać dodany przez `manage.py add-user`.
3. [x] Dashboard React jest zintegrowany z API i obsługuje Multi-User.

---

## 📝 NOTATKI ARCHITEKTONICZNE
- **Baza Danych**: Używamy **PostgreSQL (Neon.tech)** jako standardu produkcyjnego.
- **Deployment**: Google Cloud Run (Serverless) jako platforma hostująca.
- **Frontend**: React (Vite) serwowany statycznie przez FastAPI.
