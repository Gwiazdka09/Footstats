# FootStats — Plan Beta Launch + Analiza 2026-05-20

## Stan aktualny

- **Hosting:** Google Cloud Run (Dockerfile.api → uvicorn)
- **DB:** PostgreSQL (Neon.tech) via DATABASE_URL
- **Frontend:** preview.html (1256 linii, SPA z Tailwind) + GUI React (gui/dist/)
- **Auth:** JWT (24h expiry), bcrypt, multi-user z migracjami
- **URL:** https://footstats-api-949240532526.europe-west1.run.app/preview
- **PWA:** manifest.json + sw.js zarejestrowany — strona instalowalna na telefonie

---

## KRYTYCZNE BUGI DO NAPRAWY

### Bug #1: Bankroll — "null value in column id"

**Przyczyna:** Tabela `bankroll_state` w DDL (main.py:147) ma:
```sql
CREATE TABLE IF NOT EXISTS bankroll_state (
    id         INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton!
    balance    REAL NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```
Migracja v2 usunela CHECK i dodala `user_id`, ale kolumna `id` nadal nie ma GENERATED ALWAYS AS IDENTITY. Gdy `api/routes/bankroll.py` robi INSERT z `(user_id, balance, updated_at)` — PostgreSQL nie wie jakie `id` wstawic → NULL → error.

**Dodatkowy problem:** `bankroll.py:23` robi `INSERT INTO bankroll_state (user_id, balance)` — ten sam problem.

### Bug #2: Brak aktualnych meczy

**Przyczyna:** Endpoint `/api/matches/today` wywoluje `_fetch_predictions()` (coupons.py:30). Logika:
1. Probuje BzzoiroClient z env BZZOIRO_KEY
2. Jesli brak klucza lub blad → fallback `_mock_predictions()` (3 statyczne mecze)
3. Filtr: `now < dt <= cutoff(48h)` — mock mecze maja daty "jutro/pojutrze" wiec powinny przejsc

**Mozliwe przyczyny:**
- BZZOIRO_KEY nie ustawiony w Cloud Run env vars
- BzzoiroClient zwraca pusty response → fallback dziala ale mecze sie filtruja
- Cache TTL 600s moze serwowac stale dane

---

## FAZA 0: Naprawa krytycznych bugow (Dzien 1-2)

### Zakres
- Fix bankroll_state id generation
- Fix brak meczy
- Weryfikacja na produkcji

### Claude Code Prompt — Faza 0

