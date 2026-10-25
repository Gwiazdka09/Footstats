import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import MatchAnalysisView from './MatchAnalysisView';

/**
 * Opis meczu (23.10) jest TYLKO dla właściciela. Zwykły użytkownik nie może
 * zobaczyć przycisku — nasze liczby nie pokazują się w GUI poza kreatorem.
 */
const KARTA = {
  home: 'Arsenal', away: 'Chelsea', liga: 'Premier League', data: '2026-10-25',
  home_stats: { team: 'Arsenal', gf_pg: 1.7, ga_pg: 0.6 },
  away_stats: { team: 'Chelsea', gf_pg: 1.5, ga_pg: 1.1 },
};

const apiFetchZ = (opis) => vi.fn((endpoint) => {
  if (endpoint.startsWith('/analyses/matches')) return Promise.resolve({ matches: [KARTA] });
  if (endpoint === '/admin/opis-meczu') {
    return Promise.resolve({
      karta: {
        poisson: { p1: 59.3, px: 24.6, p2: 16.1, over25: 44.8, btts: 43.8 },
        bzzoiro: null,
        rynek: { p1: 55.0, px: 25.0, p2: 20.0 },
      },
      opis,
      z_cache: false,
    });
  }
  return Promise.reject(new Error('nieznany endpoint'));
});

describe('Analizy meczów — opis tylko dla admina', () => {
  it('zwykły użytkownik nie widzi przycisku opisu', async () => {
    render(<MatchAnalysisView apiFetch={apiFetchZ('x')} />);
    await screen.findByText('Premier League');
    expect(screen.queryByRole('button', { name: /opis \(admin\)/i })).toBeNull();
  });

  it('admin pobiera opis i widzi kartę liczb', async () => {
    const api = apiFetchZ('Arsenal faworytem wg Poissona.');
    render(<MatchAnalysisView apiFetch={api} isAdmin />);
    fireEvent.click(await screen.findByRole('button', { name: /opis \(admin\)/i }));
    expect(await screen.findByText('Arsenal faworytem wg Poissona.')).toBeInTheDocument();
    expect(screen.getByText('59.3%')).toBeInTheDocument();
    const [, opcje] = api.mock.calls.find(([e]) => e === '/admin/opis-meczu');
    expect(JSON.parse(opcje.body)).toMatchObject({ home: 'Arsenal', away: 'Chelsea' });
  });

  it('brak opisu z LLM pokazuje samą kartę z komunikatem', async () => {
    render(<MatchAnalysisView apiFetch={apiFetchZ(null)} isAdmin />);
    fireEvent.click(await screen.findByRole('button', { name: /opis \(admin\)/i }));
    expect(await screen.findByText(/opis niedostępny/i)).toBeInTheDocument();
  });
});

describe('Analizy meczów — wyszukiwarka', () => {
  it('wpisanie „barc” pyta API z ?q=barc', async () => {
    const api = apiFetchZ('x');
    render(<MatchAnalysisView apiFetch={api} />);
    await screen.findByText('Premier League');
    fireEvent.change(screen.getByLabelText('Szukaj meczu'), { target: { value: 'barc' } });
    await waitFor(() => expect(api).toHaveBeenCalledWith('/analyses/matches?q=barc'));
    expect(await screen.findByText(/Wyniki dla „barc”/)).toBeInTheDocument();
  });

  it('pusty wynik wyszukiwania pokazuje komunikat', async () => {
    const api = vi.fn((e) => Promise.resolve({ matches: e.includes('q=') ? [] : [KARTA] }));
    render(<MatchAnalysisView apiFetch={api} />);
    await screen.findByText('Premier League');
    fireEvent.change(screen.getByLabelText('Szukaj meczu'), { target: { value: 'zzzz' } });
    expect(await screen.findByText('Brak nadchodzących meczów dla „zzzz”')).toBeInTheDocument();
  });

  it('jeden znak nie uruchamia wyszukiwania', async () => {
    const api = apiFetchZ('x');
    render(<MatchAnalysisView apiFetch={api} />);
    await screen.findByText('Premier League');
    fireEvent.change(screen.getByLabelText('Szukaj meczu'), { target: { value: 'b' } });
    await new Promise(r => setTimeout(r, 600));
    expect(api.mock.calls.some(([e]) => e.includes('q='))).toBe(false);
    expect(screen.getByText('Dziś i jutro')).toBeInTheDocument();
  });
});
