# Częściowe odmrożenie modelu — projekt (2026-10-22)

**Decyzja właściciela (22.10):** model rozwijamy dalej, powoli i z pomiarem — ale tylko
na czterech rodzinach rynków i bez pokazywania naszych typów ludziom. Zastępuje zapis
„MODEL ZAMROŻONY (decyzja 2026-09-10)” w `CLAUDE.md`.

Punkt wyjścia: model nie bije rynku (39/39 lig, 04.09) i ulepszenia raczej tego nie zmienią.
Cel rozwoju to **pokrycie i uczciwość prawdopodobieństw**, mierzalne na każdym kroku —
nie „wygrywanie z bukmacherem”.

## 1. Zasady

- **Zakres rynków:** 1X2, podwójna szansa (1X, X2, 12), gole Over/Under na liniach
  0.5–4.5, BTTS (tak/nie). Pozostałe rynki (handicapy, rożne, kartki, gole drużyny,
  betbuilder) zostają zamrożone.
- **Analiza ≠ kupony:** model liczy i zapisuje do `model_log` wszystko, co umie policzyć,
  we wszystkich ligach. Do selekcji kuponów liga trafia dopiero po pomiarze na danych
  na żywo (whitelist `LIGI_WHITELIST` rozszerzana liga po lidze, nie hurtem).
- **Tempo:** jedna zmiana modelu na 1–2 tygodnie, jeden PR na zmianę.
- **Reguła akceptacji zapisana PRZED pomiarem** (jak 22.09): co mierzymy, na jakim oknie,
  jaki próg. Zmiana zostaje tylko, gdy poprawia; inaczej revert.
- **Nasze typy dalej niewidoczne dla ludzi** poza kreatorem „Stwórz Kupon” (bez zmian
  w GUI wynikających z tego projektu). Zakazy z `.claude/rules/wypuszczenie-pl.md` bez zmian.
- **Naprawy błędów, pomiary i monitoring** — jak dotąd, bez ograniczeń.

## 2. Pomiar (wspólny dla wszystkich kroków)

- **Offline:** walk-forward na `data/hist_cache/full_dataset.parquet`
  (`scripts/run_walkforward_prod.py`, `scripts/porownaj_modele.py`) — Brier/NLL per rynek,
  wersja przed vs po, różnica sparowana z błędem standardowym.
- **Na żywo:** `model_log` — test obciążenia na całej próbie (`sprawdz_obciazenie`,
  jak 22.10) i pokrycie (% kandydatów policzonych przez Poissona).
- **Liczba testowanych wyjść ustalana z góry** — poprawka Šidáka rośnie razem z liczbą
  rynków (6 wyjść → |z| ≥ 2,64; więcej wyjść → wyższy próg).
- Nowe źródło predykcji (np. reprezentacje) dostaje **własny `model_source`**, żeby nie
  mieszać go z pomiarami `poisson-dc` (powód wykluczenia pucharów w `23ae6181c`).

## 3. Kolejność

### Krok 0 — naprawy (błędy, dozwolone niezależnie od odmrożenia)
1. **Podwójna szansa zaniżona o remis:** `1X` → `p_wygrana`, `X2` → `p_przegrana`
   zamiast sumy z remisem — `ai/analyzer_helpers.py:15-20` i `daily_agent.py:365-370`.
   Poprawnie: 1X = p1+pX, X2 = pX+p2, 12 = p1+p2.
2. **Over 1.5 zgadywane:** `core/match_tips.py:59` liczy `Over 2.5 + 15 pp`; prawdziwa
   wartość jest w macierzy (`core/markets.py:76-79`). Widoczne w kreatorze.
3. **Aliasy lig:** „Trendyol Super Lig”, „Liga MX Apertura”, „Stoiximan Super League”
   odrzucane mimo że liga jest na whiteliście (`core/daily_filters.py:62-69`,
   `config.py:300`). ≥17 meczów w 30 dni.

Akceptacja: testy z przypadkami z logów + po tygodniu w logach zero odrzuceń tych nazw.

