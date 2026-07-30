"""inwentarz_funkcji.py — generuje FUNCTIONS.md: spis wszystkich funkcji projektu.

Dla kazdej funkcji: nazwa, krotki opis, pokrycie testami (%), status uzycia.

Po co: latwo dorobic funkcje i zapomniec ja podpiac. Tak powstaly m.in. martwe
importy `ai_analyzer`/`scraper_kursy` w cli.py (opcje I/J nie dzialaly miesiacami,
bo `except ImportError: pass` cicho je gasil). Inwentarz pokazuje takie rzeczy
od reki, ale TYLKO gdy jest swiezy — dlatego generator, nie plik pisany recznie.

Uzycie:
    python -m coverage json -o coverage.json     # albo uzyj istniejacego .coverage
    python scripts/inwentarz_funkcji.py
    python scripts/inwentarz_funkcji.py --cov coverage.json --out FUNCTIONS.md

Wynik (FUNCTIONS.md) jest w .gitignore — to migawka lokalnego stanu, nie zrodlo prawdy.

OGRANICZENIA — czytaj, zanim uznasz cos za martwe:
  * Wykrywanie uzycia jest po NAZWIE (AST: Name/Attribute + literaly stringow).
    Nazwa uzywana przez wiecej niz jedna definicje dostaje znacznik "?" —
    licznik jest wtedy niewiarygodny.
  * Wywolania dynamiczne (getattr, rejestry, dispatch po stringu) czesciowo
    lapiemy przez literaly, ale nie w 100%.
  * Funkcje wolane przez framework (endpointy FastAPI, __main__, dundery)
    sa oznaczane jako WEJSCIE na podstawie dekoratorow/nazwy, nie licznika.
  * Pliki z `omit` w .coveragerc nie maja danych pokrycia -> "n/d".
Status MARTWA to KANDYDAT do usuniecia, nie wyrok. Sprawdz recznie.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src" / "footstats"

# Warstwa architektury -> (etykieta, kolejnosc). Dopasowanie po prefiksie sciezki.
_WARSTWY: list[tuple[str, str]] = [
    ("core/", "Silnik modelu i logika zakładów"),
    ("scrapers/", "Pozyskiwanie danych"),
    ("ai/", "Warstwa LLM / RAG"),
    ("api/", "API i endpointy"),
    ("db/", "Baza danych"),
    ("operator/", "Operator i smoke-testy"),
    ("export/", "Eksport (PDF/tabele)"),
    ("utils/", "Narzędzia wspólne"),
    ("data/", "Ładowanie danych historycznych"),
]
_WARSTWA_ROOT = "Pipeline i punkty wejścia"

# Dekoratory oznaczajace funkcje wolana przez framework, nie przez nasz kod.
_DEKORATORY_WEJSCIA = re.compile(
    r"\b(get|post|put|patch|delete|head|options|route|websocket|"
    r"on_event|middleware|exception_handler|fixture|task|command|hookimpl|"
    # Pydantic wola walidatory sam, po zarejestrowaniu dekoratorem — nigdy po nazwie.
    # Bez tego cale RegisterRequest.*_valid ladowalo w MARTWA (falszywy alarm).
    r"validator|field_validator|model_validator|root_validator|"
    r"field_serializer|model_serializer|computed_field|"
    r"property|staticmethod|classmethod|cached_property|lru_cache)\b"
)

# Metody wolane przez framework po konwencji nazwy, nie przez nasz kod.
# `dispatch` — BaseHTTPMiddleware (Starlette). Reszta to protokoly Pythona.
_METODY_WEJSCIA = {"dispatch", "setUp", "tearDown"}


def _warstwa(rel: str) -> str:
    rel = rel.replace("\\", "/")
    for prefiks, etykieta in _WARSTWY:
        if rel.startswith(prefiks):
            return etykieta
    return _WARSTWA_ROOT


def _opis(wezel) -> str:
    """Pierwsze zdanie docstringa, przyciete. Brak docstringa to tez informacja."""
    doc = ast.get_docstring(wezel)
    if not doc:
        return "—"
    linia = next((ln.strip() for ln in doc.splitlines() if ln.strip()), "")
    linia = re.sub(r"\s+", " ", linia)
    # utnij na pierwszej kropce konczacej zdanie
    kropka = re.search(r"\.(\s|$)", linia)
    if kropka and kropka.start() > 15:
        linia = linia[: kropka.start()]
    return (linia[:72] + "…") if len(linia) > 73 else linia or "—"


def _zbierz_funkcje() -> list[dict]:
    """AST: wszystkie funkcje i metody w src/footstats."""
    out: list[dict] = []
    for plik in sorted(_SRC.rglob("*.py")):
        rel = str(plik.relative_to(_SRC)).replace("\\", "/")
        drzewo = ast.parse(plik.read_text(encoding="utf-8"))

        def _dodaj(wezel, klasa: str | None) -> None:
            dekoratory = [ast.unparse(d) for d in wezel.decorator_list]
            out.append({
                "nazwa": wezel.name,
                "klasa": klasa,
                "plik": rel,
                "od": wezel.lineno,
                "do": getattr(wezel, "end_lineno", wezel.lineno),
                "opis": _opis(wezel),
                "dekoratory": dekoratory,
                "warstwa": _warstwa(rel),
                "prywatna": wezel.name.startswith("_") and not wezel.name.startswith("__"),
                "dunder": wezel.name.startswith("__") and wezel.name.endswith("__"),
            })

        for wezel in drzewo.body:
            if isinstance(wezel, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _dodaj(wezel, None)
            elif isinstance(wezel, ast.ClassDef):
                for skladnik in wezel.body:
                    if isinstance(skladnik, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        _dodaj(skladnik, wezel.name)
    return out


def _zbierz_uzycia() -> tuple[Counter, Counter, Counter]:
    """Licznik referencji po nazwie w src / tests / scripts.

    Liczymy `ast.Name`, `ast.Attribute` oraz literaly stringow (czesciowo lapie
    dispatch dynamiczny). Definicje NIE licza sie jako uzycie.
    """
    liczniki = {"src": Counter(), "tests": Counter(), "scripts": Counter()}
    katalogi = {
        "src": _ROOT / "src",
        "tests": _ROOT / "tests",
        "scripts": _ROOT / "scripts",
    }
    for gdzie, katalog in katalogi.items():
        if not katalog.exists():
            continue
        for plik in katalog.rglob("*.py"):
            if ".egg-info" in str(plik):
                continue
            try:
                drzewo = ast.parse(plik.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for wezel in ast.walk(drzewo):
                if isinstance(wezel, ast.Name):
                    liczniki[gdzie][wezel.id] += 1
                elif isinstance(wezel, ast.Attribute):
                    liczniki[gdzie][wezel.attr] += 1
                elif isinstance(wezel, (ast.Import, ast.ImportFrom)):
                    # `from x import foo` to REFERENCJA do foo — w AST nazwa siedzi
                    # w alias.name, a nie w wezle Name, wiec bez tego przypadku
                    # funkcje wolane tylko po imporcie wygladaly na martwe.
                    for alias in wezel.names:
                        liczniki[gdzie][alias.name.split(".")[-1]] += 1
                        if alias.asname:
                            liczniki[gdzie][alias.asname] += 1
                elif isinstance(wezel, ast.Constant) and isinstance(wezel.value, str):
                    tekst = wezel.value.strip()
                    if tekst.isidentifier():
                        liczniki[gdzie][tekst] += 1
    return liczniki["src"], liczniki["tests"], liczniki["scripts"]


def _wczytaj_pokrycie(sciezka: Path) -> dict[str, tuple[set[int], set[int]]]:
    """plik -> (linie wykonane, linie pominiete). Klucz znormalizowany do src-rel."""
    if not sciezka.exists():
        return {}
    dane = json.loads(sciezka.read_text(encoding="utf-8"))
    wynik: dict[str, tuple[set[int], set[int]]] = {}
    for nazwa, info in dane.get("files", {}).items():
        znorm = nazwa.replace("\\", "/")
        idx = znorm.find("src/footstats/")
        if idx == -1:
            continue
        rel = znorm[idx + len("src/footstats/"):]
        wynik[rel] = (set(info.get("executed_lines", [])),
                      set(info.get("missing_lines", [])))
    return wynik


def _procent(fn: dict, pokrycie: dict) -> tuple[str, float | None]:
    dane = pokrycie.get(fn["plik"])
    if dane is None:
        return "n/d", None
    wykonane, pominiete = dane
    zakres = set(range(fn["od"], fn["do"] + 1))
    mierzone = (wykonane | pominiete) & zakres
    if not mierzone:
        return "n/d", None
    trafione = wykonane & zakres
    pct = 100.0 * len(trafione) / len(mierzone)
    return f"{pct:.0f}%", pct


def _status(fn: dict, w_src: int, w_tests: int, w_scripts: int, dwuznaczna: bool) -> str:
    if fn["dunder"]:
        return "WEJŚCIE"          # wolane niejawnie przez interpreter
    if any(_DEKORATORY_WEJSCIA.search(d) for d in fn["dekoratory"]):
        return "WEJŚCIE"          # endpoint / walidator / hook frameworka
    if fn["nazwa"] in _METODY_WEJSCIA or fn["nazwa"] in {"main", "run", "cli"}:
        return "WEJŚCIE"
    if w_src > 0:
        return "PROD?" if dwuznaczna else "PROD"
    if w_tests > 0 or w_scripts > 0:
        return "TYLKO-TEST?" if dwuznaczna else "TYLKO-TEST"
    return "MARTWA?" if dwuznaczna else "MARTWA"


_KOLEJNOSC = {"MARTWA": 0, "MARTWA?": 1, "TYLKO-TEST": 2, "TYLKO-TEST?": 3,
              "PROD": 5, "PROD?": 5, "WEJŚCIE": 6}


def generuj(cov_path: Path, out_path: Path) -> dict:
    funkcje = _zbierz_funkcje()
    u_src, u_tests, u_scripts = _zbierz_uzycia()
    pokrycie = _wczytaj_pokrycie(cov_path)

    # nazwa zdefiniowana wielokrotnie -> licznik referencji niewiarygodny
    ile_definicji = Counter(f["nazwa"] for f in funkcje)

    for fn in funkcje:
        n = fn["nazwa"]
        # NIE odejmujemy definicji: `def foo` trzyma nazwe w polu tekstowym
        # FunctionDef.name, ktore nie jest wezlem Name — licznik jej nie widzi.
        # Wczesniejsze odejmowanie zanizalo wynik i robilo martwymi funkcje
        # uzywane dokladnie tyle razy, ile razy zdefiniowane.
        w_src = u_src[n]
        dwuznaczna = ile_definicji[n] > 1
        fn["pokrycie"], fn["pct"] = _procent(fn, pokrycie)
        fn["uzycia"] = f"{w_src}/{u_tests[n]}"
        fn["status"] = _status(fn, w_src, u_tests[n], u_scripts[n], dwuznaczna)

    wg_warstwy: dict[str, list[dict]] = defaultdict(list)
    for fn in funkcje:
        wg_warstwy[fn["warstwa"]].append(fn)

    statusy = Counter(f["status"] for f in funkcje)
    martwe = [f for f in funkcje if f["status"].startswith(("MARTWA", "TYLKO-TEST"))]

    L: list[str] = []
    L.append("# Inwentarz funkcji FootStats\n")
    L.append("> Plik **generowany** — `python scripts/inwentarz_funkcji.py`. "
             "Nie edytuj ręcznie, bo nadpisze. Poza gitem (migawka lokalna).\n")
    L.append(f"Funkcji: **{len(funkcje)}** w {len({f['plik'] for f in funkcje})} modułach. "
             f"Pokrycie liczone z `.coverage` z ostatniego przebiegu pytest.\n")

    L.append("\n## Legenda statusu\n")
    L.append("| Status | Znaczenie |")
    L.append("|---|---|")
    L.append("| `PROD` | wołana z `src/` — żyje w produkcji |")
    L.append("| `WEJŚCIE` | wołana przez framework/interpreter (endpoint, `main`, dunder) |")
    L.append("| `TYLKO-TEST` | referencje wyłącznie z `tests/` lub `scripts/` — nie działa w produkcji |")
    L.append("| `MARTWA` | zero referencji poza definicją — **kandydat do usunięcia** |")
    L.append("| `?` na końcu | nazwa zdefiniowana w kilku miejscach → licznik niewiarygodny, sprawdź ręcznie |")
    L.append("\nKolumna 'użycia' to `referencje w src / referencje w tests`.\n")

    L.append("\n## Podsumowanie\n")
    L.append("| Status | Ile |")
    L.append("|---|---:|")
    for st, ile in sorted(statusy.items(), key=lambda x: _KOLEJNOSC.get(x[0], 9)):
        L.append(f"| {st} | {ile} |")

    if martwe:
        L.append(f"\n## Do przeglądu — {len(martwe)} funkcji bez użycia produkcyjnego\n")
        L.append("Najpierw te, bo tu jest robota. Reszta niżej, warstwami.\n")
        L.append("| Funkcja | Plik:linia | Status | Pokrycie | Opis |")
        L.append("|---|---|---|---:|---|")
        for fn in sorted(martwe, key=lambda f: (_KOLEJNOSC.get(f["status"], 9), f["plik"], f["od"])):
            pelna = f"{fn['klasa']}.{fn['nazwa']}" if fn["klasa"] else fn["nazwa"]
            L.append(f"| `{pelna}` | {fn['plik']}:{fn['od']} | {fn['status']} | "
                     f"{fn['pokrycie']} | {fn['opis']} |")

    kolejnosc_warstw = [e for _, e in _WARSTWY] + [_WARSTWA_ROOT]
    for warstwa in kolejnosc_warstw:
        lista = wg_warstwy.get(warstwa)
        if not lista:
            continue
        zmierzone = [f["pct"] for f in lista if f["pct"] is not None]
        srednia = f"{sum(zmierzone)/len(zmierzone):.0f}%" if zmierzone else "n/d"
        L.append(f"\n## {warstwa}\n")
        L.append(f"Funkcji: {len(lista)} · średnie pokrycie: {srednia}\n")
        L.append("| Funkcja | Plik:linia | Status | Pokr. | Użycia | Opis |")
        L.append("|---|---|---|---:|---:|---|")
        for fn in sorted(lista, key=lambda f: (_KOLEJNOSC.get(f["status"], 9), f["plik"], f["od"])):
            pelna = f"{fn['klasa']}.{fn['nazwa']}" if fn["klasa"] else fn["nazwa"]
            L.append(f"| `{pelna}` | {fn['plik']}:{fn['od']} | {fn['status']} | "
                     f"{fn['pokrycie']} | {fn['uzycia']} | {fn['opis']} |")

    L.append("\n---\n")
    L.append("**Jak czytać ostrożnie:** wykrywanie użycia jest po nazwie, więc "
             "wywołania dynamiczne (`getattr`, rejestry) mogą umknąć, a nazwy "
             "powtarzalne dostają `?`. `MARTWA` to kandydat do usunięcia, nie wyrok — "
             "zweryfikuj, zanim skasujesz.\n")

    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return {"funkcji": len(funkcje), "statusy": dict(statusy), "martwe": len(martwe)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Inwentarz funkcji FootStats")
    ap.add_argument("--cov", default="coverage.json", help="raport JSON z coverage")
    ap.add_argument("--out", default="FUNCTIONS.md", help="plik wynikowy")
    a = ap.parse_args()
    wynik = generuj(Path(a.cov), _ROOT / a.out)
    print(f"FUNCTIONS.md: {wynik['funkcji']} funkcji, "
          f"{wynik['martwe']} bez użycia produkcyjnego")
    for st, ile in sorted(wynik["statusy"].items()):
        print(f"  {st:<14} {ile}")
