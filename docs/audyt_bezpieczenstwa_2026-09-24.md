# Audyt bezpieczeństwa — 2026-09-24 (backend + frontend)

**Zakres:** API FastAPI (`src/footstats/api`), warstwa danych, front React/Vite (Cloud Run
i Vercel), zależności, konfiguracja produkcji (Cloud Run, Vercel), CI/CD.
**Metoda:** przegląd kodu + pomiary na żywej produkcji (`curl`, `gcloud`) + skanery
(`bandit`, `pip-audit`, `npm audit`). Każde znalezisko zweryfikowane, nie przypuszczone.
**Zastrzeżenie:** to nie jest audyt zewnętrzny ani porada prawna.

---

## Wynik w jednym zdaniu

Rdzeń uwierzytelniania jest solidny — nie znalazłem drogi do cudzego konta ani do bazy.
**Osiem znalezisk naprawionych**, wszystkie tego samego rodzaju: ochrona była *napisana*,
ale w produkcji *nie działała* albo nie obejmowała ścieżki, którą faktycznie chodzą ludzie.

---

## Naprawione

### 1. Link resetu hasła działał wielokrotnie (najpoważniejsze)

Token resetu niósł tylko `uid` i `exp`, a `reset_password` sprawdzał podpis, `purpose`
i wygaśnięcie. **Nic go nie zużywało**, więc ten sam link ustawiał hasło dowolną liczbę
razy przez 60 minut.

Dlaczego to realne: linki resetu wyciekają inaczej niż hasła — zostają w skrzynce (także
po jej późniejszym przejęciu), w historii przeglądarki, w logach proxy, w kopii maila na
innym urządzeniu. Ofiara resetuje hasło i uznaje, że odzyskała konto; napastnik z tym
samym linkiem ustawia własne hasło w ciągu godziny. Podbicie `token_version` przy resecie
(B1, 17.08) wyrzucało wtedy z sesji **właściciela**, nie napastnika.

Naprawa używa mechanizmu, który już istniał: token niesie `tv` (wersję sesji z chwili
wystawienia), a udany reset tę wersję podbija. Fail closed przy braku claimu, niezgodnej
wersji i nieczytelnej bazie. Commit `355e836d6`.

### 2. Odpowiedź 500 oddawała treść wyjątku psycopg2

17 miejsc w `api/routes` robiło `detail=str(e)`. `str()` wyjątku psycopg2 to opis wnętrza
bazy: nazwa relacji i kolumny, fragment zapytania z pozycją błędu, czasem wartość, która
błąd wywołała. Dla atakującego darmowy zwiad (OWASP API8) — mapa schematu bez ani jednego
udanego wstrzyknięcia. Sześć z tych miejsc nie logowało nic, więc diagnostyka jest teraz
lepsza niż przed zmianą. Commit `87dc19962`.

### 3. Front na Vercelu leciał bez nagłówków bezpieczeństwa

