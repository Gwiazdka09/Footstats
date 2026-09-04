# Warstwa strzalow — REPLIKACJA, 2026-09-04

Pre-rejestracja: `scripts/warstwa_strzalow_ab.py` (commit c07583dbe).

```
  WARSTWA STRZALOW CELNYCH. Dodatnie = strzaly POMAGAJA.
  Grupa B to REPLIKACJA na ligach, ktorych pierwszy pomiar nie widzial.
=================================================================================================

  GRUPA A — ODNIESIENIE — 8 lig zmierzonych 03.09
  liga                          n  ruszone  Brier bez  Brier ze   roznica       SE      z   p_kor
  ---------------------------------------------------------------------------------------------
  POL-Ekstraklasa             493      489     0.6422    0.6340  +0.00826  0.00332  +2.49  0.0504
  USA-MLS                     868      863     0.6254    0.6177  +0.00768  0.00350  +2.19  0.1076
  NOR-Eliteserien             380      374     0.5642    0.5546  +0.00964  0.00484  +1.99  0.1714
  IRL-Premier Division        321      321     0.6253    0.6229  +0.00240  0.00460  +0.52  0.9429
  DNK-Superliga               314      309     0.6148    0.6130  +0.00182  0.00529  +0.34  0.9737
  SWZ-Super League            379      379     0.6291    0.6288  +0.00032  0.00441  +0.07  0.9939
  AUT-Bundesliga              316      315     0.6296    0.6311  -0.00149  0.00410  -0.36  0.9997
  MEX-Liga MX                 559      559     0.5889    0.5902  -0.00134  0.00316  -0.42  0.9998
  ZBIORCZO grupa A: n=3630  Brier +0.00403  SE 0.00145  z=+2.78   95%: +0.00119 .. +0.00688

  GRUPA B — REPLIKACJA — 6 lig dobackfillowanych 04.09
  liga                          n  ruszone  Brier bez  Brier ze   roznica       SE      z   p_kor
  ---------------------------------------------------------------------------------------------
  ROU-Superliga               516      503     0.6264    0.6203  +0.00608  0.00364  +1.67  0.2534
  SWE-Allsvenskan             388      380     0.6126    0.6057  +0.00690  0.00485  +1.42  0.3839
  RUS-Premier League          348      342     0.5711    0.5672  +0.00395  0.00524  +0.75  0.7843
  BRA-Serie A                 618      607     0.6031    0.6039  -0.00082  0.00315  -0.26  0.9961
  ARG-Liga Profesional        865      853     0.6410    0.6420  -0.00102  0.00304  -0.34  0.9975
  JPN-J1 League               424      412     0.6159    0.6193  -0.00340  0.00388  -0.88  1.0000
  ZBIORCZO grupa B: n=3159  Brier +0.00138  SE 0.00154  z=+0.89   95%: -0.00165 .. +0.00441

  Pierwotny wynik grupy A (cytowany, nie przeliczany): +0.00430 (SE 0.00147, z=2.93, n=3568) — pomiar z 2026-09-03

  REGULA DECYZYJNA (zamrozona przed przebiegiem):
    |z|=0.89 < 2 -> NIE replikuje. Pierwotne z=2.93
    zostaje wynikiem JEDNEJ proby i tak ma byc cytowane.
    Bez zlewania grup i bez szukania podzbiorow grupy B.

  POGLADOWO, 14 lig razem: n=6789  Brier +0.00280  z=+2.64
  Ta liczba NIE rozstrzyga niczego — zawiera probe, na ktorej
  efekt zostal znaleziony.
```
