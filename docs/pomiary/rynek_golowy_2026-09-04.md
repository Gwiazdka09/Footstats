# Rynek golowy — wynik, 2026-09-04

Pre-rejestracja: `scripts/rynek_golowy.py` (commit 9f8ea2be1).
Replay walk-forward 22 lig europejskich od 2019-07, ensemble OFF (czysty model).

```
  RYNEK GOLOWY (Over/Under 2.5) kontra zamkniecie Pinnacle.  Dodatnie = MODEL lepszy od ceny.
  Te same mecze niosa kolumne 1X2 dla porownania.  p po korekcie Sidaka na 22 lig.
============================================================================================================
liga                          n  %over     T_gole       SE      z   p_kor      T_1x2   z_1x2    defG  def1X2
------------------------------------------------------------------------------------------------------------
SCO-League Two             1001  50.5%   -0.00544  0.00559  -0.97  1.0000   -0.01458   -2.41   -1.1%   -2.2%
ENG-Premier League         2458  54.9%   -0.00869  0.00347  -2.51  1.0000   -0.01596   -5.26   -1.8%   -2.5%
SCO-League One              990  54.2%   -0.01810  0.00683  -2.65  1.0000   -0.02505   -3.71   -3.6%   -3.9%
SCO-Premiership            1364  52.5%   -0.01251  0.00433  -2.89  1.0000   -0.01233   -3.59   -2.5%   -1.9%
SCO-Championship           1033  48.6%   -0.01928  0.00616  -3.13  1.0000   -0.01706   -3.36   -3.9%   -2.6%
POR-Primeira Liga          1971  48.5%   -0.01286  0.00395  -3.26  1.0000   -0.01725   -5.67   -2.6%   -2.7%
ITA-Serie A                2456  52.1%   -0.01485  0.00419  -3.54  1.0000   -0.02014   -6.97   -3.0%   -3.1%
ENG-Championship           3548  46.6%   -0.01080  0.00300  -3.60  1.0000   -0.01481   -5.98   -2.2%   -2.3%
BEL-First Division A       1859  55.5%   -0.01422  0.00393  -3.62  1.0000   -0.01515   -4.44   -2.9%   -2.3%
GER-Bundesliga             1919  60.8%   -0.01492  0.00370  -4.04  1.0000   -0.02148   -5.90   -3.1%   -3.3%
ESP-La Liga                2446  46.1%   -0.01450  0.00341  -4.25  1.0000   -0.01856   -7.08   -2.9%   -2.9%
GRE-Super League           1477  45.8%   -0.02379  0.00552  -4.31  1.0000   -0.01305   -3.36   -4.8%   -2.0%
GER-2. Bundesliga          1896  58.4%   -0.01698  0.00391  -4.34  1.0000   -0.01645   -4.50   -3.5%   -2.5%
TUR-Super Lig              2253  53.4%   -0.01635  0.00365  -4.48  1.0000   -0.02119   -6.20   -3.3%   -3.3%
NED-Eredivisie             1885  58.7%   -0.01746  0.00366  -4.78  1.0000   -0.01309   -4.11   -3.6%   -2.0%
ITA-Serie B                2320  44.2%   -0.01938  0.00364  -5.32  1.0000   -0.02391   -7.77   -3.9%   -3.6%
ENG-League Two             3323  46.7%   -0.01857  0.00318  -5.85  1.0000   -0.01905   -6.60   -3.7%   -2.9%
FRA-Ligue 1                2161  52.8%   -0.02198  0.00373  -5.88  1.0000   -0.01884   -5.92   -4.4%   -2.9%
ESP-Segunda Division       2925  40.2%   -0.01924  0.00321  -6.00  1.0000   -0.01820   -6.22   -4.0%   -2.8%
ENG-League One             3272  48.5%   -0.02032  0.00317  -6.40  1.0000   -0.02644   -8.51   -4.1%   -4.1%
ENG-National League        3226  51.9%   -0.02774  0.00432  -6.43  1.0000   -0.02466   -7.31   -5.6%   -3.8%
FRA-Ligue 2                2173  43.4%   -0.02957  0.00456  -6.48  1.0000   -0.02438   -7.09   -6.0%   -3.7%
------------------------------------------------------------------------------------------------------------

  ZBIORCZO rynek golowy   n=47956  Brier -0.01752  SE 0.00085  z=-20.67
  ZBIORCZO 1X2 (te same)  n=47956  Brier -0.01915  SE 0.00072  z=-26.54

  DEFICYT ZNORMALIZOWANY (srednia po ligach, ujemne = gorsi od ceny):
    rynek golowy -3.5% niepewnosci
    1X2          -2.9% niepewnosci
    Tylko ta para jest porownywalna miedzy rynkami — surowe Briery
    dwoch i trzech wyjsc to nie ta sama liczba.

  EV PO NAJLEPSZEJ CENIE (`_max`), plasko 1 jednostka, prog EV>0:
    zakladow 50253  trafione 24680  ROI brutto -1.46%  po 12% -13.46%  SE 0.46%  z -29.00

  REGULA DECYZYJNA (zamrozona przed przebiegiem):
    z <= -2 -> rynek golowy TEZ nas bije. Nie jest schronieniem.
    Pytanie zamkniete, bez szukania lig i progow.

  Zakres: 22 ligi europejskie. 17 lig pozaeuropejskich nie ma cen
  golowych ani u football-data, ani wstecz w API-Football (okno 7 dni).
```
