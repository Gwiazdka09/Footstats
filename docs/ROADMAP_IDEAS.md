# FootStats — Pomysły i Roadmap

**Ostatnia aktualizacja:** 2026-06-06  
**Stan:** v3.4-stable | Accuracy: 26.7% live | Cel: M1=55% win rate

---

## 🔴 KRYTYCZNE (blokują accuracy — zrób przed betą)

### 1. Filtr ligowy — odrzucaj mecze bez danych Poisson
- Przed dodaniem meczu do kandydatów sprawdź czy `predict_match()` != None
- Jeśli None → skip (towarzyskie Afryka/Azja/CONCACAF bez historii)
- Efekt: mniej kuponów, ale znacznie lepsze
- **Effort:** 2–3h | Plik: `daily_agent.py` krok 1

### 2. Minimum decision_score=50 dla DRAFT (podnieść próg)
- Teraz `PROG_DRAFT=40` → bierze zbyt słabe mecze
- Podnieść do 50–55, ewentualnie dynamicznie (jeśli < 5 kandydatów → akceptuj 40)
- **Effort:** 30 min | Plik: `core/decision_score.py`

### 3. Kalibracja modelu (po 50 settled kuponów)
- Uruchom: `python -m footstats.core.probability_calibrator`
- A/B test wag ensemble: 50/50 → 60/40 → 70/30 Poisson/Bzzoiro
- **Effort:** 1–2h | Czekać: ~3 tygodnie na dane

---

## 🟡 WAŻNE (poprawiają UX i reliability)

### 4. Stop-loss mechanizm
- Auto-pause gdy strata > 20% bankrollu w ciągu 7 dni
- Telegram alert + status `PAUSED` w bazie
- Wznawianie manualne przez dashboard
- **Effort:** 3–4h

### 5. Liga whitelist/blacklist w configu
- `config.py`: `ALLOWED_LEAGUES = ["Premier League", "Bundesliga", "Serie A", ...]`
- Scraper odrzuca automtycznie ligi spoza listy
- Użytkownik edytuje listę przez dashboard
- **Effort:** 2h

### 6. Lepsze rozliczanie kuponów (FlashScore fallback)
- Teraz FlashScore.mobi często nie znajduje meczów towarzyskich
- Dodać fallback: API-Football (już mamy klucz) → szukaj po nazwie drużyny
- **Effort:** 3–4h | Plik: `core/coupon_settlement.py`

### 7. CLV (Closing Line Value) tracking
- Porównuj kurs w momencie obstawiania vs kurs zamknięcia
- Positive CLV = długoterminowa edge → ważniejszy od win rate krótkoterminowego
- Zapis do tabeli `predictions` (kolumny już przygotowane)
- **Effort:** 3–5h

### 8. Void kuponów dla meczów przełożonych/odwołanych
- Teraz ACTIVE wisią w nieskończoność gdy mecz odwołany
- Sprawdzaj status w API-Football, jeśli `CANCELLED/POSTPONED` → VOID automatycznie
- **Effort:** 2h

---

## 🟢 FAJNE (nice to have, po M1)

### 9. Telegram — interaktywne komendy
- `/status` → bankroll + accuracy + otwarte kupony
- `/kupon` → dzisiejsza propozycja
- `/void 33` → ręczny void kuponu
- `/stats` → wykres accuracy 30 dni
- **Effort:** 4–6h | Plik: `utils/telegram_notify.py` + webhook

### 10. Dashboard UX v2
- Filtrowanie kuponów: liga / data / typ / status
- Wykres bankroll over time (Chart.js)
- Accuracy per liga (Premier League vs Ekstraklasa)
- Accuracy per typ zakładu (Over 2.5 vs 1X2)
- **Effort:** 1–2 dni

### 11. Value bet alert — push notification
- Gdy agent znajdzie mecz z EV > 15% → natychmiastowy Telegram push
- Nie czekaj do rana, alert w momencie detekcji
- **Effort:** 2h

### 12. Ekspansja danych historycznych
- Dodać Ekstraklasa, Eredivisie, Primeira Liga do Understat
- Scraper wyników z FBref (ma dane dla większości lig)
- Więcej danych = lepsza kalibracja Poissona dla mniejszych lig
- **Effort:** 3–5 dni

### 13. Odds comparison — STS/Fortuna/LV BET
- Sprawdzaj kursy u 3 bukmacherów przed obstawieniem
- Wybierz najwyższy kurs (max value)
- Playwright login dla każdego (już mamy Superbet jako template)
- **Effort:** 1–2 tygodnie

### 14. Backtest na danych historycznych 2024–2025
- Uruchom pipeline na historycznych meczach top 5 lig
- Sprawdź: jaka accuracy była gdyby bot działał przez cały sezon?
- Potrzebne do credibility przy onboardingu beta testerów
- **Effort:** 2–3 dni | Plik: `core/backtest_engine.py` (już istnieje)

---

## 🔵 DUŻE FEATURE'Y (miesiące pracy, po beta)

### 15. Multi-user — każdy ze swoim bankrollem i ryzykiem
- Per-user: bankroll, stake%, risk profile (conservative/aggressive)
- Per-user Telegram chat_id
- Admin panel do zarządzania użytkownikami
- **Effort:** 1–2 tygodnie

### 16. SaaS — płatny dostęp
- Stripe integration (subskrypcja miesięczna)
- Tier darmowy: 1 kupon/dzień | Pro: wszystkie kupony + statystyki
- **Effort:** 2–3 tygodnie

### 17. Mobile app (PWA)
- Service Worker + offline support
- Push notifications (zamiast Telegrama)
- Instalowalna na iOS/Android
- **Effort:** 3–5 dni (Streamlit → React)

### 18. Automatyczne obstawianie (integracja z bukmacherem)
- Playwright auto-login → auto-bet gdy kupon zatwierdzony
- BARDZO ryzykowne — wymaga pełnego stop-loss, limitów, audytu
- Regulacyjnie szara strefa w PL
- **Effort:** 2–4 tygodnie | ⚠️ Konsultacja prawna przed

---

## Milestones

| Milestone | Warunek | Co odblokuje |
|-----------|---------|--------------|
| **M1** 55% win rate | 50 settled + kalibracja | Beta testerów |
| **M2** 60% win rate | Tuning wag + filtr lig | Stop-loss + CLV |
| **M3** 65% selected | Multi-liga + odds comparison | SaaS pricing |
| **M4** SaaS | Stripe + multi-user | Monetyzacja |

---

## Notatki / Odrzucone pomysły

- **Arbitraż** — wymaga kont u wielu bukmacherów równocześnie, limity kont; poza scopem
- **Lay betting (Betfair)** — brak polskiej licencji Betfair Exchange; nie możliwe
- **GPT-4 zamiast Groq** — 10x droższy, Llama 3.1 wystarczy dla JSON scoring
