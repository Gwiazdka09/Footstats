import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import SettingsView from './SettingsView';

describe('SettingsView', () => {
  it('blad /auth/me daje komunikat zamiast cichego pustego konta', async () => {
    const apiFetch = vi.fn().mockRejectedValue(new Error('boom'));
    render(<SettingsView status={{ bankroll: 100 }} apiFetch={apiFetch} user="jan" onLogout={vi.fn()} />);
    expect(await screen.findByText(/Nie udało się pobrać danych konta/)).toBeInTheDocument();
  });
});
