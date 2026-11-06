import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
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
});
