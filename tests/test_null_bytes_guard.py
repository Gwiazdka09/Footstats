"""test_null_bytes_guard.py — Verify no null bytes in critical modules."""

from pathlib import Path

import pytest


def test_no_null_bytes_in_core_modules():
    """Check that core .py files have no embedded null bytes."""
    root = Path(__file__).parent.parent / "src" / "footstats"
    critical_modules = [
        "ai/analyzer.py",
        "core/async_utils.py",
        "core/response_cache.py",
    ]

    for module in critical_modules:
        fpath = root / module
        assert fpath.exists(), f"Module {module} not found"

        with open(fpath, "rb") as f:
            content = f.read()

        assert b"\x00" not in content, f"Null bytes found in {module}"


def test_python_syntax_valid():
    """Każdy moduł w src/footstats musi się kompilować.

    28.08 — PRZEPISANE Z `subprocess python -m py_compile`. Tamta wersja miała
    dwie wady, obie zmierzone:

    * `py_compile` ZAPISUJE bajtkod do `src/footstats/**/__pycache__`, wspólnego
      dla wszystkich procesów. Dwa równoległe przebiegi pytest kompilowały te
      same pliki w to samo miejsce — jeden nadpisywał plik, który drugi właśnie
      czytał. Test padał wtedy `UnicodeDecodeError` na `result.stderr.decode()`,
      bo komunikat błędu Pythona przychodzi w kodowaniu konsoli (cp1250), a nie
      w UTF-8. Objaw wyglądał na uszkodzone źródło, a źródło było w porządku;
    * jeden `subprocess` NA PLIK — ponad 170 procesów na jeden test.

    `compile()` w procesie sprawdza dokładnie to samo (składnię), niczego nie
    zapisuje na dysk i nie ma z czym kolidować.
    """
    root = Path(__file__).parent.parent / "src" / "footstats"

    bledy = []
    for pyfile in root.rglob("*.py"):
        if "__pycache__" in str(pyfile):
            continue
        try:
            compile(pyfile.read_text(encoding="utf-8"), str(pyfile), "exec")
        except SyntaxError as e:
            bledy.append(f"{pyfile}: {e}")
        except UnicodeDecodeError as e:
            bledy.append(f"{pyfile}: plik nie jest poprawnym UTF-8 ({e})")

    assert not bledy, "Nie kompiluje sie:\n" + "\n".join(bledy)


def test_wykrywa_zepsuta_skladnie(tmp_path):
    """Kontrola do testu wyżej: gdyby `compile()` przestało cokolwiek sprawdzać,
    strażnik świeciłby na zielono nad zepsutym drzewem."""
    zepsuty = tmp_path / "src" / "footstats" / "modul.py"
    zepsuty.parent.mkdir(parents=True)
    zepsuty.write_text("def f(:\n", encoding="utf-8")

    with pytest.raises(SyntaxError):
        compile(zepsuty.read_text(encoding="utf-8"), str(zepsuty), "exec")
