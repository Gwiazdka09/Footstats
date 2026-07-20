---
description: ROAST — rada 4 agentów ocenia pomysł FootStats (Wierzący→Sceptyk→Inwestor→Sędzia). Podaj pomysł jako argument.
---

Odpal **radę roast** na pomyśle: **$ARGUMENTS**

(Jeśli brak argumentu — zapytaj użytkownika jaki pomysł/feature/kierunek roastujemy, zanim ruszysz.)

Kolejność jest sednem — Sędzia rządzi ostatni, po usłyszeniu trzech. Odpal subagentów **po kolei**, każdemu podając pomysł + wszystkie wcześniejsze werdykty:

1. **footstats-believer** — dostaje: pomysł. Zwraca: case ZA + jeden zakład na którym stoi.
2. **footstats-skeptic** — dostaje: pomysł + case Wierzącego. Zwraca: ataki + fatal flaw.
3. **footstats-investor** — dostaje: pomysł + Wierzący + Sceptyk. Zwraca: analizę wartości/edge + własny werdykt tak/nie.
4. **footstats-judge** — dostaje: pomysł + wszystkie trzy głosy. Zwraca: WERDYKT (BUILD/FIX FIRST/KILL) + ryzyko + test 10-min, i **dopisuje wpis do `docs/roasts/COUNCIL_LOG.md`**.

Na koniec pokaż użytkownikowi zwięzłe podsumowanie: 1 linia od każdego głosu + werdykt Sędziego w tabeli.