```
Tryb: caveman ultra. Bez wyjasnien, czyste zmiany. Projekt: F:\bot

=== TASK 1: Fix bankroll_state id ===

1. Nowa migracja v3 w src/footstats/db/migrations.py:
   Dodaj do MIGRATIONS:
   (3, "fix_bankroll_state_id_generation", [
       "ALTER TABLE bankroll_state ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY",
       "SELECT setval(pg_get_serial_sequence('bankroll_state', 'id'), COALESCE((SELECT MAX(id) FROM bankroll_state), 0) + 1)",
   ])

   UWAGA: Jesli powyzsze nie zadziala (PG moze nie pozwolic ALTER istniejacego PK),
   alternatywa — uzyj sekwencji:
   (3, "fix_bankroll_state_id_generation", [
       "CREATE SEQUENCE IF NOT EXISTS bankroll_state_id_seq",
       "SELECT setval('bankroll_state_id_seq', COALESCE((SELECT MAX(id) FROM bankroll_state), 0) + 1)",
       "ALTER TABLE bankroll_state ALTER COLUMN id SET DEFAULT nextval('bankroll_state_id_seq')",
   ])

2. W src/footstats/api/routes/bankroll.py:25, zmien INSERT na:
   "INSERT INTO bankroll_state (user_id, balance, updated_at) VALUES (?, ?, ?)"
   " ON CONFLICT (user_id) DO UPDATE"
   " SET balance=EXCLUDED.balance, updated_at=EXCLUDED.updated_at",
   (user_id, data.balance, now),
   
   UWAGA: Nie wstawiaj `id` — niech PG uzyje SERIAL/sequence.

3. Dodaj test tests/test_bankroll_api.py:
   - mock _connect()
   - test_update_bankroll_new_user → INSERT bez id, sprawdz brak bledu
   - test_update_bankroll_existing_user → ON CONFLICT UPDATE

=== TASK 2: Fix brak meczy ===

1. src/footstats/api/routes/coupons.py — popraw _mock_predictions():
   Zamien statyczne daty na dynamiczne:
   ```python
   from datetime import datetime, timedelta
   tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
   day2 = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
   ```
   To juz jest! Problem jest gdzie indziej.

2. Dodaj logging do _fetch_predictions():
   ```python
   import logging
   _log = logging.getLogger(__name__)
   
   def _fetch_predictions() -> list:
       try:
           from footstats.scrapers.bzzoiro import BzzoiroClient
           from footstats.config import ENV_BZZOIRO
           key = os.getenv(ENV_BZZOIRO, "").strip()
           _log.info("BZZOIRO_KEY present: %s, length: %d", bool(key), len(key))
           if not key:
               _log.warning("Brak BZZOIRO_KEY — using mock predictions")
               return _mock_predictions()
           client = BzzoiroClient(key)
           preds = client.predykcje_tygodnia()
           _log.info("Bzzoiro returned %d predictions", len(preds) if preds else 0)
           return preds if preds else _mock_predictions()
       except Exception as e:
           _log.error("_fetch_predictions error: %s", e, exc_info=True)
           return _mock_predictions()
   ```

3. Sprawdz w Cloud Run czy BZZOIRO_KEY jest w env vars.
   Jesli nie: gcloud run services update footstats-api --set-env-vars BZZOIRO_KEY=<klucz>

=== TASK 3: Deploy i test ===

git add -A && git commit -m "fix: bankroll id generation + match fetch logging"
# Deploy do Cloud Run (CI/CD lub reczny push)
```

---

## FAZA 1: Zabezpieczenia przed beta (Dzien 3-5)

### Zakres
- Endpoint rejestracji
- Auto-seed bankroll dla nowych userow
- Rate limiting na auth
- CORS origins

### Claude Code Prompt — Faza 1

```
Tryb: caveman ultra. Projekt: F:\bot

=== TASK 1: Endpoint rejestracji ===

W src/footstats/api/auth.py dodaj:

class RegisterRequest(BaseModel):
    username: str
    password: str

@router.post("/auth/register", response_model=TokenResponse)
def register(req: RegisterRequest):
    if len(req.username) < 3 or len(req.password) < 6:
        raise HTTPException(400, "Min 3 znaki login, 6 znakow haslo")
    from footstats.utils.db import connect
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (req.username,)
        ).fetchone()
        if existing:
            raise HTTPException(409, "Uzytkownik juz istnieje")
        hashed = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
        row = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?) RETURNING id",
            (req.username, hashed),
        ).fetchone()
        user_id = row["id"]
        # Auto-seed bankroll
        conn.execute(
            "INSERT INTO bankroll_state (user_id, balance, updated_at)"
            " VALUES (?, 0, CURRENT_TIMESTAMP)",
            (user_id,),
        )
    return TokenResponse(access_token=_make_token(req.username, user_id))

=== TASK 2: Rate limit na auth ===

W src/footstats/api/main.py, po limiter = Limiter(...):
Zmien domyslny limit na auth endpoints.

W auth.py dodaj:
from slowapi import Limiter
from slowapi.util import get_remote_address

# Na poczatku pliku
from fastapi import Request

Zmien login i register:
@router.post("/auth/login")
@limiter.limit("10/minute")
def login(request: Request, req: LoginRequest):

@router.post("/auth/register")  
@limiter.limit("5/minute")
def register(request: Request, req: RegisterRequest):

Uwaga: limiter musi byc importowany z main.py lub przekazany inaczej.
Najprostrze: w main.py po app creation dodaj:
  auth_router.app = app  # slowapi needs app reference
Lub uzyj shared limiter instance.

=== TASK 3: CORS ===

Sprawdz .env ALLOWED_ORIGINS — dodaj:
ALLOWED_ORIGINS=https://footstats-api-949240532526.europe-west1.run.app,http://localhost:8000,http://localhost:5173

=== TASK 4: Test rejestracji ===

tests/test_auth_register.py:
- test_register_success: nowy user, sprawdz token + bankroll seeded
- test_register_duplicate: 409
- test_register_short_password: 400
- test_register_short_username: 400

git add -A && git commit -m "feat: user registration + rate limiting + CORS"
```

