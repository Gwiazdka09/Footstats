import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import DashboardHome from './DashboardHome';
import { formatKwota, formatRoi } from './ui';

describe('formatRoi / formatKwota', () => {
  it('brak liczby to kreska', () => {
    for (const v of [null, undefined, NaN, 'abc']) {
      expect(formatRoi(v)).toBe('—');
      expect(formatKwota(v)).toBe('—');
    }
  });

  it('liczba dostaje znak i dwa miejsca po przecinku', () => {
    expect(formatRoi(3.2)).toBe('+3.2%');
    expect(formatRoi(0)).toBe('+0%');
    expect(formatRoi(-1.5)).toBe('-1.5%');
    expect(formatKwota(100)).toBe('100.00');
  });
});

describe('DashboardHome bez danych z /status', () => {
  it('status = null pokazuje kreski, nie "undefined%" ani puste saldo', () => {
    const { container } = render(
      <DashboardHome user="jan" status={null} coupons={[]} calibration={null}
        isAdmin={false} onSeeAll={() => {}} />
    );
    expect(container.textContent).not.toMatch(/undefined|NaN/);
    expect(screen.getByText('Skuteczność (ROI)').parentElement).toHaveTextContent('—');
    expect(screen.getByText('Dostępny Balans').parentElement).toHaveTextContent('—');
  });

  it('status z danymi pokazuje ROI i saldo', () => {
    render(
      <DashboardHome user="jan" status={{ bankroll: 250, stats: { roi_pct: 4.5 } }}
        coupons={[]} calibration={null} isAdmin={false} onSeeAll={() => {}} />
    );
    expect(screen.getByText('+4.5%')).toBeInTheDocument();
    expect(screen.getByText('250.00')).toBeInTheDocument();
  });
});
