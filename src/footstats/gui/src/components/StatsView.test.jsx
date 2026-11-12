import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatsView from './StatsView';

describe('StatsView', () => {
  it('pusta odpowiedz /stats/me renderuje sie bez wyjatku i pokazuje kreske zamiast liczb', async () => {
    const apiFetch = vi.fn((sciezka) =>
      Promise.resolve(sciezka === '/stats/me' ? {} : []),
    );
    render(<StatsView apiFetch={apiFetch} />);
    expect(await screen.findByText('Statystyki')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('pusta odpowiedz nie pokazuje undefined ani NaN, a liczniki daja kreske', async () => {
    const apiFetch = vi.fn((sciezka) =>
      Promise.resolve(sciezka === '/stats/me' ? {} : []),
    );
    const { container } = render(<StatsView apiFetch={apiFetch} />);
    await screen.findByText('Statystyki');
    const tekst = container.textContent;
    expect(tekst).not.toMatch(/undefined/);
    expect(tekst).not.toMatch(/NaN/);
    expect(tekst).toContain('—/— rozliczonych kuponów.');
  });

  const ME = { settled_count: 3, total_coupons: 3, win_rate: 0.5, roi: 0, profit_units: 0,
    current_streak: 1, best_coupon: null, worst_coupon: null };

  it('sekcja wg rodzaju pokazuje trafione/ile, plakietke malej proby i brak rekomendacji', async () => {
    const markets = [{ market: 'Gole drużyny', n: 9, wins: 7, hit_rate: 7 / 9,
      implied_prob: 0.6, edge_pp: 17.8, se_pp: 13.9, n_za_male: true, skladniki: [] }];
    const apiFetch = vi.fn((s) => Promise.resolve(
      s === '/stats/me' ? ME : s === '/stats/markets' ? markets : []));
    render(<StatsView apiFetch={apiFetch} />);
    expect(await screen.findByText('Gole drużyny')).toBeInTheDocument();
    expect(screen.getByText('7/9')).toBeInTheDocument();
    expect(screen.getByText(/mała próba/)).toBeInTheDocument();
    expect(screen.getByText(/\+17\.8 pp/)).toBeInTheDocument();
  });

  it('pusta lista rodzajow pokazuje stan pusty', async () => {
    const apiFetch = vi.fn((s) => Promise.resolve(s === '/stats/me' ? ME : []));
    render(<StatsView apiFetch={apiFetch} />);
    expect(await screen.findByText(/Brak rozliczonych nóg/)).toBeInTheDocument();
  });

  it('blad /stats/markets nie blokuje widoku', async () => {
    const apiFetch = vi.fn((s) => (s === '/stats/markets'
      ? Promise.reject(new Error('503')) : Promise.resolve(s === '/stats/me' ? ME : [])));
    render(<StatsView apiFetch={apiFetch} />);
    expect(await screen.findByText(/Brak rozliczonych nóg/)).toBeInTheDocument();
  });
});