---

## FAZA 2: Multi-user onboarding (Dzien 6-10)

### Zakres
- Ekran "ustaw bankroll" po rejestracji (GUI)
- Formularz rejestracji w preview.html
- PWA — "dodaj do ekranu glownego" na telefonie
- Strona → odrazu login, bez landing page

### Claude Code Prompt — Faza 2

```
Tryb: caveman ultra. Projekt: F:\bot

=== TASK 1: Dodaj rejestracje do preview.html ===

W src/footstats/api/preview.html, w sekcji #login-overlay:

Pod przyciskiem "Zaloguj" dodaj link:
<p class="text-center text-sm text-slate-400 mt-4">
  Nie masz konta? 
  <span onclick="showRegister()" class="text-indigo-400 cursor-pointer hover:underline">Zaloz konto</span>
</p>

Dodaj nowy overlay #register-overlay (analogiczny do login):
<div id="register-overlay" class="hidden" style="position:fixed;inset:0;background:rgba(0,0,0,0.85);display:flex;align-items:center;justify-content:center;z-index:1000">
  <div class="login-box">
    <h2 class="text-xl font-bold text-center mb-1 text-white">FootStats</h2>
    <p class="text-center text-slate-400 text-xs mb-6">Stworz konto</p>
    <input id="reg-user" class="login-input" type="text" placeholder="Login (min. 3 znaki)" />
    <input id="reg-pass" class="login-input" type="password" placeholder="Haslo (min. 6 znakow)" />
    <input id="reg-pass2" class="login-input" type="password" placeholder="Powtorz haslo" />
    <div id="reg-err" class="text-xs text-rose-400 hidden"></div>
    <button onclick="doRegister()" class="w-full py-3 bg-indigo-500 hover:bg-indigo-600 text-white font-bold rounded-xl transition-all text-sm">Zaloz konto</button>
    <p class="text-center text-sm text-slate-400 mt-4">
      Masz konto? <span onclick="showLogin()" class="text-indigo-400 cursor-pointer hover:underline">Zaloguj sie</span>
    </p>
  </div>
</div>

Dodaj JS:
function showRegister() {
  document.getElementById('login-overlay').classList.add('hidden');
  document.getElementById('register-overlay').classList.remove('hidden');
}

async function doRegister() {
  const user = document.getElementById('reg-user').value.trim();
  const pass = document.getElementById('reg-pass').value;
  const pass2 = document.getElementById('reg-pass2').value;
  const err = document.getElementById('reg-err');
  err.classList.add('hidden');
  if (pass !== pass2) { err.textContent = 'Hasla nie sa takie same'; err.classList.remove('hidden'); return; }
  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ username: user, password: pass })
    });
    const data = await res.json();
    if (!res.ok) { err.textContent = data.detail || 'Blad rejestracji'; err.classList.remove('hidden'); return; }
    localStorage.setItem('fs_token', data.access_token);
    document.getElementById('register-overlay').classList.add('hidden');
    showBankrollSetup();  // po rejestracji pokaz "ustaw bankroll"
    loadAll();
  } catch(e) { err.textContent = 'Blad polaczenia'; err.classList.remove('hidden'); }
}

=== TASK 2: Ekran "ustaw bankroll" ===

Dodaj overlay #bankroll-setup (tylko po rejestracji, nie po loginie):
<div id="bankroll-setup" class="hidden" style="position:fixed;inset:0;background:rgba(0,0,0,0.85);display:flex;align-items:center;justify-content:center;z-index:1000">
  <div class="login-box">
    <h2 class="text-xl font-bold text-center mb-1 text-white">Ustaw bankroll</h2>
    <p class="text-center text-slate-400 text-xs mb-6">Ile PLN przeznaczasz na typowanie?</p>
    <input id="setup-bankroll" class="login-input" type="number" placeholder="np. 100" min="1" step="1" />
    <button onclick="saveBankroll()" class="w-full py-3 bg-emerald-500 hover:bg-emerald-600 text-white font-bold rounded-xl transition-all text-sm">Zapisz</button>
  </div>
</div>

JS:
function showBankrollSetup() {
  document.getElementById('bankroll-setup').classList.remove('hidden');
}
async function saveBankroll() {
  const val = parseFloat(document.getElementById('setup-bankroll').value);
  if (!val || val < 1) return;
  await apiFetch('/api/bankroll', { method: 'POST', body: JSON.stringify({ balance: val }) });
  document.getElementById('bankroll-setup').classList.add('hidden');
  loadAll();
}

=== TASK 3: Strona startowa → od razu login ===

W main.py, zmien route "/" :
Zamiast RedirectResponse(url="/preview") daj:
return RedirectResponse(url="/preview")  # juz jest ok

W preview.html na poczatku JS (loadAll):
Jesli brak tokenu → showLogin() od razu (juz dziala: linia 785).
Nie dodawaj zadnego landing page, hero section, ani wyjasnienia.
Strona = login → dashboard. Zero upiekszen.

=== TASK 4: PWA "dodaj do telefonu" ===

PWA juz dziala (manifest.json + sw.js + meta tagi).
Dodaj baner instalacyjny w preview.html:

JS (na koncu skryptu):
let deferredPrompt;
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  document.getElementById('pwa-install-btn').classList.remove('hidden');
});

function installPWA() {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  deferredPrompt.userChoice.then(() => {
    document.getElementById('pwa-install-btn').classList.add('hidden');
    deferredPrompt = null;
  });
}

HTML (w sidebar, na dole nawigacji):
<button id="pwa-install-btn" onclick="installPWA()" class="hidden nav-item w-full text-left">
  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 18v-6m0 0V6m0 6h6m-6 0H6"/></svg>
  Zainstaluj apke
</button>

git add -A && git commit -m "feat: register flow + bankroll setup + PWA install"
```

