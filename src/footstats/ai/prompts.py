"""Prompt templates for FootStats AI analyzer.

Extracted from analyzer.py to keep that module under 800 LOC.
All builder functions return formatted strings ready to send to LLM.
"""
from __future__ import annotations

import re

from footstats.core.rynki import rynki_dla_promptu

# Emoji i znaki ozdobne kosztuja 2-4 TOKENY przy jednym-dwoch znakach (zmierzone
# tokenizerem: "⚔️" = 4 tokeny, "🏅" = 3, "⚠️" = 4), a nie niosa nic ponad sasiadujace
# slowo. W opisach czynnikow siedza, bo te same napisy ida do konsoli i Telegrama —
# tam maja sens. Do modelu wysylamy wersje bez nich: na jednej linii czynnikow
# to ~18% tokenow, przy 5 meczach rzedu 50-150 tokenow za sama dekoracje.
# Swiadomie NIE ruszamy bloku strzalek U+2190-U+21FF: "→" kosztuje 1 token,
# a rozdziela tresc ("λg=1.8 → gospodarz dominuje"). Ciecie na oslep zabiera sens.
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF"      # piktogramy: 🏅 😫 🔄 👑 🆘 🏰
    "☀-➿"               # symbole i dingbaty: ⚔ ⚠ ✈ ✅ ❌ ★
    "⬀-⯿"               # dodatkowe strzalki/ksztalty ozdobne
    "️‍]"               # selektor wariantu + ZWJ (same w sobie tokeny)
)


def bez_emoji(tekst: str) -> str:
    """Usuwa emoji/ikony z tekstu idacego do modelu. Zostawia polskie znaki i strzalki."""
    if not tekst:
        return tekst
    return re.sub(r"[ \t]{2,}", " ", _EMOJI.sub("", tekst))


# ── System prompt for the betting analyst role ─────────────────────────────

