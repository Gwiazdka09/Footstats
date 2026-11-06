import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App';

/**
 * Blad pobrania danych nie moze wygladac jak "brak danych": dashboard z zerami
 * jest mylacy. Baner z ponowieniem ma sie pokazac po bledzie i zniknac po udanym
 * pobraniu.
 */

const odpowiedz = (dane) => ({ ok: true, status: 200, json: () => Promise.resolve(dane) });

const zDanymi = (url) => {
  if (url.endsWith('/status')) return odpowiedz({ bankroll: 100, stats: {} });
  if (url.endsWith('/auth/me')) return odpowiedz({ birth_ym: '1990-01' });
  if (url.endsWith('/coupons/active') || url.endsWith('/bankroll/history')) return odpowiedz([]);
  return odpowiedz({});
};

beforeEach(() => {
  localStorage.setItem('fs_token', 'a.e30.c');
});

describe('baner bledu pobierania danych', () => {
  it('pokazuje baner z ponowieniem, gdy fetch pada, i chowa go po udanym ponowieniu', async () => {
    let dziala = false;
    global.fetch = vi.fn((url) => (
      dziala ? Promise.resolve(zDanymi(url)) : Promise.reject(new TypeError('Failed to fetch'))
    ));
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(<App />);

    expect(await screen.findByText(/Nie udało się pobrać danych/)).toBeInTheDocument();

    dziala = true;
    fireEvent.click(screen.getByText('Spróbuj ponownie'));

    await waitFor(() => {
      expect(screen.queryByText(/Nie udało się pobrać danych/)).not.toBeInTheDocument();
    });
  });

  it('bez bledu banera nie ma', async () => {
    global.fetch = vi.fn((url) => Promise.resolve(zDanymi(url)));
    render(<App />);
    await screen.findByText(/Witaj,/);
    expect(screen.queryByText(/Nie udało się pobrać danych/)).not.toBeInTheDocument();
  });
});
