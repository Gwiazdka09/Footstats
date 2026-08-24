"""Adres serwisu żyje w ośmiu plikach naraz — przeprowadzka na własną domenę
musi objąć wszystkie, bo połowiczna zmiana jest niewidoczna.

DLACZEGO TO NIE JEST KOSMETYKA:

1. **Regulamin §1.1 nazywa adres Serwisu.** Jeśli dokument mówi
   `bot-opal-nu.vercel.app`, a użytkownik siedzi na `footstats.pl`, to regulamin
   formalnie opisuje INNY serwis niż ten, z którego ktoś korzysta. Ten sam kształt
   błędu co polityka wskazująca Neon zamiast Supabase (naprawione 24.08).
2. **`canonical` i `sitemap.xml` zostawione na starym hoście** każą wyszukiwarce
   indeksować adres, który po przeniesieniu przestaje być kanoniczny — a `robots.txt`
   wskazuje wtedy sitemapę spod obcej domeny i bywa ignorowany w całości.
3. Żadna z tych rzeczy nie rzuca błędu. Strona się buduje, testy przechodzą,
   serwis odpowiada 200. Dokładnie ten rodzaj cichej degradacji, który w tym
   projekcie wychodził już pięć razy w ciągu jednego dnia.

JAK UŻYĆ PRZY ZAKUPIE DOMENY: zmień `ADRES_PUBLICZNY` na nową domenę i uruchom ten
plik. Testy wypunktują każdy plik, którego nie ruszyłeś. Dopiero gdy są zielone,
przeprowadzka jest kompletna.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KORZEN = Path(__file__).resolve().parents[1]

# JEDYNE ŹRÓDŁO PRAWDY o publicznym adresie serwisu. Zmiana tutaj = lista roboty.
ADRES_PUBLICZNY = "bot-opal-nu.vercel.app"

# Pliki, w których adres MUSI wystąpić. Nie jest to lista „gdzie przypadkiem jest" —
# w każdym z nich brak adresu albo adres nieaktualny ma konkretny skutek.
PLIKI_Z_ADRESEM = [
    "src/footstats/api/regulamin.html",        # §1.1 — jaki serwis opisuje dokument
    "src/footstats/gui/index.html",            # canonical + og:url
    "src/footstats/gui/public/sitemap.xml",    # co indeksuje wyszukiwarka
    "src/footstats/gui/public/robots.txt",     # gdzie leży sitemapa
    "README.md",
    "README.pl.md",
    "STATUS.md",
]

HOST_VERCEL = re.compile(r"[a-z0-9][a-z0-9-]*\.vercel\.app")


@pytest.mark.parametrize("rel", PLIKI_Z_ADRESEM)
def test_plik_wskazuje_aktualny_adres(rel: str) -> None:
    sciezka = KORZEN / rel
    assert sciezka.exists(), f"{rel} nie istnieje — zaktualizuj PLIKI_Z_ADRESEM"

    tresc = sciezka.read_text(encoding="utf-8")

    assert ADRES_PUBLICZNY in tresc, (
        f"{rel}: brak aktualnego adresu '{ADRES_PUBLICZNY}'. "
        "Przy przeprowadzce na własną domenę ten plik został pominięty."
    )


def test_nigdzie_nie_zostal_stary_host_vercel() -> None:
    """Po przeprowadzce na własną domenę żaden `*.vercel.app` nie ma prawa zostać.

    Dopóki `ADRES_PUBLICZNY` sam jest hostem Vercela, test pilnuje tylko tego,
    żeby nie pojawił się DRUGI, rozjechany host — np. z innego deploymentu.
    """
    znalezione: dict[str, set[str]] = {}

    for rel in PLIKI_Z_ADRESEM:
        sciezka = KORZEN / rel
        if not sciezka.exists():
            continue
        obce = {h for h in HOST_VERCEL.findall(sciezka.read_text(encoding="utf-8"))
                if h != ADRES_PUBLICZNY}
        if obce:
            znalezione[rel] = obce

    assert not znalezione, (
        f"nieaktualne hosty Vercela po przeprowadzce na '{ADRES_PUBLICZNY}': "
        f"{znalezione}"
    )


def test_regulamin_nie_opisuje_innego_serwisu() -> None:
    """§1.1 to jedyne miejsce, gdzie adres ma skutek prawny, nie tylko SEO."""
    tresc = (KORZEN / "src/footstats/api/regulamin.html").read_text(encoding="utf-8")

    paragraf = re.search(r"dostępnego pod adresem\s*<strong>([^<]+)</strong>", tresc)

    assert paragraf, "§1.1 regulaminu nie wskazuje adresu Serwisu"
    assert paragraf.group(1).strip() == ADRES_PUBLICZNY, (
        f"regulamin opisuje serwis pod adresem '{paragraf.group(1).strip()}', "
        f"a serwis stoi pod '{ADRES_PUBLICZNY}'"
    )
