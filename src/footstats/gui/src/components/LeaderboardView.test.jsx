import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import LeaderboardView from './LeaderboardView';

describe('LeaderboardView', () => {
  it('blad pobrania oczekujacych daje komunikat, a nie ciche "brak oczekujacych"', async () => {
    const apiFetch = vi.fn((sciezka) => {
      if (sciezka.startsWith('/leaderboard/pending')) return Promise.reject(new Error('boom'));
      return Promise.resolve(sciezka === '/auth/me' ? { leaderboard_opt_in: false } : []);
    });
    render(<LeaderboardView apiFetch={apiFetch} />);
    expect(await screen.findByText(/Nie udało się pobrać listy świeżo udostępnionych/)).toBeInTheDocument();
  });

  it('ponowienie po bledzie oczekujacych usuwa baner po udanym pobraniu', async () => {
    let proby = 0;
    const apiFetch = vi.fn((sciezka) => {
      if (sciezka.startsWith('/leaderboard/pending')) {
        proby += 1;
        return proby === 1 ? Promise.reject(new Error('boom')) : Promise.resolve([]);
      }
      return Promise.resolve(sciezka === '/auth/me' ? { leaderboard_opt_in: false } : []);
    });
    render(<LeaderboardView apiFetch={apiFetch} />);
    await screen.findByText(/Nie udało się pobrać listy świeżo udostępnionych/);
    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }));
    await waitFor(() => expect(
      screen.queryByText(/Nie udało się pobrać listy świeżo udostępnionych/)
    ).not.toBeInTheDocument());
    expect(proby).toBe(2);
  });

  it('ponowienie, ktore tez pada, zostawia baner', async () => {
    const apiFetch = vi.fn((sciezka) => {
      if (sciezka.startsWith('/leaderboard/pending')) return Promise.reject(new Error('boom'));
      return Promise.resolve(sciezka === '/auth/me' ? { leaderboard_opt_in: false } : []);
    });
    render(<LeaderboardView apiFetch={apiFetch} />);
    await screen.findByText(/Nie udało się pobrać listy świeżo udostępnionych/);
    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }));
    await waitFor(() => expect(
      apiFetch.mock.calls.filter(([s]) => s.startsWith('/leaderboard/pending'))
    ).toHaveLength(2));
    expect(screen.getByText(/Nie udało się pobrać listy świeżo udostępnionych/)).toBeInTheDocument();
  });
});
