# Ruch linii — wynik wstepny, 2026-09-04

Pre-rejestracja: `scripts/ruch_linii.py` (commit 3feb2b1f0).

**WYNIK WSTEPNY.** Test A dodatni, ale najbardziej prawdopodobne
wyjasnienie (nieaktualnosc ceny otwarcia) NIE zostalo jeszcze wykluczone.

```
Zrzut 120641 meczow (39 lig) | 22 lig ma ceny otwarcia | dopasowane w nich: 92.2% (76114 meczow w zakresie)
Do pomiaru: 70132 meczow z obiema cenami Pinnacle, 22 lig, 2016-08-12 .. 2026-01-14

============================================================================================
  TEST A — RUCH LINII. Czy nasza niezgoda z otwarciem przewiduje,
  dokad pojedzie cena. Ten sam bukmacher w dwoch chwilach.
============================================================================================
  wymiar               n   b (sygnal)        SE       z   c (poziom)      R2
  ----------------------------------------------------------------------------------------
  gospodarz        70132     +0.01327   0.00124  +10.68     +0.00441  0.0017
  gosc             70132     +0.01174   0.00119   +9.88     +0.00555  0.0016

  REGULA DECYZYJNA (zamrozona przed przebiegiem):
    b > 0 w OBU wymiarach przy z >= 2 -> model WYPRZEDZA rynek.
    Pierwszy dodatni wynik tego projektu, wiec tym bardziej:
    holdout po dacie, pre-rejestrowany osobno, zanim cokolwiek dalej.

============================================================================================
  TEST B — deficyt wobec OTWARCIA i wobec ZAMKNIECIA, ten sam
  bukmacher, te same mecze. Dodatnie = model lepszy od ceny.
============================================================================================
  model vs otwarcie Pinnacle      Brier ceny 0.5982  roznica -0.02346  SE 0.00065  z -35.82
  model vs zamkniecie Pinnacle    Brier ceny 0.5960  roznica -0.02569  SE 0.00068  z -38.02

  Ile warte jest samo zamkniecie: otwarcie - zamkniecie +0.00224  SE 0.00020  z +11.21
  To jest rozmiar nagrody, o ktora gra TEST A.

============================================================================================
  TEST C — ROI po NAJLEPSZEJ CENIE PRZEDMECZOWEJ (MaxH/MaxD/MaxA)
============================================================================================
  meczow z cena 47835  zakladow 63181  trafione 18595
  ROI brutto -3.99%  po podatku 12% -15.99%  SE 0.70%  z -22.92
  Dla porownania po cenie ZAMKNIECIA (MaxC*, pomiar 04.09): -15.01% po podatku.
```

## Kontrole (reguła zamrożona w commicie 49781bad2)

```
  KONTROLA 1 — TERCYLE SWIEZOSCI. Czy `b` znika, gdy miedzy otwarciem
  a zamknieciem NIE doszly nowe wyniki tych druzyn.
============================================================================================
  progi odpoczynku: 5 i 7 dni
  tercyl                             n           b   z (gorszy wymiar)
  --------------------------------------------------------------------
  dolny (<= 5 dni, swieze)       24954    +0.01214               +5.18
  srodkowy (5-7 dni)             31126    +0.01391               +7.79
  gorny (> 7 dni, nic nowego)    14052    +0.00985               +3.48

============================================================================================
  KONTROLA 2 — PODZIAL PO DACIE
============================================================================================
  mecze < 2023-01-01             47896    +0.01172               +7.80
  mecze >= 2023-01-01            22236    +0.01375               +5.40

  REGULA DECYZYJNA KONTROL (zamrozona przed przebiegiem):
    |b_gorny| / |b_dolny| = 0.81   z_gorny = +3.48   polowy czasowe: +7.80 / +5.40
    -> NIEAKTUALNOSC NIE TLUMACZY efektu. To informacja, ktorej
       cena otwarcia nie ma. Dalej NIE sa to pieniadze: TEST B
       i TEST C stoja niezmienione.
```

### Sprawdzian surowszy niż pre-rejestrowany

Górny tercyl to tylko „>7 dni", więc kontrast jest słaby. Rozbicie na
drobniejsze przedziały — szukane po to, żeby własny dodatni wynik ZABIĆ:

```
przedzial                    n           b   z (gorszy)
-------------------------------------------------------
<= 3 dni                 11720    +0.01280        +3.81
4-6 dni                  23375    +0.01232        +5.00
7-9 dni                  25259    +0.01329        +6.07
10-13 dni                 3075    +0.00551        +0.31
>= 14 dni (przerwa)       6703    +0.01261        +3.04
```

Efekt plaski az do przerw reprezentacyjnych, gdzie miedzy otwarciem
a zamknieciem te druzyny NIE rozegraly ani jednego meczu. Nieaktualnosc
ceny otwarcia nie tlumaczy wiec niczego.
