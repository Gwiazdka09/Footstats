# BP-02 — Proces kalibracji → flip dźwigni M1

## KONTEKST
Cel M1 = 55% win rate. Root-cause'y Cel B usunięte (fix 06-19 `pred` w quick_picks + 07-06 `GROQ_TIP_OVERRIDE` ON — model wybiera, LLM tylko analiza). Teraz faza **PASYWNA**: zbieramy świeże settled (pipeline PC-off: cloud draft 07:30 + settle 06:00/21:30) i czekamy na progi decyzyjne. Dźwignie zbudowane flag-OFF czekają na flip: `SELECTION_MIN_CONF=65` (offline: pasmo 65%+ conf = 68% acc) i `LEAGUE_GATING=1` (odcina POL/ESP/FRA <50%). **INWARIANT NADRZĘDNY: żadnych nowych zmian λ/modelu aż progi osiągnięte** — zmiana teraz zaciemnia czy fixy działają.

To blueprint **procesu powtarzalnego** (agent `footstats-calibration-reporter` + decyzje usera), nie kodowania.

## INWARIANTY
- Neon: READ-ONLY. Żadnych flipów flag bez decyzji usera. Żadnych zmian λ w fazie pasywnej.
- Trend ogłaszamy od ~15 nowych settled (małe n = szum).
- Każdy raport porównuj z poprzednim (STATUS.md / git log) — liczy się Δ, nie snapshot.

## PROCES (cykl co 2-3 dni — agent `footstats-calibration-reporter`)

### Krok 1 — Monitor
`python scripts/calibration_monitor.py` (Neon read-only). Zbierz: licznik fresh settled (≥06-19), accuracy System vs Pipeline, per-liga, output flip-advisora (`core/flip_advisor.py`).

### Krok 2 — Interpretacja progów
| Próg | Akcja |
|------|-------|
| n<20 | Raport licznika, nic więcej. Jeśli n NIE rośnie między raportami → **ALARM** → odpal `footstats-ops-monitor` (pipeline padł?). |
| n≥20 | **D3**: pełna decyzja a/b/c — próg guardu `GROQ_TIP_OVERRIDE_THRESHOLD` (33/45), czy argmax na stałe. Przygotuj tabelę: acc z guardem vs bez, per próg. Decyzja = user. |
| n≥88 | **D2**: auto-refit kalibracji (delta +30 od n_train); gdy krzywa zdrowa (rozpiętość OK w `probability_calibrator.maybe_refit_calibration`) → rekomenduj `CALIBRATION_ENABLED=1`. Dodatkowo: flip-advisor → rekomendacja flip `SELECTION_MIN_CONF=65` i `LEAGUE_GATING=1`. Decyzja = user. |

### Krok 3 — Raport (format stały)
```
Licznik: n=X fresh (Δ+Y od ostatniego) | progi: 20 (D3) / 88 (D2+flip)
Accuracy: live X% vs offline 51.8% vs M1 55% — trend ↑/↓/flat
Per liga (flip-advisor): [top3] / [bottom3 → kandydaci LIGI_SLABE]
Reweight 30/70 (ENSEMBLE_MARKET_WEIGHT=0.70): log-loss check OK/regres
Rekomendacja: CZEKAĆ (brakuje Z settled) / D3-READY / FLIP-READY / ALARM
```

## PO DECYZJI USERA (taski dla codera — TDD)

### T1 — Flip `SELECTION_MIN_CONF=65` (gdy user zatwierdzi)
- **Pliki:** `.env` na prod (Cloud Run env — user/deploy, NIE coder) + `tests/` walidacja progu.
- **Test-first:** `test_selekcja_prog_65_odrzuca_ponizej` w teście `system_paper` — mecz conf=60 odpada, conf=70 wchodzi.
- **Akceptacja:** paper System + cloud-draft respektują próg; monitor pokazuje mniejszy wolumen, wyższe acc pasma.

### T2 — Flip `LEAGUE_GATING=1` (gdy user zatwierdzi)
- **Pliki:** env prod + `core/daily_filters.py` — zweryfikuj listę `LIGI_SLABE` vs aktualny flip-advisor (może się zmienić od offline'owej!).
- **Test-first:** `test_gating_odrzuca_lige_slaba` — POL odpada przy fladze ON, NED przechodzi.
- **Akceptacja:** `_pre_filtruj_ligi` aktywny; brak predykcji z lig gated w następnym cyklu.

### T3 — `CALIBRATION_ENABLED=1` (dopiero po D2 + zdrowa krzywa)
- Gate w `probability_calibrator.py:145` już istnieje; flip = env. Test regresji: kalibracja identity gdy plik `calibration.json` stary/pusty (już jest — zweryfikuj `pytest tests/test_probability_calibrator.py -q`).

## DEFINITION OF DONE
M1 osiągnięte = live ≥55% na ≥50 settled po flipach. Wtedy → M2 (tuning). Każdy flip udokumentowany w TODO.md + STATUS.md (scribe).

## ESKALACJA
Accuracy się załamuje (<40% na n≥15) po którymkolwiek flipie → natychmiast rekomenduj rollback env (escape-hatch: każda flaga odwracalna) + raport do usera. Nie kombinuj z λ.
