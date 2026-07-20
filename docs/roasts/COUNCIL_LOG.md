# ROAST Council — Log

## 2026-07-20 — FootStats jako czysta predykcja
- **WERDYKT:** FIX FIRST
- **Ryzyko:** Jedyny żywy edge (absencje) jest NIETESTOWANY i prawdopodobnie już w kursie — cel „skalibrowany predyktor" realizuje darmowy devig rynku lepiej (log-loss 0.6692 < 0.6840).
- **Test 10-min:** Blend na istniejącym OOS: log-loss logit-mieszanki(model, devig-rynku) z optymalną wagą α vs sam devig; zalicza gdy α_model ≥ 0.15 ORAZ mieszanka bije rynek o ≥ 0.002 log-loss.
- **Jeśli FIX FIRST:** Zmierzony forward CLV na sygnale absencji — mediana CLV ≥ +2% (po vigu, po 12% podatku) na ≥500 osiedlonych zakładów → przełącza na BUILD.