---

## FAZA 3: Beta launch — znajomi (Dzien 11+)

### Zakres
- Stworzenie kont lub self-registration
- Monitoring i feedback
- Disclaimer prawny
- Opcjonalnie: custom domain

### Claude Code Prompt — Faza 3

```
Tryb: caveman ultra. Projekt: F:\bot

=== TASK 1: Disclaimer prawny ===

W src/footstats/api/preview.html, w login-overlay i register-overlay,
na dole (po linkach "Zaloz konto" / "Zaloguj sie"):

<p class="text-center text-[10px] text-slate-500 mt-6 leading-relaxed">
  FootStats to narzedzie analityczne w fazie beta.<br>
  Nie stanowi porady finansowej ani zachety do hazardu.<br>
  Korzystasz na wlasna odpowiedzialnosc.
</p>

=== TASK 2: Feedback button ===

W sidebar preview.html, dodaj nad "Zainstaluj apke":
<a href="https://forms.gle/TWOJ_LINK_DO_FORMULARZA" target="_blank" class="nav-item w-full text-left">
  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/></svg>
  Zglos feedback
</a>

TASK 3: Sentry monitoring — juz skonfigurowany (main.py). Sprawdz .env:
SENTRY_DSN=https://...@sentry.io/...
Jesli brak → stworz projekt na sentry.io (free tier) i dodaj DSN.

TASK 4: Wlasna domena (opcjonalnie):
1. Kup domene (np. footstats.pl na OVH ~30 PLN/rok)
2. W Cloud Run: gcloud run domain-mappings create --service footstats-api --domain footstats.pl
3. Ustaw rekordy DNS wg instrukcji GCR
4. Dodaj domene do ALLOWED_ORIGINS w .env

git add -A && git commit -m "feat: beta disclaimer + feedback + monitoring"
```

