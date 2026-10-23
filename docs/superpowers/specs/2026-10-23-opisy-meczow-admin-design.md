# Opisy meczów dla właściciela (panel admina, na żądanie) — projekt (2026-10-23)

**Decyzja właściciela (23.10):** „to co do tej pory robiliśmy (liczby) + opisy meczów,
ale nie dla ludzi, tylko dla mnie” → panel admina, opis generowany na żądanie.
Nie zmienia zasady z `CLAUDE.md`: nasze typy dalej NIE pokazują się zwykłym
użytkownikom (endpoint i przycisk tylko dla `adm`).

## Podejście: karta liczb + opis LLM ograniczony do karty

1. **Karta liczb** (deterministyczna, bez LLM) — wszystko, co o meczu wiemy z własnych danych.
2. **Opis** — Groq dostaje WYŁĄCZNIE kartę i ma ją zinterpretować. Prompt zabrania
   dopisywania faktów spoza karty (kontuzje, składy, transfery, „wiadomości”) i rekomendacji
   zakładu. Bez karty nie ma opisu (żadnego „ogólnego” tekstu z wiedzy modelu).

Odrzucone: sam szablon bez LLM (sucho, ale zostaje jako zapas, gdy Groq padnie — zwracamy
samą kartę); sam LLM bez karty (halucynacje — znany problem z kursami Groqa 14.08).

## Karta liczb (`core/opis_meczu.py`)

`zbuduj_karte(home, away, liga, data, df, bzz) -> dict`:
- **Poisson bez mieszania z Bzzoiro** (`poisson.predict_match` z opcjami domyślnymi na
  zbiorze z `load_cached()` + `adapt_to_prod_schema`; λ jak w potoku — po kalibracji
  i xG; 1X2 z limitem remisu 40%): λ gospodarzy/gości, 1X2, linie Over 0.5–4.5
  (`poisson.prob_linii_goli`), BTTS. Brak wyniku → `poisson=None` + powód.
- **Bzzoiro-ML** (event z `predykcje_tygodnia`, dopasowany po nazwach jak w
  `api/routes/analyses.py`): 1X2, Over 2.5, BTTS.
- **Rynek** z kursów eventu (1X2 i O/U 2.5) po zdjęciu marży: proporcjonalnie (1/kurs
  znormalizowane). Brak kursów → `rynek=None`.
- **Forma** z `df`: ostatnie 5 meczów każdej drużyny (data, rywal, wynik, dom/wyjazd),
  średnie gole strzelone/stracone z ostatnich 10; tylko mecze sprzed daty meczu
  (opis meczu z przeszłości nie zna późniejszych wyników).
- **Statystyki drużyn** z `build_match_card` (gf_pg, ga_pg, rating, strzelcy) — gdy dostępne.
- **Uwagi stałe** wpisane do karty: definicja ramienia Poissona (jw.); „Poisson z λ
  potoku zaniża sumę goli o ~0,3/mecz (próba odkrywcza 23.10, w trakcie replikacji)”; „model nie bije rynku (39/39 lig)”.

`prompt_opisu(karta) -> str` — po polsku, 5 sekcji: siła i forma, czego spodziewa się
model, gdzie model różni się od rynku (różnice ≥ 5 pp), niepewność (mała historia,
brak Poissona, zaniżone gole), podsumowanie w 2 zdaniach. Zakazy jak wyżej.

`opisz(karta, zapytaj=zapytaj_ai) -> str | None` — `max_tokens=700`; wyjątek / `None`
z klienta → `None` (karta i tak wraca do GUI). Cache w pamięci procesu: klucz = hash
karty, TTL 6 h, max 200 wpisów (jeden użytkownik — trwały cache w bazie to YAGNI;
SQLite z `match_analysis` żyje na efemerycznym FS kontenera, więc nie używamy).

## API

`POST /api/admin/opis-meczu` (nowy plik `api/routes/admin_opisy.py`, montowany jak
`model_stats`): `Depends(require_admin)`, `@limiter.limit("10/minute")`.
Body: `{home, away, liga, data}` (to, co GUI ma na karcie z `/analyses/matches`).
Odpowiedź: `{karta, opis, z_cache}`. Zbiór historyczny ładowany leniwie raz na proces
(pierwsze żądanie wolniejsze). Błędy: 404 gdy brak meczu w Bzzoiro i brak Poissona;
nigdy `detail=str(e)` (audyt 24.09).

## GUI

`MatchAnalysisView.jsx` dostaje `isAdmin` z `App.jsx`. Na karcie meczu (tylko admin)
przycisk „Opis (admin)” → POST → panel z opisem + kluczowymi liczbami (Poisson / Bzzoiro /
rynek w jednym wierszu na rynek). Styl wg design system (glass-card, `.btn-see-all`,
ikony 16 px). Weryfikacja Playwright desktop + mobile (`footstats-gui-verifier`).

## Testy (bez sieci, bez prod DB, bez Telegrama)

- karta: Poisson z małej atrapy `df`; dopasowanie Bzzoiro; rynek po zdjęciu marży sumuje się do 1;
  forma z `df`; brak Poissona → `poisson=None` z powodem.
- prompt: zawiera liczby z karty i zakazy; NIE zawiera pól spoza karty.
- `opisz`: zapytaj zamockowany; drugi raz → z cache; wyjątek → `None`.
- endpoint: brak tokenu 401/403, zwykły user 403, admin 200 (zależności nadpisane w teście).

## Wykonanie (tryb team lead)

1. Backend (Sonnet): `core/opis_meczu.py` + endpoint + testy — gałąź `feat/opisy-meczow-admin`.
2. GUI (Haiku z gotowym kodem) + weryfikacja Playwright (gui-verifier).
3. Recenzja, CI, Sourcery, Vercel, merge, sprawdzenie na prod (jedno wywołanie jako admin).

Poza zakresem: opisy dla zwykłych użytkowników, Telegram, trwały cache w bazie.
