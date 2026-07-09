# Blueprinty — format i zasady wykonania

Blueprint = plan pisany tak, żeby **mniejszy model** (sonnet/haiku, np. `footstats-coder`) wykonał go na wysokim poziomie **bez dodatkowego kontekstu**. Orchestrator podaje coderowi JEDEN task z blueprinta na raz.

## Struktura blueprinta (sekcje obowiązkowe)

1. **KONTEKST** — 3-6 zdań: co i po co. Zero wiedzy plemiennej — wszystko co trzeba wiedzieć jest tu albo w podanych plikach.
2. **INWARIANTY** — czego NIE wolno naruszyć (np. „zero zapisu do prod Neon z testów", „nie zmieniaj zachowania backtestu offline"). Coder przerywa i raportuje, jeśli task wymusza złamanie inwariantu.
3. **ZADANIA (T1, T2, …)** — każdy task zawiera:
   - **Pliki:** dokładne ścieżki do edycji + pliki testów. Pliki spoza listy = NIE DOTYKAJ.
   - **Test-first:** jaki test napisać NAJPIERW (nazwa `test_<co>_<warunek>`, plik) i czemu ma failować (RED).
   - **Implementacja:** minimalna zmiana do GREEN, z nazwami funkcji/kluczy.
   - **Akceptacja:** obserwowalny warunek zaliczenia + komenda (`pytest tests/test_x.py -q`).
4. **DEFINITION OF DONE** — dla całego blueprinta (pełny suite green, commit per task, docs).
5. **ESKALACJA** — kiedy STOP: 3 nieudane próby na tasku, konflikt z inwariantem, odkryty bug poza zakresem (raportuj, nie naprawiaj).

## Zasady wykonania (dla codera)

- TDD: RED → GREEN → REFACTOR. Test musi failować zanim naprawisz.
- Jeden task = jeden commit `<type>: <opis PL>` (feat/fix/refactor/test/docs/chore).
- Styl: PEP8, type hints, komentarze/logi PL. Minimal diff — nie refaktoruj przy okazji.
- Test targeted przed full: `pytest tests/<plik> -q`, na koniec taska pełny `pytest tests/ -q`.
- Windows: encoding cp1250 — wzorzec `sys.stdout.reconfigure` jest akceptowany, nie walcz z nim.
- Niczego nie uruchamiaj z live pipeline (guard hook blokuje) — testy i skrypty read-only wystarczą.

## Indeks

| Blueprint | Temat | Priorytet | Źródło |
|-----------|-------|-----------|--------|
| [BP-01](BP-01-analizy-hardening.md) | Hardening zakładki „Analizy" (auth, walidacja, prod-data) | HIGH | Audyt 2026-07-07 H1,H2,M1-M4,L1,L3,L5 |
| [BP-02](BP-02-kalibracja-m1.md) | Proces kalibracji → flip M1 (monitoring, progi 20/88) | P0 | TODO P0/P1 |
| [BP-03](BP-03-decyzje-czerwcowe.md) | Otwarte HIGH-e z audytu 06-27 (wymagają decyzji usera) | HIGH-latent | Audyt 06-27 + 07-07 H3-H5,M5 |
| [BP-04](BP-04-jadro-predykcji.md) | Jądro predykcji: money/math (D1-D12) — **PO POWROCIE** (zmienia selekcję) | HIGH | Deep-dive 2026-07-09 |
