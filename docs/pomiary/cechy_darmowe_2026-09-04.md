# Cechy darmowe — wynik, 2026-09-04

Pre-rejestracja: `scripts/cechy_darmowe.py` (commity 0885669d7, 86f88ac05).
Zrzut walk-forward n=120 641, 39 lig, join z cechami 100.00%.

## Przebieg pierwszy

```
  CECHY DARMOWE — czy niosa informacje, ktorej nie ma juz w prognozie
  Holdout: mecze od 2023-01-01. Dodatnie = cecha POMAGA. p po korekcie Sidaka na 5 cech w kazdym zrodle.
========================================================================================================

  ZRODLO: model   (NASZ MODEL — czy my to przeoczamy)
  cecha                      n hold   d logloss        SE       z    p_kor    d Brier  z Brier
  ----------------------------------------------------------------------------------------------------
  min_odpoczynek              44535   +0.000089  0.000038   +2.30   0.0524  +0.000070    +2.52
  glebokosc_sezonu            44535   +0.000026  0.000082   +0.32   0.9037  +0.000047    +0.97
  roznica_odpoczynku          44535   -0.000023  0.000016   -1.45   1.0000  -0.000013    -1.36
  roznica_zageszczenia        44535   -0.000019  0.000012   -1.55   1.0000  -0.000012    -1.55
  roznica_nowosci             44535   -0.000065  0.000033   -1.98   1.0000  -0.000040    -1.74

  ZRODLO: pinn   (ZAMKNIECIE PINNACLE — czy RYNEK to przeocza)
  cecha                      n hold   d logloss        SE       z    p_kor    d Brier  z Brier
  ----------------------------------------------------------------------------------------------------
  min_odpoczynek              35905   +0.000100  0.000035   +2.82   0.0119  +0.000073    +2.99
  glebokosc_sezonu            35905   -0.000002  0.000047   -0.04   0.9736  -0.000008    -0.25
  roznica_zageszczenia        35905   -0.000037  0.000023   -1.63   1.0000  -0.000023    -1.53
  roznica_nowosci             35905   -0.000027  0.000015   -1.78   1.0000  -0.000019    -1.77
  roznica_odpoczynku          35905   -0.000049  0.000020   -2.48   1.0000  -0.000030    -2.31

  REGULA DECYZYJNA (zamrozona przed przebiegiem):
    NIESIE INFORMACJE SPOZA CENY: min_odpoczynek
    -> najmocniejszy mozliwy wynik. Wymaga replikacji, NIE wdrozenia.
    Zadna cecha nie poprawia rowniez naszego modelu.

  Luka modelu do zdewigowanej ceny to -0.018..-0.052 Briera w kazdej
  z 39 lig. Zaden wynik tego skryptu tego nie odwraca.
```

## Replikacja (reguła zamrożona przed przebiegiem)

```
  REPLIKACJA — czy pierwszy wynik przezyl. Regula zamrozona w docstringu.
================================================================================================

  model/min_odpoczynek
    A. ODWROCONY PODZIAL (ucz >= 2023-01-01, oceniaj wczesniej)
       n=76106  logloss +0.000012  SE 0.000056  z +0.21
    B. ROZBICIE NA LIGI (holdout pierwotny, >=200 meczow)
       lig: 39   z roznica dodatnia: 26  (67%)
         SCO-League One             n=641    +0.000568  z +2.08
         NED-Eredivisie             n=1120   +0.000546  z +2.27
         GER-Bundesliga             n=1089   +0.000525  z +2.29
    WERDYKT: NIE PRZEZYL  (odwrocony z=+0.21, lig dodatnich 67%)
       -> szum, ktory przezyl jeden podzial. Nie raportujemy jako znaleziska.

  pinn/min_odpoczynek
    A. ODWROCONY PODZIAL (ucz >= 2023-01-01, oceniaj wczesniej)
       n=75899  logloss -0.000052  SE 0.000068  z -0.76
    B. ROZBICIE NA LIGI (holdout pierwotny, >=200 meczow)
       lig: 39   z roznica dodatnia: 26  (67%)
         AUT-Bundesliga             n=548    +0.000692  z +2.42
         NED-Eredivisie             n=926    +0.000632  z +2.85
         GRE-Super League           n=658    +0.000517  z +1.87
    WERDYKT: NIE PRZEZYL  (odwrocony z=-0.76, lig dodatnich 67%)
       -> szum, ktory przezyl jeden podzial. Nie raportujemy jako znaleziska.
```