---

## FAZA 4: Maintenance — z dzisiejszej analizy (Rownolegle)

Te taski mozna robic rownolegle z fazami 0-3:

### P4.1: Version Sync
```
config.py:11 → VERSION = "v3.4-stable"
CLAUDE.md:1 → "# FootStats v3.4-stable"
```

### P4.2: SQLite Context Managers (referee_db.py, dashboard.py)
Dotyczy lokalnego SQLite — nie blokuje bety (produkcja uzywa PostgreSQL).

### P4.3: Exception Handling Audit
216x `except Exception` bez logowania. Top pliki:
- sts.py (16x), superbet.py (15x), base_playwright.py (14x)
- daily_agent.py (13x), analyzer.py (13x)

### P4.4: Cache Cleanup
682 plikow >30 dni (263MB). Stworzyc scripts/cleanup_cache.py.

### P4.5: Root Cleanup
Przeniesc 10 plikow do scripts/ i docs/.

---

## ARCHITEKTURA PRODUKCYJNA (Aktualna)

```
Uzytkownik (telefon/PC)
    |
    | HTTPS
    v
Google Cloud Run
    |-- FastAPI (uvicorn, port 8000)
    |   |-- /preview (SPA - preview.html)
    |   |-- /api/auth/login
    |   |-- /api/matches/today
    |   |-- /api/coupon/kelly
    |   |-- /api/coupon/place
    |   |-- /api/bankroll
    |   |-- /api/status
    |   |-- /api/coupons
    |   |-- /api/settings
    |   +-- /health
    |
    | PostgreSQL wire protocol
    v
Neon.tech (PostgreSQL)
    |-- users
    |-- bankroll_state (per user)
    |-- bankroll_history (per user)
    |-- coupons (per user)
    |-- predictions
    |-- ai_feedback + embeddings
    +-- wf_results
```

## MULTI-USER STATUS

| Komponent | Status |
|-----------|--------|
| JWT auth z user_id | ✅ Gotowe |
| Migracje multi-user (v2) | ✅ Gotowe |
| Izolacja kuponow per user | ✅ Gotowe |
| Izolacja bankroll per user | ✅ Gotowe (po fixie id) |
| Izolacja settings per user | ✅ Gotowe |
| Endpoint rejestracji | ❌ Do zrobienia (Faza 1) |
| Auto-seed bankroll | ❌ Do zrobienia (Faza 1) |
| Rate limiting auth | ⚠️ Globalny 60/min (Faza 1: osobny) |

## PWA — INSTALACJA NA TELEFONIE

Strona juz jest PWA-ready:
- `manifest.json` z name, icons, start_url, display:standalone
- `sw.js` z cache-first strategy
- Meta tagi apple-mobile-web-app w preview.html

Gdy uzytkownik wejdzie na strone z telefonu:
1. Chrome/Safari pokaze "Dodaj do ekranu glownego" (automatycznie lub przez przycisk)
2. Po instalacji — strona otwiera sie jak natywna apka (bez paska URL)
3. Nie trzeba zadnych licencji, App Store, Google Play
4. Aktualizacje sa automatyczne (sw.js invaliduje cache)

Brakuje: ikony 192x192 i 512x512 w /static/. Trzeba stworzyc lub podmienić.

---

## TIMELINE

| Dzien | Faza | Efekt |
|-------|------|-------|
| 1-2 | Faza 0 | Bankroll i mecze dzialaja |
| 3-5 | Faza 1 | Rejestracja, security |
| 6-10 | Faza 2 | Pelny flow: register → bankroll → mecze → kupon |
| 11+ | Faza 3 | Znajomi testuja, feedback, monitoring |
| Ciagle | Faza 4 | Maintenance z daily analysis |
