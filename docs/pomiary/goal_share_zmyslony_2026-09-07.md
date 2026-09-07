# `goal_share` był zmyślony dla 62% drużyn, 2026-09-07

Nie pomiar hipotezy, tylko naprawa błędu produkcyjnego znaleziona przy audycie.

## Obietnica, której kod nie dotrzymywał

Docstring `core/absencje.py` opisuje ochronę jako już działającą:

> Premier League po dwóch kolejkach dała 5 goli na dwie kadry, więc udział
> jednego strzelca wyszedłby 0,4 i model policzyłby jego absencję jako utratę
> 40% ataku. `team_goal_shares_recent` sięga po poprzedni pełny sezon i takiego
> skoku nie ma.

`team_goal_shares_recent` sięgała po pierwszy **niepusty** sezon, nie pełny:

```python
for s in range(season, season - lookback - 1, -1):
    shares = team_goal_shares(team, s, db_path=db_path)
    if shares:          # <- jeden wiersz wystarczy
        return shares
```

`team_goal_shares` dzieli gole przez sumę graczy **zapisanych**, więc przy jednym
wpisie ten jeden dostaje **100% ataku drużyny**.

## Dlaczego to strzelało codziennie

Produkcja pyta o sezon bieżący (`daily_phases:44`, `analyses.py:70`). Skład
sezonu bieżącego w bazie pochodzi z `/players/topscorers` API-Football, a ten
endpoint oddaje **20 nazwisk na całą ligę** — czyli 1-4 na drużynę.

Strzelcy na drużynę w `data/player_stats.json`:

```
sezon  druzyn  min  p25  mediana  p75  max
 2024     212    1    1        2   13   29    zrodlo mieszane
 2025      95    9   13       15   17   30    pelne sklady (Understat)
 2026      53    1    1        1    2    4    /players/topscorers
```

Luka **4 ↔ 9** jest pusta. `MIN_SKLAD = 8` przepuszcza 95 sezonów-drużyn z 95
prawdziwych i zatrzymuje 53 z 53 śmieciowych. Wyżej zaczyna kosztować: próg 12
gubi 12 prawdziwych, próg 16 gubi 58 — za zero dodatkowej ochrony.

## Rozmiar szkody

Na 662 drużynach z `model_log` za ostatnie 14 dni:

```
PRZED:  105 druzyn dostawalo udzialy
        z tego 65 (62%) ZMYSLONYCH — jeden gracz, udzial 100%
PO:      57 druzyn dostaje udzialy (prawdziwe)
         17 zmyslonych odzyskuje pelne 2025
         48 schodzi na plaska korekte
```

Co robił zmyślony udział 100% (przy λ 1.5, cap redukcji 0.35):

```
udzial 100% (zmyslony):  lambda 1.5 -> 0.975   P(Over) 0.499 -> 0.371   edge -0.1295
udzial   4% (prawdziwy): lambda 1.5 -> 1.470   P(Over) 0.499 -> 0.499   edge -0.0011
```

Absencja jednego zawodnika fabrykowała **12.8 pp przewagi nad rynkiem** na Under.
Kanał team-news ożył wczoraj (07.09) — czyli błąd trafiłby na produkcję razem
z pierwszymi realnymi absencjami.

## Czego NIE zrobiłem

**Nie wlałem sezonu 2026 z API-Football.** Sprawdzone: dane są (`+20 graczy`
na ligę), ale to ten sam `topscorers`, więc dolałyby dokładnie tego śmiecia.

**Understat, który dawał pełne składy, jest martwy.** `GET
https://understat.com/league/EPL/2026` oddaje HTTP 200 i **4684 bajty** — stronę
bez `playersData`. Fallback na Playwright też nic nie znajduje. To samo na 2025,
więc źródło padło po tym, jak zebrano obecne dane. Czwarty martwy scraper po
SofaScore (403), worldfootball (403) i Transfermarkt.

Zostaje więc 2025 jako jedyne pełne źródło i próg, który do niego cofa.

## Straż

* `tests/test_goal_share_cienki_sezon.py` — 6 przypadków, w tym dowód, że bez
  progu udział wychodzi 1.0, oraz ścieżka przez zrzut (kontener nie ma bazy,
  więc poprawka działająca tylko na SQLite byłaby cichym no-opem).
* `test_zrzut_produkcyjny_istnieje_i_ma_biezacy_sezon` liczy teraz drużyny
  **przechodzące próg**, nie same sezony. Stara wersja przechodziła na zielono
  przez cały czas trwania błędu.
* `scripts/eksport_player_stats.py` raportuje kompletność per sezon przy każdym
  zrzucie — bez tego plik wygląda tak samo bogato niezależnie od źródła.