SYSTEM_TYPER_BAZA = """Jesteś BEZWZGLĘDNYM ANALITYKIEM DANYCH BUKMACHERSKICH. Nie bądź miły — bądź precyzyjny.

KRYTERIA DECYZJI:
1. VALUE BETTING (PRIORYTET): Twoim celem jest znalezienie przewagi nad bukmacherem (Value), a nie tylko wskazanie faworyta.
   Jeśli kurs na czyste zwycięstwo (1 lub 2) jest niższy niż 1.60, zabraniam wystawiania tego typu.
   W takim przypadku przeanalizuj alternatywy o wyższym kursie (1.65 - 2.20): Over 2.5 gola lub BTTS (Obie strzelą).
2. FORMA (60% wagi): Przeanalizuj ostatnie 5 meczów każdej drużyny. Zwycięstwa vs porażki. Gole dla/przeciw. Trend wzrostowy czy spadkowy?
3. H2H (20% wagi): Historia bezpośrednich starć. Kto wygrywa, gole, pattern.
PRZED WYSTAWIENIEM TYPU:
- Podsumuj formę: "Ostatnie 5: W-W-P-W-W (trend +)"
- Podsumuj H2H: "3x Drużyna A wygrała, średnio 2.3 gola/mecz"
- Sprawdź kursy: "Faworytu <1.40 — UNIKAJ tego typu"

PEWNOŚĆ (confidence_score 0-100):
- 80-100: Silny sygnał. Forma wyraźna lub przekonujące H2H. Bądź decyzyjny!
- 65-79: Sensowny typ z racjonalnymi argumentami. Nie bój się dawać not 70-80, gdy dane wskazują faworyta!
- <65: Niska pewność, omijać.

== DEVIL'S ADVOCATE (OBOWIĄZKOWE) ==
Twoim zadaniem jest przeprowadzenie "ataku" na własną sugestię typu.
1. Wygeneruj dokładnie 3 najsilniejsze argumenty PRZECIWKO sugerowanemu typowi (np. kontuzje, xG rywala, zmęczenie).
2. Umieść je w polu przewidzianym na ryzyka przez schemat odpowiedzi, który dostałeś.
3. Dopiero PO analizie ryzyk oblicz ostateczną pewność typu.
4. Każde istotne ryzyko musi realnie obniżać pewność (np. brak kluczowego gracza = -10 pkt).

Odpowiadaj zawsze po polsku. Zawsze zwracaj JSON. Bądź konkretny.
           Over 1.5 gdy obie druzyny strzelaja regularnie, wynik klasy A vs D).
           EV przy 1.23 i P=93%: 0.93x1.23x0.88-1 = +0.7% – ledwo na plusie, wiec pewnosc musi byc pewna.
1.35-1.80: DOPUSZCZALNE TYLKO w AKO jako noga — NIGDY jako standalone single.
           Przy stawce 5-10 PLN zysk netto z singla 1.67 to tylko ~2-3 PLN – nieoplacalne.
           W AKO mnozy kurs laczny — wtedy ma sens.
> 1.80  : standard dla singla i AKO, liczymy EV_netto normalnie.
ZASADA SINGLA: single (1 noga) dozwolony tylko gdy kurs >= 1.80 LUB stawka >= 50 PLN.

== BUDOWANIE KUPONU AKO ==
Cel: wlasciwy kurs laczny, nie liczba zdarzen. Optymalna liczba: 4-6 zdarzen.
Struktura "kotwica + wartosc": 1-2 tanich pewnych zdarzen (1.20-1.40, pewnosc >=90%)
  + 3-4 wartosciowych zdarzen (1.50-2.00, EV_netto > 3%).
Max 2 mecze tej samej ligi w kuponie (korelacja dnia/pogody/sedziow).
Nie lacze typow z tego samego meczu (np. "1" i "Over" z PSG – oba ida w gore lub dol razem).
Kazde zdarzenie musi miec wlasne uzasadnienie – nie "dolaczone dla kursu".
Nie wkladaj meczow z ROTACJA, ZMECZENIE obu druzyn, ani ROZBIÉZNOSC.

== STAWKI (stale stawki, flat betting) ==
Kupon A (kurs ~11-14):  10 PLN – bardziej pewny, nizsza stawka na ryzyko
Kupon B (kurs ~20-30):   5 PLN – wyzsze ryzyko = nizsza stawka
Single value bet:       10-15 PLN gdy EV_netto > 5% i brak czynnikow ostrzegawczych
Eksperymentalny (>30):   2-3 PLN
Zasada: nie zmieniaj stawki po wygranej ani po stracie. Emocje to najgorszy doradca.

== DOBOR TYPOW ==
Over 2.5: mocny sygnal gdy lambda_g + lambda_a > 2.8 (Poisson). Sprawdz BTTS jako potwierdzenie.
Over 1.5: kotwica gdy obie druzyny strzelajace, pewnosc >=95%. Bezpieczne "dokladanie" do AKO.
Under 2.5: lambda_g + lambda_a < 2.0, obie defensywne, brak HIGH_STAKES (bo desperacja = gole).
BTTS: oba ataki w formie, zadna druzyna nie ma COMFORT/VACATION (bo te druzyny nie ryzykuja).
1/X/2: EV_netto > 3%, brak ROTACJA/ZMECZENIE, Poisson i ML zgodne.
1X / X2: bezpieczniejsze ale niskie kursy – tylko gdy EV_netto > 0 po podatku.

== PRZYKLADY ==
KOTWICA: 1=91% kurs=1.28 EV=+2.5% klasa A vs D → OK
VALUE: TWIERDZA 1=82% kurs=1.48 EV=+6.8% → BIERZ
NIE: kurs<1.20 NIGDY | ROZBIEŻNOŚĆ>15% POMIŃ | ROTACJA POMIŃ
RAG: PATENT+TWIERDZA→1: 7/8=87% → mocny dowód

== ZAKAZY BEZWZGLEDNE (nauczone na stratach 04.04.2026) ==
1. Max 6 nog w AKO – bez wyjatkow. Wiecej nog = iluzja pewnosci, nie wieksza szansa.
2. Grupy spadkowe i relegacyjne: Over 2.5 ZABRONIONE.
   Druzyny walczace o przezycie graja defensywnie i chaotycznie. Lambda z sezonu ich nie opisuje.
3. Duplikacja selekcji miedzy kuponami: max 1 wspolna selekacja.
   Jezeli ta sama noga pada, tracisz podwojnie. To nie dywersyfikacja – to multiplikacja bledu.
4. "Kupon 19 pewniaczkow": NIE BUDUJ. Kazda noga ponizej 1.20 to NIGDY. 19 nog to 19 szans na blad.

== POLITYKA "OVER 2.5" I KONTUZJI (PEŁNA ANALIZA) ==
- SCEPTYCYZM WOBEC OVER 2.5: Wymagaj dowodow na SIŁĘ ATAKU OBU drużyn. Jeśli brakuje informacji lub jedna z drużyn ma słaby atak, ODRZUC Over 2.5. Słaba obrona to nie jest wystarczający powód na Over.
- KONTUZJE ATAKU: Jeśli topowy strzelec (lub pomocnik ofensywny) nie gra z powodu zawieszenia lub kontuzji — ZAKAZ Over 2.5.
- NIEKOMPLETNE DANE: Jeśli widzisz ryzyko lub rotację (np. mecze Pucharowe), załóż niższy pułap bramek i odrzuć Over. Typuj Under lub bezpieczne zakłady z wyższym kursem i mniejszym ryzykiem utraty (1X/X2). W skrócie: jak są kontuzje/rotacja w obu drużynach = omijaj z daleka.
"""

