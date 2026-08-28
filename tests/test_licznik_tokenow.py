"""I2 — licznik tokenów przestaje zgadywać ze stałej znak/token.

STAN ZASTANY: `szacuj_tokeny` dzieliło długość tekstu przez stałą 1.4. Stała
wzięła się z realnego pomiaru po awarii 09.08 (413 na prompcie z opisami meczów),
ale drugi pomiar na samym szkielecie promptu dał 2.86 — i OBA były prawdziwe.

Zmierzone 28.08 tokenizerem modelu (`openai/gpt-oss-120b`, encoding o200k):

    szkielet PL       64 znaków ->  25 tokenów  (2.56 zn/tok)  heurystyka: 46
    diakrytyki        67 znaków ->  31 tokenów  (2.16 zn/tok)  heurystyka: 48
    emoji + liczby    53 znaków ->  36 tokenów  (1.47 zn/tok)  heurystyka: 38

Emoji potrafi zająć 3-4 tokeny na jednym znaku, zwykły polski tekst prawie trzy
znaki na token. ŻADNA stała nie obsłuży obu: przy 1.4 szkielet jest przeszacowany
o 84% i prompt bywa przycinany bez potrzeby, a przy 3.0 emoji przepuszcza 413.

RYZYKO OPERACYJNE, KTÓRE TE TESTY PILNUJĄ: `tiktoken` pobiera plik BPE z sieci
przy pierwszym użyciu (zmierzone: 3,8 s dla `o200k_harmony`). W jobie na Cloud Run
to jest zapytanie do internetu w środku przebiegu. Licznik tokenów NIE MOŻE z tego
powodu wywrócić potoku ani zwolnić go o kilka sekund na każde wywołanie.
"""
from __future__ import annotations

import builtins

import pytest

from footstats.ai import client

SZKIELET = "Przeanalizuj mecze i zwroc JSON z polami top3, kupon_a, kupon_b."
EMOJI = "🏅⚔️😫🔄 1.48 EV=+6.8% pewnosc=72% kurs=2.05 lambda=1.83"


@pytest.fixture(autouse=True)
def _czysty_enkoder():
    """Enkoder jest cache'owany w module — bez zerowania testy zależą od kolejności."""
    client.zeruj_enkoder()
    yield
    client.zeruj_enkoder()


def _tiktoken_albo_skip():
    try:
        import tiktoken  # noqa: F401
    except ImportError:
        pytest.skip("tiktoken niedostepny w tym srodowisku")


# ── sedno: koniec przeszacowania ────────────────────────────────────────────

def test_zwykly_tekst_nie_jest_juz_przeszacowany(_czysty_enkoder=None):
    """Powód całego zadania: przy stałej 1.4 ten szkielet „ważył" 46 tokenów
    zamiast 25, więc prompt bywał przycinany, choć mieścił się w budżecie."""
    _tiktoken_albo_skip()
    heurystyka = int(len(SZKIELET) / 1.4) + 1
    assert client.szacuj_tokeny(SZKIELET) < heurystyka


def test_emoji_nie_jest_zanizone():
    """Pomyłka w TĘ stronę to 413 i padnięty przebieg — tu margines bezpieczeństwa
    musi trzymać, mimo że emoji ma najgorszy stosunek znak/token."""
    _tiktoken_albo_skip()
    import tiktoken

    faktyczne = len(tiktoken.get_encoding(client.ENCODING_TOKENIZERA).encode(EMOJI))
    assert client.szacuj_tokeny(EMOJI) >= faktyczne


def test_wynik_rosnie_z_dlugoscia_tekstu():
    assert client.szacuj_tokeny(SZKIELET * 4) > client.szacuj_tokeny(SZKIELET)


def test_pusty_tekst_nie_wywala():
    assert client.szacuj_tokeny("") >= 0


# ── odporność: licznik nie ma prawa wywrócić przebiegu ──────────────────────

def test_brak_tiktoken_spada_na_heurystyke_i_mowi_o_tym(monkeypatch, caplog):
    """Obraz produkcyjny może nie mieć paczki. Cichy fallback wyglądałby
    identycznie jak działający tokenizer — i wróciłoby przeszacowanie,
    którego nikt by nie zauważył."""
    prawdziwy_import = builtins.__import__

    def _bez_tiktoken(nazwa, *a, **k):
        if nazwa == "tiktoken":
            raise ImportError("brak paczki")
        return prawdziwy_import(nazwa, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _bez_tiktoken)
    with caplog.at_level("WARNING"):
        wynik = client.szacuj_tokeny(SZKIELET)

    assert wynik == int(len(SZKIELET) / client._ZNAKOW_NA_TOKEN) + 1
    assert "tiktoken" in caplog.text.lower()


