import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import MarketStatsSection from './MarketStatsSection';

describe('MarketStatsSection', () => {
  it('null w implied_prob i edge_pp daje kreske zamiast procentu i pp', () => {
    const stat = {
      market: 'Wynik 1X2', n: 3, wins: 2, hit_rate: 2 / 3,
      implied_prob: null, edge_pp: null, se_pp: 27, n_za_male: true, skladniki: [],
    };
    render(<MarketStatsSection stats={[stat]} />);
    expect(screen.getByText('kurs implikuje —')).toBeInTheDocument();
    expect(screen.getByText('różnica —')).toBeInTheDocument();
    expect(screen.getByText('trafność 67%')).toBeInTheDocument();
  });
});