# Schemat POJEDYNCZEGO typu. Wydzielony 31.08, bo `SYSTEM_TYPER` narzucał go
# WSZYSTKIM czterem wywołaniom typera, a tylko część tego chce. Zmierzone:
# `ai_analiza_pewniaczki` parsuje `top3`/`kupon_a`, dostawała `{"typ": ...}`
# i wpadała w fallback — kupony `phase='final'` zniknęły po 15.08.
#
# Dlaczego dopiero po podmianie modelu: `llama-3.1-8b-instant` słabo trzymała
# się promptu systemowego i szła za promptem użytkownika. `gpt-oss-120b` trzyma
# się systemowego, więc konflikt, który był tam od początku, stał się widoczny.
# Enum typow GENEROWANY z `TYP_DO_ODDS_KEY`, nie przepisany. Do 01.09 wyliczal
# 22 rynki, z ktorych wyceniamy 6 — byly tam m.in. "Handicap +1", "Kartki
# Over 3.5" i "Rozne Over 9.5". Model brał je za dozwolone, a weryfikacja
# kasowala noge jako halucynacje ("brak realnego kursu w Bzzoiro"). Zmierzone
# 01.09: `Usunieto 4 halucynowanych nog` i pusty kupon mimo poprawnych typow.
# BTTS NIE swiadomie poza lista, dopoki BTTS_TWO_WAY jest wylaczone.
_TYPY_ENUM = " | ".join(f'"{_r}"' for _r in rynki_dla_promptu())

SCHEMAT_POJEDYNCZY_TYP = f"""JSON SCHEMA (OBOWIĄZKOWY - Zwróć wyłącznie JSON):
{{
  "typ": {_TYPY_ENUM},
  "kurs": 1.80,
  "pewnosc_pct": 75,
  "risks_analysis": ["ryzyko 1", "ryzyko 2", "ryzyko 3"],
  "uzasadnienie": "Krótko: dlaczego ten typ mimo ryzyk?",
  "value_bet": true | false
}}
"""

# Zgodność wstecz: domyślny prompt typera to baza + schemat pojedynczego typu,
# czyli dokładnie to, co było do 31.08. Wołający, który parsuje inny kształt,
# przekazuje `schemat=None`.
SYSTEM_TYPER = SYSTEM_TYPER_BAZA + chr(10) + chr(10) + SCHEMAT_POJEDYNCZY_TYP



# ── Prompt builders (f-string templates with runtime variables) ─────────────

def build_mecz_prompt(
    gospodarz: str,
    goscie: str,
    p_wygrana: float,
    p_remis: float,
    p_przegrana: float,
    btts: float,
    over25: float,
    pewnosc_modelu: float,
    forma_g: str,
    forma_a: str,
    h2h_opis: str,
    rag_context: str,
    value_info: str,
    komentarz_footstats: str | None,
) -> str:
    return f"""Analizujesz mecz piłkarski i musisz podać typ bukmacherski.

═══════════════════════════════════════
MECZ: {gospodarz} vs {goscie}
═══════════════════════════════════════

ANALIZA STATYSTYCZNA (FootStats – model Poissona + ML):
  Gospodarz wygrywa: {p_wygrana:.1f}%
  Remis:             {p_remis:.1f}%
  Goście wygrywają:  {p_przegrana:.1f}%
  BTTS (obie strzelą): {btts:.1f}%
  Over 2.5 gola:       {over25:.1f}%
  Pewność modelu:      {pewnosc_modelu}%

FORMA:
  {gospodarz}: {forma_g}
  {goscie}:    {forma_a}

HISTORIA BEZPOŚREDNIA (H2H):
  {h2h_opis}
{rag_context}
{value_info}
KOMENTARZ FOOTSTATS:
  {komentarz_footstats or 'brak'}
═══════════════════════════════════════

ZADANIE – Wykonaj analizę "Devil's Advocate" podając 3 ryzyka, a następnie wybierz JEDEN najlepszy typ spośród:
  1, X, 2, 1X, X2, BTTS, Over, Under

Odpowiedź TYLKO w formacie JSON (bez żadnego tekstu przed ani po):
{{
  "typ": "1",
  "pewnosc": 74,
  "risks_analysis": ["ryzyko 1", "ryzyko 2", "ryzyko 3"],
  "uzasadnienie": "Krótkie 2-3 zdania po polsku wyjaśniające wybór.",
  "value_bet": false,
  "value_bet_opis": "Opis value bet jeśli istnieje, inaczej pusta string.",
  "alternatywny_typ": "Over",
  "ostrzezenia": "Ewentualne ryzyka lub pusta string."
}}"""


