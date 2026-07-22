# ROAST Council — Log

## 2026-07-20 — FootStats jako czysta predykcja
- **WERDYKT:** FIX FIRST
- **Ryzyko:** Jedyny żywy edge (absencje) jest NIETESTOWANY i prawdopodobnie już w kursie — cel „skalibrowany predyktor" realizuje darmowy devig rynku lepiej (log-loss 0.6692 < 0.6840).
- **Test 10-min:** Blend na istniejącym OOS: log-loss logit-mieszanki(model, devig-rynku) z optymalną wagą α vs sam devig; zalicza gdy α_model ≥ 0.15 ORAZ mieszanka bije rynek o ≥ 0.002 log-loss.
- **Jeśli FIX FIRST:** Zmierzony forward CLV na sygnale absencji — mediana CLV ≥ +2% (po vigu, po 12% podatku) na ≥500 osiedlonych zakładów → przełącza na BUILD.

## 2026-07-22 — FootStats jako dziennik kuponów (re-roast po pivocie)
- **WERDYKT:** FIX FIRST
- **Ryzyko:** Zbudowane ≠ używane — 87 dni publiczny `/auth/register` → 0 zewnętrznych kont, a jedyny wyróżnik (podgląd modelu) jest zmierzony gorszy od darmowego devigu (0.6840 > 0.6692) i działa tylko dla naszych lig → produkt sprzedaje friction bez edge.
- **Test 10-min:** Wyślij osobisty link do 10 realnych typerów; PASS = ≥5/10 wpisze ≥2 kupony w ≥2 różne dni w 7 dni; <3/10 = KILL. Zero nowego kodu przed tym testem.
- **Jeśli FIX FIRST:** ≥5 zewnętrznych userów z ≥2 wpisami w odstępie ≥24h w 14 dni (przy włączonej instrumentacji retencji) → BUILD. Podgląd modelu skreślony jako wyróżnik (gorszy od darmowego), nie inwestować.