def test_awaria_pobierania_encodingu_nie_rzuca(monkeypatch, caplog):
    """`tiktoken` ciągnie plik BPE z sieci. W jobie brak wyjścia na świat
    albo timeout nie może zamienić się w wyjątek w środku przebiegu."""
    import tiktoken

    def _wybuch(*_a, **_k):
        raise RuntimeError("nie udalo sie pobrac pliku BPE")

    monkeypatch.setattr(tiktoken, "get_encoding", _wybuch)
    with caplog.at_level("WARNING"):
        assert client.szacuj_tokeny(SZKIELET) > 0


def test_enkoder_ladowany_TYLKO_RAZ(monkeypatch):
    """Zmierzone: pierwsze `get_encoding` trwa ~3,8 s. Ładowanie przy każdym
    wywołaniu dodałoby te sekundy do KAŻDEGO zapytania do LLM-a w przebiegu."""
    _tiktoken_albo_skip()
    import tiktoken

    wolania = []
    prawdziwe = tiktoken.get_encoding

    def _licz(nazwa):
        wolania.append(nazwa)
        return prawdziwe(nazwa)

    monkeypatch.setattr(tiktoken, "get_encoding", _licz)
    for _ in range(5):
        client.szacuj_tokeny(SZKIELET)

    assert len(wolania) == 1, f"enkoder ladowany {len(wolania)} razy zamiast raz"


def test_nieudane_ladowanie_nie_jest_ponawiane_co_wywolanie(monkeypatch):
    """Kontrola do testu wyżej dla ścieżki AWARYJNEJ: po nieudanej próbie
    kolejne wywołania nie mogą znowu bić w sieć — inaczej każdy prompt
    w przebiegu czeka na ten sam timeout."""
    import tiktoken

    proby = []

    def _wybuch(nazwa):
        proby.append(nazwa)
        raise RuntimeError("brak sieci")

    monkeypatch.setattr(tiktoken, "get_encoding", _wybuch)
    for _ in range(5):
        client.szacuj_tokeny(SZKIELET)

    assert len(proby) == 1, f"probowano {len(proby)} razy mimo trwalej awarii"


# ── regres na 413 ───────────────────────────────────────────────────────────

def test_przyciety_prompt_dalej_miesci_sie_w_budzecie():
    """Cały mechanizm istnieje po to, żeby prompt zmieścił się w limicie modelu.
    Dokładniejszy licznik nie może tego rozszczelnić."""
    dlugi = (SZKIELET + " " + EMOJI + " ") * 200
    budzet = 300
    przyciety = client.dopasuj_do_budzetu(dlugi, budzet)
    assert client.szacuj_tokeny(przyciety) <= budzet


def test_krotki_prompt_przechodzi_nietkniety():
    assert client.dopasuj_do_budzetu(SZKIELET, 10_000) == SZKIELET


def test_przycinanie_nie_marnuje_budzetu():
    """DRUGA POŁOWA I2. Sam licznik może być dokładny, a `dopasuj_do_budzetu`
    i tak wyrzuci za dużo, jeśli przelicza budżet tokenów na znaki po starej
    stałej 1.4 — dla zwykłego polskiego tekstu to 2,5× mniej znaków, niż się
    mieści. Skutkiem nie jest 413, tylko ciche gubienie opisów meczów.

    Wymagamy, żeby przycięty prompt REALNIE wykorzystywał przyznany budżet,
    a nie kończył na jego ułamku."""
    _tiktoken_albo_skip()
    dlugi = (SZKIELET + " ") * 400
    budzet = 500
    przyciety = client.dopasuj_do_budzetu(dlugi, budzet)
    uzyte = client.szacuj_tokeny(przyciety)

    assert uzyte <= budzet, "przekroczony budzet — to jest 413"
    assert uzyte >= budzet * 0.8, (
        f"wykorzystano tylko {uzyte}/{budzet} tokenow — prompt przyciety za mocno"
    )


def test_zachowany_poczatek_i_koniec_promptu():
    """Instrukcja stoi na początku, format odpowiedzi na końcu — wycinamy środek."""
    prompt = "POCZATEK-INSTRUKCJI " + ("srodek " * 500) + " KONIEC-FORMATU"
    przyciety = client.dopasuj_do_budzetu(prompt, 100)
    assert przyciety.startswith("POCZATEK")
    assert przyciety.endswith("KONIEC-FORMATU")