def build_pewniaczki_prompt(
    n_mecze: int,
    sygnaly: str,
    kalibracja_str: str,
    feedback_str: str,
    mecze_opisy_text: str,
    cel_kuponow_text: str,
) -> str:
    # UWAGA PRZY EDYCJI: kazdy token tutaj zabiera miejsce OPISOM MECZOW, ktore
    # niosa informacje. Szkielet mial 2077 tokenow z 4300 budzetu (48%), wiec
    # prompt byl przycinany na slepo w KAZDYM przebiegu. Struktura kuponu byla
    # powielona 4x, a regula "wysoka pewnosc + wysoki kurs" powtorzona 3x.
    # `tests/test_prompt_budzet.py` pilnuje i rozmiaru, i kompletu zakazow.
    #
    # Prog pewnosci nogi jest POKRETLEM (`KUPON_MIN_PEWNOSC_PCT`), nie stala:
    # to decyzja o strategii zakladow, a te zmienia sie bez zmiany kodu.
    # Import lokalny, zeby podmiana zmiennej srodowiskowej dzialala po
    # przeladowaniu configu, bez przeladowywania tego modulu.
    from footstats.config import BTTS_TWO_WAY, KUPON_MIN_PEWNOSC_PCT

    # Lista z tego samego slownika, co bramka weryfikacji — przepisana
    # rozjechalaby sie z nia przy pierwszej zmianie mapy.
    _RYNKI = ", ".join(rynki_dla_promptu(BTTS_TWO_WAY))

    # Liczba zadanych kuponow jest POCHODNA liczby meczow. `Fill all four`
    # kazalo wypisywac cztery niezaleznie od tego, ilu mamy kandydatow —
    # a `Each slip = a DIFFERENT match` czynilo czwarty niemozliwym.
    # Placilismy tokenami WYJSCIA za pola nie do wypelnienia i 01.09
    # odpowiedz urwala sie w polowie (`wyjscie sciete do 2640`), przez co
    # kupon `final` znowu nie powstal mimo poprawnych typow w `top3`.

    return f"""ROLE: ultra-skeptical betting analyst. You look NOT for a winner, but for reasons a pick will LOSE.

DATA: {n_mecze} matches within 72h. [metoda:POISSON] = full factor analysis; [metoda:ML] = Bzzoiro only, no history.

CONTEXT:
{bez_emoji(sygnaly)}
{bez_emoji(kalibracja_str)[:600]}{bez_emoji(feedback_str)[:400]}
TAX 12%: net = stake * total_odds * 0.88. EV in the data is BEFORE tax.

CONFIDENCE (cold calculation, not optimism):
- 75-100%: only with overwhelming evidence (win streak, no injuries, H2H dominance). 50-74%: normal bet. <50%: avoid.
- Confidence >=75% with odds >2.00 is a contradiction -> cut it hard unless the data is overwhelming.
- Cannot list 3 arguments AGAINST -> lower confidence by 15-25 points.

RISK: every pick MUST carry a "ryzyko" field with the 3 strongest arguments AGAINST it. Missing = under-analysis.

COUPONS:
{bez_emoji(cel_kuponow_text)}

MATCHES:
{bez_emoji(mecze_opisy_text)}

TASK: reply with JSON ONLY (no text before/after). Keep the keys exactly as shown.
{{
  "top3": [{{"mecz": "X vs Y", "typ": "1", "kurs": 1.48, "pewnosc_pct": 72, "ev_netto": 6.8, "uzasadnienie": "1 zdanie", "ryzyko": ["r1","r2","r3"]}}],
  "kupon_a": {{
    "zdarzenia": [{{"nr": 1, "mecz": "A vs B", "typ": "1", "kurs": 1.55, "pewnosc_pct": 70, "ryzyko": ["r1","r2","r3"]}}],
    "kurs_laczny": 1.55, "szansa_wygranej_pct": 70.0, "wygrana_netto": 4.84, "ryzyko_ogolne": "..."
  }},
  "kupon_b": {{...}}, "kupon_c": {{...}}, "kupon_d": {{...}},
  "ostrzezenia": "2-3 zdania"
}}
kupon_b/c/d: same structure as kupon_a, different match and market - b: 1X2, c: Over/Under, d: BTTS. Fill {min(n_mecze, 4)} of them (one per match); omit the rest entirely.
LANGUAGE: JSON keys and "typ" values exactly as above (ASCII). All free text in POLISH.

ABSOLUTE BANS:
- One kupon (kupon_a..d) = EXACTLY 1 leg (single). No accumulators (AKO). Each kupon = a DIFFERENT match; fill as many as there are qualifying matches and leave the rest empty.
- Leg odds < 1.20: NEVER. Every leg: pewnosc_pct >= {KUPON_MIN_PEWNOSC_PCT}%.
- Markets: ONLY {_RYNKI}. Any other market is discarded before settlement.
- BetBuilder (Over+BTTS from one match): FORBIDDEN."""
# Zakaz "grupy spadkowe + Over 2.5" NIE stoi juz tutaj: ma wlasny punkt
# w `SYSTEM_TYPER_BAZA` ("2. Grupy spadkowe i relegacyjne: Over 2.5 ZABRONIONE"),
# ktory idzie przy KAZDYM wywolaniu. Druga kopia tej samej reguly to dokladnie
# mechanizm, ktory 01.09 dal cztery rozjezdzajace sie wersje zasad o singlu.


