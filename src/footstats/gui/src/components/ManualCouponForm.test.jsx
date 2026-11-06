import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ManualCouponForm from './ManualCouponForm';

/**
 * Formularz dziennika: pola musza miec dostepna nazwe (czytnik ekranu), a data
 * meczu jest wymagana — kupon bez daty nigdy sie nie rozliczy ani nie zaalarmuje.
 */

const wyrenderuj = () => {
  const apiFetch = vi.fn((sciezka) => (
    sciezka === '/coupon/markets'
      ? Promise.resolve([{ grupa: '1X2', wartosc: '1', etykieta: 'Gospodarz wygra' }])
      : Promise.resolve({ ok: true })
  ));
  const onSaved = vi.fn();
  render(<ManualCouponForm apiFetch={apiFetch} onClose={vi.fn()} onSaved={onSaved} />);
  return { apiFetch, onSaved };
};

const wypelnijNoge = async () => {
  await screen.findByText('Gospodarz wygra', { selector: 'option' });
  fireEvent.change(screen.getByLabelText('Gospodarz'), { target: { value: 'Legia' } });
  fireEvent.change(screen.getByLabelText('Gość'), { target: { value: 'Lech' } });
  fireEvent.change(screen.getByLabelText('Typ'), { target: { value: '1' } });
  fireEvent.change(screen.getByLabelText('Kurs'), { target: { value: '1.85' } });
  fireEvent.change(screen.getByLabelText(/Stawka/), { target: { value: '10' } });
};

const wyslaneKupony = (apiFetch) => apiFetch.mock.calls.filter(([s]) => s === '/coupon/manual');

describe('etykiety pol', () => {
  it('kazde pole ma dostepna nazwe', () => {
    wyrenderuj();
    for (const nazwa of ['Gospodarz', 'Gość', 'Typ', 'Kurs']) {
      expect(screen.getByLabelText(nazwa)).toBeInTheDocument();
    }
    expect(screen.getByLabelText(/Stawka/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Bukmacher/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Data meczu/)).toBeInTheDocument();
  });

  it('kolejna noga ma wlasny zestaw nazwanych pol', () => {
    wyrenderuj();
    fireEvent.click(screen.getByText('Dodaj nogę'));
    expect(screen.getAllByLabelText('Gospodarz')).toHaveLength(2);
    expect(screen.getAllByLabelText('Kurs')).toHaveLength(2);
  });
});

describe('data meczu wymagana', () => {
  it('brak daty blokuje wysylke i pokazuje komunikat', async () => {
    const { apiFetch, onSaved } = wyrenderuj();
    await wypelnijNoge();
    fireEvent.click(screen.getByText('Zapisz kupon'));

    expect(await screen.findByText(/Podaj datę meczu/)).toBeInTheDocument();
    expect(wyslaneKupony(apiFetch)).toHaveLength(0);
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('z data kupon jest wysylany z match_date', async () => {
    const { apiFetch, onSaved } = wyrenderuj();
    await wypelnijNoge();
    fireEvent.change(screen.getByLabelText(/Data meczu/), { target: { value: '2026-11-08' } });
    fireEvent.click(screen.getByText('Zapisz kupon'));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [, opcje] = wyslaneKupony(apiFetch)[0];
    expect(JSON.parse(opcje.body).match_date).toBe('2026-11-08');
  });
});
