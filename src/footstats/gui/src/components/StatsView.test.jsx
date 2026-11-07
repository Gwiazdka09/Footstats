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
});
