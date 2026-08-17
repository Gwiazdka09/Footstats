import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const KATALOG = dirname(fileURLToPath(import.meta.url));

/**
 * Analityka Vercela ladowala sie BEZWARUNKOWO, zanim ktokolwiek dotknal banera
 * zgody. Flaga `fs_cookie_consent` byla czytana wylacznie przez sam baner, wiec
 * przycisk "Rozumiem" nie wlaczal ani nie wylaczal niczego. Baner twierdzil przy
 * tym, ze uzywamy WYLACZNIE plikow niezbednych, a polityka prywatnosci
 * o analityce milczala.
 *
 * Ten test czyta zrodlo `main.jsx`, bo samego montowania roota nie da sie sensownie
 * wyrenderowac w jsdom. Tani straznik: gdyby analityka wrocila razem z jakas inna
 * zmiana, build padnie zamiast po cichu wznowic zbieranie danych bez zgody.
 */
/** Usuwa komentarze — inaczej test lapie WLASNE wyjasnienie, ktore z koniecznosci
 *  wymienia nazwy usunietych komponentow. Sprawdzamy KOD, nie proze o kodzie. */
const bezKomentarzy = (tekst) =>
  tekst.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');

describe('punkt wejscia aplikacji', () => {
  const zrodlo = bezKomentarzy(readFileSync(join(KATALOG, 'main.jsx'), 'utf-8'));

  it('NIE montuje analityki bez bramki zgody', () => {
    expect(zrodlo).not.toMatch(/@vercel\/analytics/);
    expect(zrodlo).not.toMatch(/@vercel\/speed-insights/);
    expect(zrodlo).not.toMatch(/<Analytics\b/);
    expect(zrodlo).not.toMatch(/<SpeedInsights\b/);
  });

  it('dalej montuje baner zgody', () => {
    expect(zrodlo).toMatch(/<CookieConsent\b/);
  });

  it('zaleznosci @vercel/* nie wrocily do package.json', () => {
    const pkg = JSON.parse(readFileSync(join(KATALOG, '..', 'package.json'), 'utf-8'));
    const wszystkie = { ...pkg.dependencies, ...pkg.devDependencies };
    const vercelowe = Object.keys(wszystkie).filter((k) => k.startsWith('@vercel/'));
    expect(vercelowe).toEqual([]);
  });
});
