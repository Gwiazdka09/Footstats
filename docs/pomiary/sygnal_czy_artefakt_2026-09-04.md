# Sygnal czy artefakt — wynik, 2026-09-04

Pre-rejestracja: `scripts/sygnal_czy_artefakt.py` (commit a488d9183).

```
  BADANIE 1 — czy `b` przezyje kontrole nieparametryczna i placebo
============================================================================================
  wariant                           wymiar                 b        SE       z
  ------------------------------------------------------------------------------
  A1 kontrola 20 kubelkow p_otw     gospodarz       +0.01309   0.00124  +10.52
  A1 kontrola 20 kubelkow p_otw     gosc            +0.01228   0.00119  +10.32
  A2 placebo: permutacja w sezonie  gospodarz       +0.00099   0.00076   +1.31
  A2 placebo: permutacja w sezonie  gosc            +0.00090   0.00074   +1.21
  A2b placebo: permutacja w cenie   gospodarz       -0.00061   0.00124   -0.49
  A2b placebo: permutacja w cenie   gosc            +0.00155   0.00119   +1.30

  A3 SUFIT (R^2 czastkowe, bezwymiarowe)             model     wynik   udzial
  ---------------------------------------------------------------------------
    gospodarz                                      0.00158   0.00495    31.9%
    gosc                                           0.00152   0.00493    30.8%

  REGULA A (zamrozona przed przebiegiem):
    A1 przezylo kontrole nieparametryczna, A2b placebo martwe
    -> sygnal jest TRESCIA MECZOWA, nie artefaktem poziomu ceny.

============================================================================================
  BADANIE 2 — CLV. Czy kurs naszego typu na OTWARCIU jest lepszy
  niz kurs tego samego typu na ZAMKNIECIU. Ten sam bukmacher.
============================================================================================
  wariant                                    n  CLV surowe       z  CLV bez marzy       z
  ---------------------------------------------------------------------------------------
  typ modelu (argmax p_model)            70132     -0.297%  -10.15        +0.047%   +1.59
  typ rynku (argmax ceny otwarcia)       70132     -0.351%  -12.74        -0.009%   -0.33
  typ losowy                             70132     -0.325%   -9.81        +0.019%   +0.59

  REGULA B (zamrozona przed przebiegiem, na CLV SUROWYM):
    -> regula NIESPELNIONA na CLV surowym.

  CLV BEZ MARZY (dopisane po zobaczeniu, ze surowe CLV jest ujemne
  dla KAZDEGO typu — takze losowego — bo Pinnacle zaciska marze):
    model +0.047% (z=+1.59)   losowy +0.019% (z=+0.59)   roznica +0.027pp
    Ta liczba jest wielkoscia realnej przewagi cenowej modelu.
    Nie zastepuje reguly B — jest jej diagnoza.

============================================================================================
  BADANIE 3 — ile wyszloby BEZ ZADNEJ umiejetnosci
============================================================================================
  cena                               n   overround   ROI wszystkie 3
  --------------------------------------------------------------------
  PSH otwarcie Pinnacle          70132      1.0362            -4.66%
  PSCH zamkniecie Pinnacle       70132      1.0325            -4.39%
  MaxH najlepsza przedmeczowa    47835      1.0144            -2.29%
  MaxC najlepsza zamkniecie      47834      1.0047            -1.32%

  selekcja                                   n   ROI brutto       SE       z
  --------------------------------------------------------------------------
  model (argmax), cena MaxH              47835       -1.34%    0.51%   -2.65
  losowy, cena MaxH                      47835       -2.18%    0.73%   -2.97

  ROI 'wszystkie 3' to dokladnie zero umiejetnosci. Nasze ROI
  czyta sie WYLACZNIE wobec tej liczby, nie wobec zera.
```

## Test PAROWY selekcji (dopisany — badanie 3 porownywalo niesparowane)

```
n=47835, cena MaxH
model  -1.34%   losowy -2.32%   faworyt rynku -0.69%
SPAROWANE model-losowy:  +0.975pp  SE 0.943pp  z=+1.03
SPAROWANE model-faworyt: -0.652pp  SE 0.456pp  z=-1.43
zgodnosc typu modelu z faworytem rynku: 82.1%
```

Przewaga nad losowym NIE przezywa testu parowego. Punktowo prosty
„typ = faworyt rynku" wypada LEPIEJ od modelu.
