# Cena plus korekta — wynik, 2026-09-04

Pre-rejestracja: `scripts/cena_plus_korekta.py` (commit d3e5bee28).

```
  CZY MODEL POPRAWIA CENE. Dodatnie = model POMAGA.  Holdout od 2023-01-01.
====================================================================================================
  porownanie                                      logloss bazy   d logloss        SE       z  z Brier
  ------------------------------------------------------------------------------------------------
  A  otwarcie  ->  otwarcie + model                    0.99644    -0.00013   0.00007   -1.85    -1.90
  B  zamkniecie -> zamkniecie + model                  0.99285    -0.00013   0.00008   -1.61    -1.62
  C  zamkniecie -> zamkniecie + model + otwarcie       0.99285    -0.00021   0.00010   -2.06    -1.99

  p jednostronne: A 0.9677   B 0.9460   C 0.9804

  REGULA DECYZYJNA (zamrozona przed przebiegiem):
    Zadne z trzech porownan nie jest dodatnie -> cena jest
    KOMPLETNA wzgledem tego, co mamy. Kierunek 'poprawiac cene'
    zamkniety tak samo jak 'bic cene'.
    Wiecej: dolozenie modelu do ceny out-of-sample SZKODZI
    (najmocniej w C). Model wnosi do ceny wlasny blad,
    a uzyteczna czesc jest od niego o rzad wielkosci mniejsza.

  Model SAM dalej jest gorszy od ceny w kazdej lidze. Poprawka
  do ceny i konkurent ceny to dwie rozne rzeczy.
```
