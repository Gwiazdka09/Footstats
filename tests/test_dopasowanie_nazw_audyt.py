"""test_dopasowanie_nazw_audyt.py — dopasowanie nazw drużyn tylko przez `team_similarity`.

PO CO: błąd "rezerwy uznane za pierwszy zespół" siedział w CZTERECH niezależnych
miejscach i przeżył dwie poprawki, bo każde liczyło podobieństwo nazw po swojemu:

  * coupon_settlement  — surowy SequenceMatcher przy progu 0.70;
  * flashscore_results — surowy SequenceMatcher przy progu 0.85;
  * daily_phases       — podciąg (`gh in fh or fh in gh`);
  * api_football + daily_agent — podciąg, ten sam zapis.

Pierwszy audyt szukał `SequenceMatcher`/`difflib` i przez to NIE ZOBACZYŁ trzech
ostatnich — dopasowanie po podciągu wygląda inaczej, choć jest tym samym błędem.

Ten plik pilnuje obu zapisów naraz. Nie chodzi o styl: każde ręczne porównanie
nazw omija `_ZNACZNIKI_REZERW`, `_ROZROZNIAJACE` i puste nazwy, czyli wszystkie
zabezpieczenia, które siedzą w jednym miejscu właśnie po to, żeby działały
wszędzie.

Dopisujesz nowe dopasowanie nazw? Użyj `team_similarity` z progiem
`PROG_DOPASOWANIA_MECZU`. Jeśli naprawdę potrzebujesz czegoś innego — dopisz
plik do allowlisty RAZEM z uzasadnieniem.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "footstats"

# Funkcje, których wynik JEST znormalizowaną nazwą drużyny.
_NORMALIZATORY = {"normalize_team_name", "_norm", "_norm_ascii"}

# `normalize.py` implementuje `team_similarity`, więc z definicji liczy
# podobieństwo samodzielnie — to jedyne miejsce, w którym wolno.
_ALLOWLIST_SIMILARITY = {"utils/normalize.py"}

# Puste. Każdy wpis to zgoda na ręczne porównanie nazw z podaniem powodu.
_ALLOWLIST_PODCIAG: dict[str, str] = {}


def _pliki() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _wzgledna(p: Path) -> str:
    return p.relative_to(SRC).as_posix()


class _SzukaczPodciagow(ast.NodeVisitor):
    """Znajduje `a in b` / `a not in b`, gdzie OBA to znormalizowane nazwy drużyn.

    Zmienne śledzone są per moduł — nazwy typu `fh`, `ng`, `n_home` powstają
    z `normalize_team_name(...)` i tylko takie pary nas interesują. Dzięki temu
    zwykłe `if x in slownik` czy `if "vs" in tekst` nie generują szumu.
    """

    def __init__(self) -> None:
        self.znormalizowane: set[str] = set()
        self.trafienia: list[int] = []

    @staticmethod
    def _jest_normalizacja(wezel: ast.AST) -> bool:
        if not isinstance(wezel, ast.Call):
            return False
        fn = wezel.func
        nazwa = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
        if nazwa in _NORMALIZATORY:
            return True
        # `_s(normalize_team_name(...))` i podobne opakowania
        return any(_SzukaczPodciagow._jest_normalizacja(a) for a in wezel.args)

    def visit_Assign(self, node: ast.Assign) -> None:
        cele, wartosci = node.targets[0], node.value
        # `a, b = _norm(x), _norm(y)`
        if isinstance(cele, ast.Tuple) and isinstance(wartosci, ast.Tuple):
            for cel, wart in zip(cele.elts, wartosci.elts):
                if isinstance(cel, ast.Name) and self._jest_normalizacja(wart):
                    self.znormalizowane.add(cel.id)
        elif isinstance(cele, ast.Name) and self._jest_normalizacja(wartosci):
            self.znormalizowane.add(cele.id)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for op, prawy in zip(node.ops, node.comparators):
            if not isinstance(op, (ast.In, ast.NotIn)):
                continue
            lewy = node.left
            if (isinstance(lewy, ast.Name) and isinstance(prawy, ast.Name)
                    and lewy.id in self.znormalizowane
                    and prawy.id in self.znormalizowane):
                self.trafienia.append(node.lineno)
        self.generic_visit(node)


@pytest.mark.parametrize("plik", _pliki(), ids=_wzgledna)
def test_brak_dopasowania_nazw_po_podciagu(plik: Path):
    """`"legia" in "legia ii"` jest prawdą — i tak właśnie rezerwy udawały klub."""
    wzgledna = _wzgledna(plik)
    if wzgledna in _ALLOWLIST_PODCIAG:
        pytest.skip(_ALLOWLIST_PODCIAG[wzgledna])

    szukacz = _SzukaczPodciagow()
    szukacz.visit(ast.parse(plik.read_text(encoding="utf-8")))

    assert not szukacz.trafienia, (
        f"{wzgledna}: porównanie znormalizowanych nazw drużyn przez podciąg "
        f"(linie {szukacz.trafienia}). Użyj team_similarity z progiem "
        f"PROG_DOPASOWANIA_MECZU — podciąg przepuszcza rezerwy jako pierwszy zespół."
    )


@pytest.mark.parametrize("plik", _pliki(), ids=_wzgledna)
def test_similarity_liczone_w_jednym_miejscu(plik: Path):
    """Surowy SequenceMatcher omija znaczniki rezerw i człony odróżniające."""
    wzgledna = _wzgledna(plik)
    if wzgledna in _ALLOWLIST_SIMILARITY:
        pytest.skip("normalize.py implementuje team_similarity")

    drzewo = ast.parse(plik.read_text(encoding="utf-8"))
    uzycia = [
        w.lineno for w in ast.walk(drzewo)
        if isinstance(w, ast.Call)
        and (getattr(w.func, "id", "") == "SequenceMatcher"
             or getattr(w.func, "attr", "") == "SequenceMatcher")
    ]

    assert not uzycia, (
        f"{wzgledna}: surowy SequenceMatcher na nazwach (linie {uzycia}). "
        f"Użyj team_similarity — dawał 0.81 parze Manchester United / City "
        f"przy progu rozliczeń 0.6."
    )


# Funkcje liczące podobieństwo nazw drużyn.
_SIMILARITY = {"team_similarity", "_similar", "_similarity", "_dopasowanie"}


def _srednie_podobienstw(drzewo: ast.AST) -> list[int]:
    """Znajduje `(sim(a,b) + sim(c,d)) / 2` — uśrednianie dwóch podobieństw.

    Średnia pozwala jednemu idealnemu trafieniu przepchnąć złe dopasowanie
    drugiej strony: 1.00 + 0.58 daje 0.79, czyli powyżej progu 0.6, mimo że
    druga drużyna go nie przeszła. Tak "Legia – Lech Poznań" rozliczało się
    wynikiem meczu "Legia – Lechia Gdańsk".

    Wykrywa też wariant PRZEZ ZMIENNE:

        s_h = team_similarity(...)
        s_a = team_similarity(...)
        total = (s_h + s_a) / 2          # <- tak umknął `flashscore_results`

    Pierwsza wersja tego strażnika patrzyła tylko na wywołania wprost w wyrażeniu
    i dlatego przegapiła szóste miejsce tego samego błędu.

    Poprawnie: `min(...)` — obie strony muszą przejść próg.
    """
    z_podobienstwa: set[str] = set()

    for w in ast.walk(drzewo):
        if isinstance(w, ast.Assign) and isinstance(w.value, ast.Call):
            fn = w.value.func
            nazwa = getattr(fn, "id", "") or getattr(fn, "attr", "")
            if nazwa in _SIMILARITY:
                for cel in w.targets:
                    if isinstance(cel, ast.Name):
                        z_podobienstwa.add(cel.id)

    def _jest_sim(w: ast.AST) -> bool:
        if isinstance(w, ast.Call):
            return (getattr(w.func, "id", "") in _SIMILARITY
                    or getattr(w.func, "attr", "") in _SIMILARITY)
        return isinstance(w, ast.Name) and w.id in z_podobienstwa

    trafienia = []
    for w in ast.walk(drzewo):
        if not (isinstance(w, ast.BinOp) and isinstance(w.op, ast.Div)):
            continue
        lewy = w.left
        if (isinstance(lewy, ast.BinOp) and isinstance(lewy.op, ast.Add)
                and _jest_sim(lewy.left) and _jest_sim(lewy.right)):
            trafienia.append(w.lineno)
    return trafienia


@pytest.mark.parametrize("plik", _pliki(), ids=_wzgledna)
def test_brak_usredniania_podobienstw(plik: Path):
    """Średnia z pary maskuje złe dopasowanie jednej ze stron."""
    trafienia = _srednie_podobienstw(ast.parse(plik.read_text(encoding="utf-8")))

    assert not trafienia, (
        f"{_wzgledna(plik)}: uśrednianie dwóch podobieństw (linie {trafienia}). "
        f"Użyj min(...) — obie drużyny muszą przejść próg, inaczej jedno idealne "
        f"trafienie przepycha dopasowanie do meczu z inną drużyną."
    )


def test_strażnik_wykrywa_usrednianie():
    """Audyt, który nic nie wykrywa, to zielone światło bez pokrycia."""
    kod = ("def f(h, a, fh, fa):\n"
           "    return (team_similarity(h, fh) + team_similarity(a, fa)) / 2\n")

    assert _srednie_podobienstw(ast.parse(kod)) == [2]


def test_strażnik_nie_zglasza_min():
    kod = ("def f(h, a, fh, fa):\n"
           "    return min(team_similarity(h, fh), team_similarity(a, fa))\n")

    assert _srednie_podobienstw(ast.parse(kod)) == []


def test_strażnik_nie_zglasza_zwyklego_dzielenia():
    kod = "def f(x, y):\n    return (x + y) / 2\n"

    assert _srednie_podobienstw(ast.parse(kod)) == []


def test_strażnik_wykrywa_usrednianie_przez_zmienne():
    """Tak umknął `flashscore_results` pierwszej wersji tego strażnika."""
    kod = ("def f(h, a, fh, fa):\n"
           "    s_h = team_similarity(fh, h)\n"
           "    s_a = team_similarity(fa, a)\n"
           "    return (s_h + s_a) / 2\n")

    assert _srednie_podobienstw(ast.parse(kod)) == [4]


def test_strażnik_nie_myli_zmiennych_niepodobienstwowych():
    """Zmienne o podobnych nazwach, ale z innego źródła, to nie ten wzorzec."""
    kod = ("def f(a, b):\n"
           "    s_h = len(a)\n"
           "    s_a = len(b)\n"
           "    return (s_h + s_a) / 2\n")

    assert _srednie_podobienstw(ast.parse(kod)) == []


def test_strażnik_wykrywa_wzorzec():
    """Audyt, który nic nie wykrywa, to zielone światło bez pokrycia."""
    kod = (
        "from footstats.utils.normalize import normalize_team_name\n"
        "def f(a, b, idx):\n"
        "    ng = normalize_team_name(a)\n"
        "    ig = normalize_team_name(b)\n"
        "    return ng in ig\n"
    )
    szukacz = _SzukaczPodciagow()
    szukacz.visit(ast.parse(kod))

    assert szukacz.trafienia == [5]


def test_strażnik_nie_zglasza_zwyklego_in():
    """Bez fałszywych alarmów na `x in slownik` czy `"vs" in tekst`."""
    kod = (
        "from footstats.utils.normalize import normalize_team_name\n"
        "def f(a, idx, tekst):\n"
        "    ng = normalize_team_name(a)\n"
        "    if ng in idx:\n"
        "        return True\n"
        "    return 'vs' in tekst\n"
    )
    szukacz = _SzukaczPodciagow()
    szukacz.visit(ast.parse(kod))

    assert szukacz.trafienia == []