### Krok 1 — zapis wszystkich rynków do pomiarów
- Podwójną szansę, Under 2.5 i „BTTS — nie” da się wyliczyć z kolumn, które już są
  w `model_log` (sumy i dopełnienia) — wystarczy dodać je do narzędzia pomiaru
  (`scripts/stan_uczenia.py`, `_WYJSCIA_OBCIAZENIA`), bez nowych kolumn.
- Nowe kolumny `model_log`: `prob_over05`, `prob_over15`, `prob_over35`, `prob_over45`
  z macierzy Poissona (`core/markets.py`); dla `bzzoiro-ml` NULL (nie podaje tych linii).
  Migracja jak dotychczas: idempotentny `ALTER TABLE … ADD COLUMN IF NOT EXISTS`
  w `core/kalibracja_log.py`.
- Akceptacja: po tygodniu ≥ 95% nowych wierszy `poisson-dc` ma niepuste nowe kolumny.

### Krok 2 — pokrycie w ligach z whitelisty
- Fakt (23.09–22.10): z ~517 kandydatów po filtrze lig Poisson policzył ~351 — około 1/3
  bez wyniku („predict_match: brak wyniku”).
- Najpierw diagnoza: próbka meczów bez wyniku, sklasyfikowana po przyczynie (nazwa
  drużyny, beniaminek, brak w zbiorze, inne). Naprawa największej przyczyny, pomiar
  pokrycia przed/po.

### Krok 3 — nowe ligi (każda pozycja dostaje własny krótki projekt przed startem)
- **3a. Reprezentacje** — 302 z 688 nazwanych odrzuceń w 30 dni (44%). Darmowe wyniki
  meczów międzynarodowych; osobny `model_source`.
- **3b. Puchary** — 189 odrzuceń. Wymaga oceny siły ligi (para drużyn z różnych lig).
- **3c. Pozostałe ligi** (Nigeria, Kolumbia, K League, ligi kobiece…) — w miarę
  znalezienia źródła danych (API-Football zawieszone).

### Krok 4 — przegląd błędów po krokach 0–3 (wymóg właściciela)
Historia projektu to ciche awarie przy zielonych testach, a kroki 0–3 dotykają potoku
w wielu miejscach naraz. Przed kalibracją pełny przegląd:
- **Ciche awarie:** każda nowa ścieżka sprawdzona na danych prod (ile wierszy naprawdę
  ma nowe wartości, ile meczów naprawdę policzono) — liczba przed/po, nie zielony test.
- **Alarmy końcowe:** dla każdej nowej ścieżki alarm w `core/alarmy_jakosci`
  (np. „nowe kolumny puste”, „pokrycie spadło”, „nowy `model_source` milczy”).
- **Dane:** audyt `footstats-data-guard` (zapis do prod z testów, lookahead,
  mieszanie `model_source`).
- **Kod:** recenzja całości zmian kroków 0–3 pod kątem połykanych wyjątków
  i fallbacków udających sukces.
- **Logi:** 7 dni `footstats-final`/`footstats-evening` bez nowych ERROR/WARNING.
Akceptacja: lista znalezisk zamknięta (naprawione albo świadomie odłożone z uzasadnieniem).

### Krok 5 — kalibracja na większej próbie
- Nowe okno pomiaru ustalane z góry po wdrożeniu kroku 1 (początek okna = dzień wdrożenia),
  ocena dopiero po przeglądzie z kroku 4. Hipoteza z 22.10: `poisson-dc` zaniża
  Over 2.5 i typ #1.

## 4. Wykonanie

Tryb team lead: zadania dla Haiku/Sonneta z dokładną specyfikacją, recenzja każdego
diffu, CI + review Sourcery przed merge'em, weryfikacja na produkcji po wdrożeniu.
Każdy krok kończy się wpisem w `docs/obserwacja_modelu.md` (pomiar przed/po).

## Poza zakresem

Pokazywanie naszych typów w GUI, płatności, nowe rynki spoza czterech rodzin.
