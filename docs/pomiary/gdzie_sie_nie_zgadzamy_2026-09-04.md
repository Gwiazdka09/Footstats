# Gdzie sie nie zgadzamy — wynik, 2026-09-04

Pre-rejestracja: `scripts/gdzie_sie_nie_zgadzamy.py` (commit 998a09be7).

```
n=111804  39 lig  |  zgoda 79.9%  niezgoda 20.1%

================================================================================================
  ZGODA I NIEZGODA Z FAWORYTEM RYNKU (zamkniecie Pinnacle)
================================================================================================
  podzbior             n  traf. model  traf. rynek  Brier model  Brier cena   d Brier       z
  --------------------------------------------------------------------------------------------
  zgoda            89281       52.61%       52.61%       0.6050      0.5851  -0.01993  -37.93
  niezgoda         22523       29.09%       42.33%       0.7023      0.6463  -0.05603  -30.91

  TEST ROZSTRZYGAJACY — McNemar w podzbiorze NIEZGODY
    model trafil 6551   rynek trafil 9533   ani jeden 6439   z=-23.51

  REGULA DECYZYJNA (zamrozona przed przebiegiem):
    Rynek trafia CZESCIEJ przy z <= -2 -> nasze odejscia od ceny sa
    systematycznie bledne. Samodzielny wklad modelu jest UJEMNY,
    a nie zerowy.

================================================================================================
  CHARAKTERYSTYKA NIEZGODY (opisowo, bez testow)
================================================================================================
  model wybral         n   udzial  traf. model  traf. rynek  sr. p_cena
  ----------------------------------------------------------------------
  gospodarz         9652    42.9%       29.79%       41.56%       30.3%
  remis             1095     4.9%       30.87%       44.02%       30.3%
  gosc             11776    52.3%       28.35%       42.80%       28.8%

  sila niezgody (decyl)          n  p_mod-p_cena  traf. model  traf. rynek
  ------------------------------------------------------------------------
  1. -0.030..+0.051           2253        +0.035       34.31%       36.26%
  2. +0.051..+0.072           2252        +0.063       33.30%       37.70%
  3. +0.072..+0.090           2252        +0.081       31.79%       37.92%
  4. +0.090..+0.106           2252        +0.098       30.42%       40.36%
  5. +0.106..+0.124           2252        +0.115       28.24%       42.63%
  6. +0.124..+0.144           2253        +0.133       27.21%       44.47%
  7. +0.144..+0.167           2252        +0.155       28.95%       43.07%
  8. +0.167..+0.197           2252        +0.181       26.55%       46.14%
  9. +0.197..+0.250           2252        +0.220       25.84%       46.80%
  10. +0.250..+0.773          2253        +0.333       24.23%       47.89%

  Decyle sa po to, zeby zobaczyc KSZTALT. Zaden prog nie zostanie
  z tej tabeli wybrany — to bylby dokladnie mechanizm 52 podzbiorow.
```
