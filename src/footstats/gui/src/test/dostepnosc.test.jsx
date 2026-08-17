import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ZRODLA = join(dirname(fileURLToPath(import.meta.url)), '..');

/**
 * Straznik dostepnosci na poziomie calego frontu (F2 z audytu 17.08).
 *
 * Stan zastany: 0 x `aria-label`, 0 x `alt`, 0 x `role` w 3381 liniach JSX.
 * Najbardziej bolaly przyciski z SAMA IKONA — czytnik ekranu anonsuje je jako
 * "przycisk" i nic wiecej, wiec menu mobilne i zamykanie formularza byly dla
 * niewidomego uzytkownika nieoznaczonymi klawiszami.
 *
 * Testy komponentowe (LoginView) sprawdzaja realne drzewo dostepnosci. Ten plik
 * lapie regresje SZERZEJ: nowy przycisk z sama ikona ma podniesc alarm od razu,
 * bez czekania, az ktos napisze do niego dedykowany test.
 */

const plikiJsx = () => {
  const wynik = [];
  const chodz = (katalog) => {
    for (const wpis of readdirSync(katalog, { withFileTypes: true })) {
      const sciezka = join(katalog, wpis.name);
      if (wpis.isDirectory()) chodz(sciezka);
      else if (wpis.name.endsWith('.jsx') && !wpis.name.endsWith('.test.jsx')) wynik.push(sciezka);
    }
  };
  chodz(ZRODLA);
  return wynik;
};

/**
 * Przycisk bez tekstu, bez `aria-label` i bez `title` = brak nazwy dla czytnika.
 *
 * Analiza jest STATYCZNA, wiec musi uznac trzy zrodla nazwy, ktorych nie widac
 * wprost w tekscie: literal w dowolnym wyrazeniu JSX (`{loading ? 'A' : 'B'}`),
 * goly identyfikator (`{submitLabel}` — zmienna niosaca napis) oraz `aria-label`.
 * Bez tego test krzyczalby na poprawne przyciski, a falszywe alarmy ucza
 * ignorowac straznika — czyli szkodza bardziej niz jego brak.
 */
const bezNazwy = (zrodlo) => {
  const winne = [];
  for (const m of zrodlo.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)) {
    const [caly, atrybuty, wnetrze] = m;
    if (/aria-label|title=/.test(atrybuty)) continue;

    const tekst = wnetrze.replace(/<[^>]+>/g, ' ').replace(/\{[\s\S]*?\}/g, ' ').trim();
    const wyrazenia = [...wnetrze.matchAll(/\{([\s\S]*?)\}/g)].map((w) => w[1]);
    const maLiteral = wyrazenia.some((w) => /['"`][^'"`]{2,}['"`]/.test(w));
    // goly identyfikator albo pole obiektu: `{submitLabel}`, `{item.label}`
    const maZmienna = wyrazenia.some((w) => /^\s*[a-z_$][\w$]*(\.[\w$]+)*\s*$/i.test(w));

    if (!tekst && !maLiteral && !maZmienna) {
      winne.push(caly.slice(0, 70).replace(/\s+/g, ' '));
    }
  }
  return winne;
};

describe('dostepnosc frontu', () => {
  const pliki = plikiJsx();

  it('znajduje pliki do sprawdzenia', () => {
    expect(pliki.length).toBeGreaterThan(5);
  });

  it('zaden przycisk nie zostaje bez nazwy dla czytnika ekranu', () => {
    const problemy = [];
    for (const plik of pliki) {
      for (const przycisk of bezNazwy(readFileSync(plik, 'utf-8'))) {
        problemy.push(`${plik.split(/[\\/]/).pop()}: ${przycisk}`);
      }
    }
    expect(problemy).toEqual([]);
  });

  it('kazdy obrazek ma alt', () => {
    const problemy = [];
    for (const plik of pliki) {
      const zrodlo = readFileSync(plik, 'utf-8');
      for (const m of zrodlo.matchAll(/<img\b[^>]*>/g)) {
        if (!/\balt=/.test(m[0])) problemy.push(`${plik}: ${m[0].slice(0, 60)}`);
      }
    }
    expect(problemy).toEqual([]);
  });

  /**
   * `<div onClick>` jest niedostepny z klawiatury (brak fokusu, brak Enter/Spacji)
   * i niewidoczny dla czytnika ekranu — nie ma roli "przycisk".
   *
   * PROG BAZOWY, nie ideal — dokladnie jak `tests/test_broad_except_audit.py`
   * po stronie backendu. Liczba ma tylko SPADAC; nowy klikalny `<div>` lamie build.
   *
   * Uwaga historyczna: audyt z 17.08 zaraportowal tu ZERO i wpisal to jako plus.
   * To bylo falszywe trafienie regexa jednolinijkowego — te tagi rozbijaja sie
   * na wiele linii. Realnie jest ich szesc.
   */
  const PROG_KLIKALNYCH_DIV = 6;

  it('liczba klikalnych <div> nie rosnie', () => {
    const problemy = [];
    for (const plik of pliki) {
      const zrodlo = readFileSync(plik, 'utf-8');
      for (const m of zrodlo.matchAll(/<(div|span)\b[^>]*?\bonClick=/gs)) {
        problemy.push(`${plik.split(/[\\/]/).pop()}: ${m[0].slice(0, 40).replace(/\s+/g, ' ')}`);
      }
    }
    expect(problemy.length).toBeLessThanOrEqual(PROG_KLIKALNYCH_DIV);
  });
});
