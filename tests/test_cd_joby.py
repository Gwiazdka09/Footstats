"""I1 — wdrożenie jobów było ręczną pułapką, a pułapka dwa razy wypaliła.

API ma CD od dawna: push na `main` buduje `Dockerfile.api`, taguje pełnym SHA
i wdraża. Joby (`footstats-final` 11:00, `footstats-evening` 23:00) nie miały nic —
obraz budowało się ręcznie (`gcloud builds submit --config cloudbuild_jobs.yaml`),
a potem człowiek przepisywał digest do `gcloud run jobs update`.

DWIE AWARIE Z TEGO SAMEGO ŹRÓDŁA:

  * 29.07 — joby wskazywały ruchomy tag `footstats-jobs:latest` bez przypiętego
    digestu, więc build pomyślany jako neutralny podmienił im obraz przy
    najbliższym uruchomieniu.

  * 30.07-02.08 — pipeline stał TRZY DNI na uszkodzonym obrazie. Po każdym
    buildzie BuildKit tworzy wpisy atestacji, które w `artifacts docker images
    list` wyglądają jak najnowsze obrazy, ale NIE MAJĄ TAGU. Człowiek wziął
    najnowszy digest z listy — czyli atestację, nie obraz.

Obie to porażki procesu ręcznego, nie kodu. Dlatego naprawa jest w CD, a ten test
pilnuje, żeby naprawa nie zdryfowała z powrotem.

DECYZJA, KTÓRA ZMIENIA WCZEŚNIEJSZĄ: `cloudbuild_jobs.yaml` mówił „build ma
budować, podmiana obrazu ma być OSOBNĄ decyzją". To była właściwa reakcja na
awarię 29.07, gdzie obraz podmieniał się PRZYPADKIEM. Deterministyczne wdrożenie
z merge'a na `main` to co innego niż przypadkowa podmiana — a rozjazd kontraktów
(API wdraża się samo, joby nie) jest dokładnie powodem, dla którego joby gniły.
KOSZT ZOSTAJE i nie jest ukryty: od teraz każdy merge na `main` zmienia
produkcyjny pipeline. Dlatego smoke-import stoi PRZED podmianą, nie po.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KORZEN = Path(__file__).resolve().parents[1]
WORKFLOWY = KORZEN / ".github" / "workflows"

JOBY = ("footstats-final", "footstats-evening")


def _teksty_workflowow() -> dict[str, str]:
    if not WORKFLOWY.is_dir():
        pytest.skip("brak katalogu .github/workflows")
    return {p.name: p.read_text(encoding="utf-8") for p in WORKFLOWY.glob("*.yml")}


def _buduje_joby(tresc: str) -> bool:
    """Wzmianka w KOMENTARZU nie liczy się jako budowanie — `dataset_refresh.yml`
    opisuje obraz jobów w nagłówku, a niczego nie buduje."""
    return any(
        "Dockerfile.jobs" in linia and not linia.lstrip().startswith("#")
        for linia in tresc.splitlines()
    )


def _workflow_jobow() -> tuple[str, str]:
    """Plik workflow, który buduje obraz jobów. Zwraca (nazwa, treść)."""
    kandydaci = [
        (nazwa, tresc)
        for nazwa, tresc in _teksty_workflowow().items()
        if _buduje_joby(tresc)
    ]
    assert kandydaci, (
        "zaden workflow nie buduje Dockerfile.jobs — joby znowu wdraza sie recznie (I1)"
    )
    assert len(kandydaci) == 1, (
        f"Dockerfile.jobs budowany w kilku workflowach: {[n for n, _ in kandydaci]}. "
        "Dwa zrodla prawdy o obrazie produkcyjnym to ta sama rodzina bledu co dwa "
        "miejsca pinowania digestu."
    )
    return kandydaci[0]


# ── sedno: joby w ogóle są w CD ─────────────────────────────────────────────

def test_workflow_buduje_obraz_jobow():
    _, tresc = _workflow_jobow()

    assert "docker/build-push-action" in tresc or "docker build" in tresc, (
        "workflow wspomina Dockerfile.jobs, ale niczego nie buduje"
    )


def test_workflow_rusza_na_main():
    _, tresc = _workflow_jobow()

    assert "branches: [main]" in tresc or "- main" in tresc, (
        "workflow jobow nie odpala sie na main — czyli dalej trzeba go wolac recznie"
    )


@pytest.mark.parametrize("job", JOBY)
def test_oba_joby_sa_aktualizowane(job: str):
    """Zaktualizowanie jednego z dwóch daje pipeline z dwóch różnych obrazów —
    stan trudniejszy do zdiagnozowania niż jawna awaria."""
    _, tresc = _workflow_jobow()

    assert job in tresc, f"{job} nie jest aktualizowany w CD"


# ── pułapka BuildKita: atestacje bez tagu ───────────────────────────────────

def test_provenance_wylaczone():
    """Sedno awarii 30.07-02.08. `provenance: false` sprawia, że BuildKit w ogóle
    nie tworzy wpisów atestacji, więc nie ma czego pomylić z obrazem. To naprawa
    u ŹRÓDŁA, nie objawu — inaczej wracamy do wybierania digestu z listy."""
    _, tresc = _workflow_jobow()

    assert re.search(r"provenance:\s*false", tresc), (
        "brak `provenance: false` przy buildzie jobow — BuildKit znowu wygeneruje "
        "wpisy atestacji BEZ TAGU, ktore w `artifacts docker images list` wygladaja "
        "jak najnowszy obraz (awaria 30.07-02.08, pipeline stal 3 dni)"
    )


def test_joby_pinowane_digestem_nie_ruchomym_tagiem():
    """Awaria 29.07: joby wskazywały `:latest`, więc dowolny późniejszy build
    podmieniał im obraz. Job musi dostać `@sha256:...`, nie tag."""
    _, tresc = _workflow_jobow()

    linie_update = [l for l in tresc.splitlines() if "run jobs update" in l or "--image" in l]
    polaczone = " ".join(linie_update)

    assert "@" in polaczone or "digest" in polaczone.lower(), (
        f"joby aktualizowane bez digestu: {linie_update!r}"
    )
    assert ":latest" not in polaczone, (
        "job przypiety do ruchomego tagu `:latest` — dowolny pozniejszy build "
        "podmieni produkcje (awaria 29.07)"
    )


def test_obraz_jobow_nie_dostaje_taga_latest():
    """`:latest` na obrazie jobów to zaproszenie do przypięcia go w jobie."""
    _, tresc = _workflow_jobow()

    zle = [l for l in tresc.splitlines()
           if "footstats-jobs:latest" in l and not l.lstrip().startswith("#")]

    assert not zle, f"obraz jobow tagowany jako :latest: {zle!r}"


# ── kolejność: smoke PRZED podmianą produkcji ───────────────────────────────

def test_smoke_import_przed_podmiana_jobow():
    """Tu kolejność jest bezpieczeństwem, nie stylem — dokładnie jak przy blokadzie
    konta (B7). Obraz instaluje zależności z locka, a sam pakiet przez `--no-deps`,
    więc brakująca paczka wychodzi dopiero PRZY IMPORCIE. Jeśli import odpali się
    po podmianie, produkcja stoi do 11:00 następnego dnia — i tak właśnie wyglądała
    awaria z martwym obrazem."""
    _, tresc = _workflow_jobow()

    i_smoke = tresc.find("smoke")
    i_update = tresc.find("run jobs update")

    assert i_smoke != -1, "brak kroku smoke-import przed podmiana obrazu jobow"
    assert i_update != -1, "workflow nie podmienia obrazu jobow"
    assert i_smoke < i_update, (
        "smoke-import stoi PO podmianie jobow — zepsuty obraz trafi na produkcje "
        "i wyjdzie dopiero o 11:00"
    )


# ── dokumentacja nie może kłamać ────────────────────────────────────────────

def test_cloudbuild_jobow_nie_twierdzi_ze_podmiana_jest_reczna():
    """`cloudbuild_jobs.yaml` opisywał podmianę jako krok wyłącznie ręczny. Po I1
    to nieprawda, a instrukcja, która kłamie, jest gorsza od jej braku — dokładnie
    tak rozjechały się wpisy o B1 w tabeli audytu."""
    plik = KORZEN / "cloudbuild_jobs.yaml"
    if not plik.exists():
        pytest.skip("brak cloudbuild_jobs.yaml")

    tresc = plik.read_text(encoding="utf-8")

    assert "cd-jobs" in tresc or "CD" in tresc, (
        "cloudbuild_jobs.yaml nie wspomina o CD — czytelnik dalej myśli, ze podmiana "
        "obrazu jest wylacznie reczna"
    )


# ── I6: filtr ścieżek nie może odciąć niczego, co ląduje w obrazie ──────────

def _zrodla_z_dockerfile() -> list[str]:
    """Ścieżki repo, które `Dockerfile.jobs` wnosi DO OBRAZU.

    Pomija `COPY --from=...` — tamto ciągnie z innego obrazu, nie z repo.
    """
    plik = KORZEN / "Dockerfile.jobs"
    if not plik.is_file():
        pytest.skip("brak Dockerfile.jobs")
    zrodla: list[str] = []
    for linia in plik.read_text(encoding="utf-8").splitlines():
        linia = linia.strip()
        if not linia.upper().startswith(("COPY ", "ADD ")):
            continue
        czesci = [c for c in linia.split()[1:] if not c.startswith("--")]
        # Ostatni argument to CEL w obrazie, reszta to źródła w repo.
        zrodla.extend(czesci[:-1])
    return zrodla


def _wzorce_paths_ignore(tresc: str) -> list[str]:
    """Wyciąga wpisy `paths-ignore` z sekcji `on:` workflowa."""
    dopasowanie = re.search(r"paths-ignore:\s*\n((?:\s*-\s*.+\n)+)", tresc)
    if not dopasowanie:
        return []
    return [
        linia.strip().lstrip("-").strip().strip("'\"")
        for linia in dopasowanie.group(1).splitlines()
        if linia.strip()
    ]


def _pasuje(sciezka: str, wzorzec: str) -> bool:
    """Uproszczona semantyka globów GitHuba, wystarczająca dla `paths-ignore`."""
    sciezka = sciezka.replace("\\", "/")
    if wzorzec.endswith("/**"):
        return sciezka.startswith(wzorzec[:-3] + "/")
    if wzorzec.startswith("**"):
        return sciezka.endswith(wzorzec[2:])
    return sciezka == wzorzec


def _pliki_sledzone() -> list[str]:
    """Pliki ŚLEDZONE PRZEZ GIT — dokładnie ten zbiór, który może się znaleźć
    w pushu, a więc jedyny, na którym `paths-ignore` cokolwiek robi.

    Chodzenie po dysku byłoby BŁĘDEM: `src/footstats/gui/node_modules` ma
    tysiące plików `README.md`, których żaden push nie zmieni i których
    `.dockerignore` i tak nie wpuszcza do obrazu.
    """
    import subprocess  # noqa: S404 — tylko `git ls-files`, bez danych z zewnatrz

    try:
        wynik = subprocess.run(  # noqa: S603
            ["git", "ls-files"], cwd=KORZEN, capture_output=True,
            text=True, timeout=30, check=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        pytest.skip(f"git ls-files niedostepne: {e}")
    return [w.strip().replace("\\", "/") for w in wynik.stdout.splitlines() if w.strip()]


def _pliki_w_obrazie() -> list[str]:
    """Śledzone pliki, które `Dockerfile.jobs` wnosi do obrazu."""
    korzenie = [z.replace("\\", "/").rstrip("/") for z in _zrodla_z_dockerfile()]
    return [
        plik for plik in _pliki_sledzone()
        if any(plik == k or plik.startswith(k + "/") for k in korzenie)
    ]


def test_filtr_sciezek_nie_odcina_niczego_z_obrazu():
    """SEDNO I6 i jedyny powód, dla którego filtr wolno tu mieć.

    `paths-ignore` oszczędza kilkanaście minut builda z chromium przy commicie
    czysto dokumentacyjnym. Ale filtr, który pominie zmianę lądującą w obrazie,
    przywraca DOKŁADNIE ten dryf między `main` a produkcyjnym obrazem, który
    likwidowało I1 — a tamten dryf trzymał pipeline trzy dni na uszkodzonym
    obrazie i nikt tego nie zauważył, bo joby kończyły się `exit=0`.

    Test nie ufa czytaniu wzorców ze zrozumieniem: bierze REALNE pliki, które
    `Dockerfile.jobs` kopiuje, i sprawdza, że żaden nie pasuje do żadnego
    wzorca ignorowanego. Dopisanie `src/README.md` zapali się tutaj, a nie na
    produkcji za trzy dni.
    """
    _, tresc = _workflow_jobow()
    wzorce = _wzorce_paths_ignore(tresc)
    if not wzorce:
        pytest.skip("workflow jobow nie ma paths-ignore — nie ma czego pilnowac")

    kolizje = [
        (plik, wzorzec)
        for plik in _pliki_w_obrazie()
        for wzorzec in wzorce
        if _pasuje(plik, wzorzec)
    ]
    assert not kolizje, (
        "paths-ignore odcina pliki, ktore Dockerfile.jobs wnosi do obrazu — "
        f"push z taka zmiana NIE przebuduje obrazu, a `main` juz sie rozjedzie: {kolizje[:5]}"
    )


def test_zmiana_samej_dokumentacji_nie_buduje_obrazu():
    """Kontrola pozytywna: gdyby filtr nie obejmował dokumentacji, cały I6
    byłby bez efektu — a to jest jedyny powód tej zmiany."""
    _, tresc = _workflow_jobow()
    wzorce = _wzorce_paths_ignore(tresc)

    assert any(_pasuje("TODO.md", w) for w in wzorce), (
        "zmiana w TODO.md dalej przebudowuje obraz z chromium (~570 MB)"
    )
    assert any(_pasuje("docs/cloud_migration.md", w) for w in wzorce), (
        "zmiana w docs/ dalej przebudowuje obraz jobow"
    )


def test_zmiana_w_src_dalej_buduje_obraz():
    """Kontrola NEGATYWNA — bez niej „filtr" da się rozszerzyć do `**` i test
    wyżej dalej będzie zielony, bo kolizji nie ma tam, gdzie nie ma builda."""
    _, tresc = _workflow_jobow()
    wzorce = _wzorce_paths_ignore(tresc)

    for krytyczny in ("src/footstats/daily_agent.py", "scripts/run_job.sh",
                      "Dockerfile.jobs", "requirements-jobs.lock"):
        assert not any(_pasuje(krytyczny, w) for w in wzorce), (
            f"{krytyczny} jest ignorowany — obraz przestanie nadazac za `main`"
        )
