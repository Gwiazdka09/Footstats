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