def build_kupon_prompt(stawka: float, picks_text: str, ml_kontekst: str) -> str:
    return f"""Oceń poniższy kupon bukmacherski jako doświadczony analityk.

KUPON DO OCENY (stawka: {stawka:.2f} PLN):
{picks_text}

PODATEK: 12% zryczałtowany. Wzór netto: {stawka} × kurs_łączny × 0.88
{ml_kontekst}

OCENA (odpowiedz po polsku):

0. WALIDACJA ZASAD (sprawdź PRZED oceną – każde naruszenie to BLOKADA):
   - Liczba nóg: czy <= 6? Jeśli więcej – ODRZUĆ, napisz które usunąć.
   - Kursy < 1.20: czy są? Jeśli tak – ODRZUĆ te nogi (zasada NIGDY).
   - BetBuilder (kombinacje z jednego meczu): czy jest? Jeśli tak – ODRZUĆ, brak modułu korelacji.
   - Grupy spadkowe / relegacyjne + Over 2.5: czy jest? Jeśli tak – ODRZUĆ (mecze defensywne).
   - Duplikacja selekcji: zaznacz jeśli ta sama noga była już na innym kuponie tego dnia.
   Podsumuj: "Zasady OK" lub wymień każde naruszenie z nazwą meczu.

1. KAŻDE ZDARZENIE (tylko te które przeszły walidację):
   - Typ i kurs
   - Ocena kursu vs prawdopodobieństwo ML (jeśli dostępne): EV+/EV-/brak danych
   - Ryzyko: NISKIE / ŚREDNIE / WYSOKIE

2. PODSUMOWANIE KUPONU:
   - Łączny kurs (oblicz)
   - Oczekiwana wygrana netto po podatku 12%
   - Ogólna ocena kuponu: ✅ WARTOŚCIOWY / ⚡ PRZECIĘTNY / ❌ RYZYKOWNY

3. REKOMENDACJA:
   - Co zmienić jeśli kupon jest słaby
   - Czy stawiać? (krótko 1 zdanie)"""


def build_scout_prompt(legs_text: str, kontekst: str) -> str:
    kontekst_blok = f"KONTEKST:\n{kontekst}" if kontekst else ""
    return f"""Oceń poniższy kupon jako LLM Scout (filtr jakości 0-100).

NOGI KUPONU:
{legs_text}
{kontekst_blok}

ZADANIE:
1. Dla każdej nogi: zaznacz ryzyko (NISKIE/ŚREDNIE/WYSOKIE) i główne zastrzeżenia.
2. Wykryj: kontuzje kluczowych zawodników, derby/finały (motywacja), mecze bez stawki (team rotation), korelację nóg.
3. Podaj końcową ocenę 0-100 gdzie:
   - 0-49: VETO (nie stawiać)
   - 50-69: SŁABY (rozważyć)
   - 70-84: DOBRY
   - 85-100: BARDZO DOBRY

Zakończ odpowiedź DOKŁADNIE w tym formacie (ostatnia linia):
SCORE: <liczba 0-100>"""
