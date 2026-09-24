"""Cache odpowiedzi nie może podać danych jednego użytkownika drugiemu.

`@cached_response` trzyma odpowiedzi w słowniku w pamięci procesu, a kluczem jest
nazwa funkcji plus WYBRANE parametry (`vary_by`). Jeśli endpoint zwraca dane
konkretnego konta, a `user_id` nie trafi do `vary_by`, klucz dla wszystkich jest
IDENTYCZNY — pierwszy, kto wejdzie, wypełnia cache, a każdy następny dostaje jego
kupony, saldo i statystyki. Cichy wyciek między kontami, bez żadnego błędu w logu.

Dziś wszystkie takie endpointy mają `vary_by=["user_id"]` (sprawdzone). Ten plik
pilnuje, żeby nowy endpoint nie zapomniał — wylicza trasy Z KODU, więc dopisanie
kolejnej funkcji z `user_id` i cache'em zapali się tutaj samo.

Drugi wątek: nagłówek `Cache-Control`. Odpowiedź uwierzytelniona nie ma prawa
trafić do cache'u współdzielonego (proxy, CDN), więc musi nieść `private`.
Dziś nic takiego przed API nie stoi, ale nagłówek jest jedyną rzeczą, która o tym
mówi pośrednikowi — a postawienie CDN-a to zmiana infrastruktury, nie kodu, więc
nikt przy niej nie zajrzy do tego dekoratora.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

KATALOG_TRAS = Path(__file__).resolve().parents[1] / "src" / "footstats" / "api" / "routes"


# Świadoma zgoda na cache WSPÓLNY dla wszystkich kont. Dopisywana przy dekoratorze
# tam, gdzie odpowiedź nie zależy od użytkownika (terminarz ligi jest ten sam dla
# każdego, a wspólny wpis oszczędza scrapowanie). Marker ma być widoczny w diffie —
# o tym, czy dane są wspólne, nie da się rozstrzygnąć automatem.
MARKER_WSPOLNY = "cache-wspolny"


def _funkcje_z_cache() -> list[tuple[str, str, list[str], list[str], bool]]:
    """(plik, funkcja, vary_by, parametry, czy_marker) dla tras z `@cached_response`."""
    out: list[tuple[str, str, list[str], list[str], bool]] = []
    for plik in sorted(KATALOG_TRAS.glob("*.py")):
        tekst = plik.read_text(encoding="utf-8")
        linie = tekst.splitlines()
        drzewo = ast.parse(tekst)
        for wezel in ast.walk(drzewo):
            if not isinstance(wezel, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dek in wezel.decorator_list:
                if not (isinstance(dek, ast.Call) and getattr(dek.func, "id", "") == "cached_response"):
                    continue
                vary: list[str] = []
                for kw in dek.keywords:
                    if kw.arg == "vary_by" and isinstance(kw.value, ast.List):
                        vary = [str(e.value) for e in kw.value.elts if isinstance(e, ast.Constant)]
                parametry = [a.arg for a in wezel.args.args] + [a.arg for a in wezel.args.kwonlyargs]
                # Marker szukany w kilku liniach nad dekoratorem — tam, gdzie
                # naturalnie stoi komentarz uzasadniający decyzję.
                okno = linie[max(0, dek.lineno - 6):dek.lineno]
                marker = any(MARKER_WSPOLNY in linia for linia in okno)
                out.append((plik.name, wezel.name, vary, parametry, marker))
    return out


def test_sa_trasy_z_cache_do_sprawdzenia() -> None:
    assert len(_funkcje_z_cache()) >= 5, "parser nie widzi dekoratorów — regułę trzeba poprawić"


@pytest.mark.parametrize("plik,nazwa,vary,parametry,marker", _funkcje_z_cache(),
                         ids=lambda w: w if isinstance(w, str) else "")
def test_endpoint_uzytkownika_rozdziela_cache(plik, nazwa, vary, parametry, marker) -> None:
    if "user_id" not in parametry:
        return                                  # trasa publiczna — nie ma czego mieszać
    assert "user_id" in vary or marker, (
        f"{plik}:{nazwa} ma `user_id` w sygnaturze i cache, ale `vary_by` go nie "
        f"zawiera (jest {vary}). Albo dopisz `user_id` do `vary_by`, albo — jeśli "
        f"odpowiedź NIE zależy od konta — postaw nad dekoratorem komentarz "
        f"`{MARKER_WSPOLNY}: <dlaczego>`. Bez jednego z tych dwóch pierwszy pytający "
        "wypełnia cache, a każdy następny dostaje JEGO dane."
    )


def test_klucz_rozni_sie_dla_dwoch_kont() -> None:
    """Kontrola pozytywna na samym budowaniu klucza, nie na kształcie kodu."""
    from footstats.core.response_cache import cache_key_builder

    a = cache_key_builder("get_coupons", ["user_id"], {"user_id": 1})
    b = cache_key_builder("get_coupons", ["user_id"], {"user_id": 2})
    assert a != b, "ten sam klucz dla dwóch kont — cache wymieszałby dane"


def test_cache_faktycznie_izoluje_wywolania() -> None:
    """Przejście przez dekorator: drugie konto NIE MOŻE dostać danych pierwszego."""
    from footstats.core.response_cache import cached_response, clear_response_cache

    clear_response_cache()

    @cached_response(ttl_seconds=60, vary_by=["user_id"])
    def moje_dane(user_id: int = 0):
        return {"czyje": user_id}

    pierwszy = moje_dane(user_id=1)
    drugi = moje_dane(user_id=2)
    import json
    assert json.loads(pierwszy.body)["czyje"] == 1
    assert json.loads(drugi.body)["czyje"] == 2


def test_odpowiedz_ma_naglowek_private() -> None:
    """Bez `private` pośrednik może podać odpowiedź jednego konta następnemu."""
    from footstats.core.response_cache import cached_response, clear_response_cache

    clear_response_cache()

    @cached_response(ttl_seconds=60, vary_by=["user_id"])
    def cokolwiek(user_id: int = 0):
        return {"ok": True}

    miss = cokolwiek(user_id=7)
    hit = cokolwiek(user_id=7)
    assert miss.headers["X-Cache"] == "MISS" and hit.headers["X-Cache"] == "HIT"
    for odp in (miss, hit):
        assert "private" in odp.headers["Cache-Control"], odp.headers["Cache-Control"]
