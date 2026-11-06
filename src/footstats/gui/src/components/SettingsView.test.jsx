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

  it('status = null pokazuje kreski przy saldzie i ROI', async () => {
    const apiFetch = vi.fn().mockResolvedValue({ username: 'jan', email: 'j@x.pl' });
    const { container } = render(
      <SettingsView status={null} apiFetch={apiFetch} user="jan" onLogout={vi.fn()} />
    );
    await screen.findByText('j@x.pl');
    expect(container.textContent).not.toMatch(/undefined|NaN/);
    expect(screen.getByText('ROI').nextElementSibling).toHaveTextContent('—');
    expect(screen.getByText('Balans').nextElementSibling).toHaveTextContent('—');
  });
});
