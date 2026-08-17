import { describe, expect, it } from 'vitest';
import { decodeJwtPayload, legalUrl } from './api';

/**
 * `legalUrl` powstalo 17.08, gdy ten sam surowy adres Cloud Run siedzial zaszyty
 * w TRZECH miejscach (baner cookie + regulamin i polityka w stopce). Po zmianie
 * hostingu wszystkie trzy linki umarlyby po cichu, kazdy osobno.
 *
 * Strony prawne serwuje API, nie front, wiec sciezka wzgledna by ich nie znalazla —
 * stad wyliczanie z `API_BASE` i odcinanie sufiksu `/api`.
 */
describe('legalUrl', () => {
  it('daje adres w korzeniu API, bez sufiksu /api', () => {
    expect(legalUrl('regulamin')).not.toContain('/api/regulamin');
    expect(legalUrl('regulamin')).toMatch(/\/regulamin$/);
  });

  it('nie zostawia podwojnego ukosnika', () => {
    expect(legalUrl('polityka-prywatnosci')).not.toMatch(/[^:]\/\//);
  });

  it('sklada pelna sciezke', () => {
    expect(legalUrl('polityka-prywatnosci')).toMatch(/polityka-prywatnosci$/);
  });
});

/**
 * `decodeJwtPayload` czyta claim `adm`, czyli decyduje o pokazaniu panelu admina.
 * To NIE jest weryfikacja podpisu — prawdziwa bramka stoi na backendzie. Test
 * pilnuje, zeby smieciowy token nie wywalil calej aplikacji bialym ekranem.
 */
describe('decodeJwtPayload', () => {
  const zbuduj = (payload) =>
    ['naglowek', btoa(JSON.stringify(payload)).replace(/=+$/, ''), 'podpis'].join('.');

  it('czyta claimy z poprawnego tokenu', () => {
    expect(decodeJwtPayload(zbuduj({ sub: 'admin', uid: 1, adm: true }))).toMatchObject({
      sub: 'admin',
      uid: 1,
      adm: true,
    });
  });

  it('smieciowy token daje null zamiast wyjatku', () => {
    expect(decodeJwtPayload('to-nie-jest-jwt')).toBeNull();
    expect(decodeJwtPayload('')).toBeNull();
    expect(decodeJwtPayload('a.b.c')).toBeNull();
  });

  it('brak tokenu nie wywala aplikacji', () => {
    expect(decodeJwtPayload(null)).toBeNull();
    expect(decodeJwtPayload(undefined)).toBeNull();
  });

  it('token bez claimu adm nie udaje admina', () => {
    const dane = decodeJwtPayload(zbuduj({ sub: 'user', uid: 7 }));
    expect(dane.adm).toBeUndefined();
  });
});
