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

describe('Analizy meczów — start meczu i teksty', () => {
  it('pokazuje dzień, datę i godzinę z API', async () => {
    const karta = { ...KARTA, data: '2026-10-31', data_pl: '2026-10-31', godzina: '20:00' };
    const api = vi.fn(() => Promise.resolve({ matches: [karta] }));
    render(<MatchAnalysisView apiFetch={api} />);
    expect(await screen.findByText('sob 31.10 · 20:00')).toBeInTheDocument();
  });

  it('bez godziny pokazuje samą datę', async () => {
    const api = vi.fn(() => Promise.resolve({ matches: [{ ...KARTA, data: '2026-10-31' }] }));
    render(<MatchAnalysisView apiFetch={api} />);
    expect(await screen.findByText('sob 31.10')).toBeInTheDocument();
  });

  it('podtytuł i pusta lista zgodne z widokiem dziś i jutro', async () => {
    const api = vi.fn(() => Promise.resolve({ matches: [] }));
    render(<MatchAnalysisView apiFetch={api} />);
    expect(screen.getByText(/dziś i jutro; wyszukiwarka obejmuje cały tydzień/)).toBeInTheDocument();
    expect(await screen.findByText('Brak nadchodzących ważnych meczów dziś i jutro.')).toBeInTheDocument();
  });
});

describe('Analizy meczów — podpis strzelców z poprzedniego sezonu', () => {
  const NOTKA = /Strzelcy wg poprzedniego sezonu/;
  const ze_strzelcami = (flaga) => ({
    ...KARTA,
    top_scorers_home: [{ name: 'Lewandowski', goal_share: 0.3 }],
    strzelcy_poprzedni_sezon: flaga,
  });
  const api = (karta) => vi.fn(() => Promise.resolve({ matches: [karta] }));

  it('z flagą pokazuje podpis pod strzelcami', async () => {
    render(<MatchAnalysisView apiFetch={api(ze_strzelcami(true))} />);
    expect(await screen.findByText(NOTKA)).toBeInTheDocument();
  });

  it('bez flagi podpisu nie ma', async () => {
    render(<MatchAnalysisView apiFetch={api(ze_strzelcami(false))} />);
    await screen.findByText(/Lewandowski/);
    expect(screen.queryByText(NOTKA)).toBeNull();
  });
});