Cała praca nad nagłówkami (B5, 23.08) siedziała w `api/main.py`, czyli obejmowała
**wyłącznie** kopię SPA serwowaną przez Cloud Run. Ludzie wchodzą na
`bot-opal-nu.vercel.app`, a stamtąd wracało tylko `Strict-Transport-Security` (domyślne
Vercela). Zero CSP, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` —
zmierzone `curl -sI`. Front dawał się osadzić w cudzej ramce, z formularzem logowania
i kreatorem kuponu włącznie.

Trzy nagłówki wymuszone + `Permissions-Policy`. CSP startuje jako `Report-Only`, bo front
woła API na innej domenie i `connect-src 'self'` z wersji Cloud Run wygasiłby aplikację.
Commit `c1a750ddf`.

### 4. CSP Report-Only bez adresu raportu = dekoracja

Polityka na Cloud Run jechała jako `Report-Only`, ale nie miała ani `report-uri`, ani
`report-to`. Naruszenia lądowały w konsoli użytkownika i nigdzie dalej — a uzasadnieniem
trybu było „nie mamy jeszcze ani jednego pomiaru naruszeń". Ten warunek nie mógł się nigdy
spełnić. Doszedł `POST /api/csp-report`: publiczny z konieczności, czyta najwyżej 8 KB,
loguje trzy pola po 200 znaków, zawsze 204. Commit `3c6c39ffa`.

### 5. `/metrics` otwarte na produkcji

Bramka brzmiała „gdy `METRICS_TOKEN` ustawiony — sprawdzaj", czyli **brak zmiennej = brak
ochrony**. Na produkcji zmiennej nie ma (`gcloud run services describe`). Nic dziś nie
wycieka wyłącznie dlatego, że `prometheus_client` nie trafił do obrazu i odpowiedź to
`metrics-disabled` — ochroną jest nieobecność biblioteki, nie decyzja, a zależność
przechodnia potrafi ją dołożyć bez niczyjej wiedzy. Teraz na produkcji bez tokenu: 404.
Commit `3c6c39ffa`.

### 6. Uprawnienie admina brane z tokenu, nie z bazy

`require_admin` sprawdzał `payload["adm"]` — flagę z chwili logowania. Token żyje 24 h,
więc `UPDATE users SET is_admin = FALSE` nie robiło nic do końca doby. To dokładnie ta
czynność, którą wykonuje się **po** incydencie. Teraz uprawnienie potwierdza baza;
asymetria zamierzona (nadanie admina wymaga przelogowania, odebranie działa od razu).
Commit `c0acca03f`.

### 7. Trzy podatności `high` we frontendzie

`npm audit`: `vite` 8.0.0–8.0.15 plus przechodnie `nanoid` i `postcss`. CI ich nie
bramkuje — job `frontend` robi tylko `npm ci`, `test` i `build`. Po `npm audit fix`
(sam lockfile, `vite` 8.3.0) — zero podatności. Commit `76aab426c`, wchodzi z PR #30.

### 8. Ręczny kupon bez górnych granic

Walidacja pilnowała dolnych granic i długości napisów, ale nie liczby nóg ani wysokości
stawki. `POST /api/coupon/manual` ze stoma tysiącami nóg lądował w bazie jako jeden
gigantyczny `legs_json`, a `GET /api/coupons` zwraca go potem w całości i potrafi
przekroczyć timeout 10 s. Rejestracja jest otwarta, więc kosztem takiego żądania jest
jedno konto. Limit nóg = 30 (tyle, co w podglądzie, który nic nie zapisuje), stawka
≤ 100 000. Commit `eeadffa99`.

### Przy okazji

* Publiczny ranking oddawał `user_id` każdego uczestnika, choć endpoint obok usuwał to
  pole celowo (OWASP API3) — `019b69d99`.
* Bramka `/cron/*` stała w pięciu kopiach; wszystkie poprawne, ale to układ, w którym
  błąd musi kiedyś powstać (w tym projekcie regułę rozsianą po wejściach pominięto już
  trzy razy) — `afe056d77`.
* `Cache-Control` bez `private` na odpowiedziach uwierzytelnionych + strażnik izolacji
  cache między kontami — `59cb00a2a`.
* Pola `POST /api/settings` bez granic i pola haseł bez `autoComplete` — `1800d9a61`.

---

## Sprawdzone i czyste

| Obszar | Wynik |
|---|---|
| SQL injection | Brak. Zero SQL budowanego f-stringiem z danych wejściowych; szablony z `{}` wstawiają wyłącznie znaki zapytania, wartości idą parametrami |
| Wykonanie polecenia / deserializacja | Brak `shell=True`, brak `eval`/`exec`, brak `pickle.load`, brak `yaml.load` |
| SSRF | Wszystkie scrapery mają zaszyte bazowe adresy; żaden URL nie pochodzi z żądania |
| IDOR na kuponach | Każda mutacja sprawdza `user_id` właściciela i zwraca 403 |
| Autoryzacja tras | `/api/status`, `/api/config`, `/api/coupons`, `/api/terminarz` → 401 bez tokenu (zmierzone na produkcji). Publiczny jest tylko ranking (za zgodą `leaderboard_opt_in`) |
| Enumeracja kont | `/auth/login` oddaje ten sam komunikat dla nieznanego loginu i złego hasła; zablokowane konto **nie sprawdza hasła**; `/auth/forgot-password` zawsze 200 |
| Brute force | Limiter globalny 60/min per klient + 10/min na logowanie i 5/min na rejestrację i reset; klucz to ostatni wpis `X-Forwarded-For`, nie adres pośrednika Cloud Run |
| Blokada konta | Rosnące okno z sufitem 15 min — nie do zamknięcia komuś konta na stałe |
| Hasła | bcrypt z solą per-hasło; uszkodzony hash daje 401, nie 500 |
| Sekrety | Wszystkie przez `secretKeyRef` z Secret Managera; `gitleaks` w CI; w produkcyjnym pakiecie frontu zero kluczy (sprawdzone na pobranym `/assets/index-*.js`) |
| Zależności Pythona | `pip-audit` na oba locki: brak znanych podatności |
| `bandit` | 24 znaleziska, wszystkie LOW, każde z uzasadnieniem `nosec` |
| XSS we froncie | Zero `dangerouslySetInnerHTML`, zero `eval`, zero `innerHTML` |
| Izolacja cache | Klucz zawiera `user_id` wszędzie, gdzie odpowiedź zależy od konta |
| `/docs`, `/openapi.json`, `/mcp` | Wyłączone na produkcji (sprawdzone: 404) |
| Logi | Żadne hasło, hash ani token nie trafia do logu — logowany jest typ wyjątku |

---

## Zostaje do decyzji właściciela

1. **Wymuszenie CSP.** Teraz oba środowiska raportują i mają gdzie raportować. Po kilku
   dniach bez naruszeń: `CSP_ENFORCE=1` na Cloud Run i zamiana nagłówka w `vercel.json`.
   To zmiana konfiguracji produkcji, nie kodu — i przy złej polityce daje białą stronę
   wszystkim naraz, więc najpierw raporty.
2. **`METRICS_TOKEN` na produkcji.** Dziś endpoint milczy (404). Jeśli metryki mają być
   zbierane, trzeba ustawić zmienną; bez niej Prometheus nic nie dostanie.
3. **Token w `localStorage`.** Wektor to XSS, a ten jest obecnie odcięty (`script-src
   'self'`, zero `unsafe-inline`, zero wstrzykiwania HTML w kodzie). Przeniesienie na
   ciasteczko `httpOnly` wymaga obsługi CSRF i dotyka całego frontu — duża zmiana,
   świadomie odłożona, nie przeoczona.
4. **Brak weryfikacji e-maila przy rejestracji.** Konto działa od razu, adres jest
   niepotwierdzony. Przy otwartej rejestracji to droga do zaśmiecania bazy i wysyłania
   maili powitalnych na cudze adresy. Decyzja produktowa, nie techniczna.
5. **`ALLOWED_ORIGINS` zawiera stary host Cloud Run** (`...949240532526...` obok
   działającego). Nie jest to luka — oba wskazują tę samą usługę — ale lista powinna
   zawierać dokładnie to, co jest w użyciu.
6. **`POST /api/settings` wygląda na martwy** — GUI czyta `/settings`, ale nigdzie nie
   zapisuje (sekcja „Algorytm & Ryzyko" została usunięta 10.09). Jeśli nie wróci, endpoint
   można skasować; do tego czasu ma przynajmniej granice pól.

---

## Czego ten audyt NIE obejmował

* Testu penetracyjnego z zewnątrz (żadnego skanowania aktywnego produkcji).
* Przeglądu uprawnień IAM w Google Cloud i zasad dostępu do Secret Managera.
* Bezpieczeństwa samego konta Supabase (role, RLS, kopie).
* Zależności `npm` pod kątem typosquattingu i przeglądu kodu paczek.
* Dostępności i integralności kopii zapasowych (`backup.yml` działa, ale nie próbowałem
  odtworzenia z kopii).
