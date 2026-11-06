import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import HistoryCouponRow from './HistoryCouponRow';

/**
 * Wiersz historii kuponu — jedyne miejsce w GUI, gdzie uzytkownik RECZNIE
 * rozlicza kupon z dziennika. Regula biznesowa (J4): recznie wolno oznaczyc
 * WYLACZNIE kupon `manual`, bo kupony AI rozlicza automat. Backend ma na to
 * strażnika (`set_coupon_result` zwraca 400 dla nie-manual) — front musi go
 * odzwierciedlac, inaczej user widzi przyciski, ktore zawsze koncza sie bledem.
 */

const kupon = (nadpisz = {}) => ({
  id: 149,
  phase: 'dziennik',
  status: 'ACTIVE',
  kupon_type: 'manual',
  created_at: '2026-08-15T10:00:00Z',
  total_odds: 1.35,
  stake_pln: 2,
  payout_pln: null,
  shared: false,
  legs: [],
  ...nadpisz,
});

const wyrenderuj = (nadpisz = {}, apiFetch = vi.fn().mockResolvedValue({})) => {
  const onRefresh = vi.fn();
  render(<HistoryCouponRow c={kupon(nadpisz)} apiFetch={apiFetch} onRefresh={onRefresh} />);
  return { apiFetch, onRefresh };
};

describe('przyciski rozliczenia', () => {
  it('widoczne dla aktywnego kuponu z dziennika', () => {
    wyrenderuj();
    expect(screen.getByText('WYGRANY')).toBeInTheDocument();
    expect(screen.getByText('PRZEGRANY')).toBeInTheDocument();
    expect(screen.getByText('ANULOWANY')).toBeInTheDocument();
  });

  it('UKRYTE dla kuponu AI — te rozlicza automat', () => {
    wyrenderuj({ kupon_type: 'accumulator' });
    expect(screen.queryByText('WYGRANY')).not.toBeInTheDocument();
  });

  it('UKRYTE dla kuponu juz rozliczonego', () => {
    wyrenderuj({ status: 'WON' });
    expect(screen.queryByText('WYGRANY')).not.toBeInTheDocument();
  });

  it('wysyla wynik pod wlasciwy endpoint', async () => {
    const { apiFetch } = wyrenderuj();
    fireEvent.click(screen.getByText('WYGRANY'));

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    const [sciezka, opcje] = apiFetch.mock.calls[0];
    expect(sciezka).toBe('/coupon/149/result');
    expect(opcje.method).toBe('PATCH');
    expect(JSON.parse(opcje.body)).toEqual({ result: 'WON' });
  });

  it('kazdy przycisk wysyla SWOJ wynik', async () => {
    const { apiFetch } = wyrenderuj();
    fireEvent.click(screen.getByText('ANULOWANY'));
    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({ result: 'VOID' });
  });

  it('odswieza liste po udanym rozliczeniu', async () => {
    const { onRefresh } = wyrenderuj();
    fireEvent.click(screen.getByText('PRZEGRANY'));
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });

  it('blad z API trafia na ekran, a nie do kosza', async () => {
    const apiFetch = vi.fn().mockRejectedValue(new Error('Kupon juz rozliczony'));
    wyrenderuj({}, apiFetch);

    fireEvent.click(screen.getByText('WYGRANY'));

    expect(await screen.findByText('Kupon juz rozliczony')).toBeInTheDocument();
  });

  it('nie odswieza listy gdy rozliczenie padlo', async () => {
    const apiFetch = vi.fn().mockRejectedValue(new Error('bum'));
    const { onRefresh } = wyrenderuj({}, apiFetch);

    fireEvent.click(screen.getByText('WYGRANY'));

    await screen.findByText('bum');
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('podwojne klikniecie NIE wysyla dwoch rozliczen', async () => {
    // CAS-guard na backendzie zwrocilby 409, ale user zobaczylby blad przy
    // poprawnej akcji. Blokada `settling` ma to zatrzymac po stronie frontu.
    let odblokuj;
    const apiFetch = vi.fn(() => new Promise((res) => { odblokuj = res; }));
    const { onRefresh } = wyrenderuj({}, apiFetch);

    const przycisk = screen.getByText('WYGRANY');
    fireEvent.click(przycisk);
    fireEvent.click(przycisk);

    expect(apiFetch).toHaveBeenCalledTimes(1);

    // Domykamy obietnice w `act`, zeby React zdazyl przetworzyc `setSettling(false)`
    // przed koncem testu — inaczej leci ostrzezenie o aktualizacji poza `act(...)`.
    await act(async () => { odblokuj({}); });
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});

describe('licznik nog', () => {
  const nogi = [
    { home: 'Legia', away: 'Wisła', tip: '1', odds: 1.8, leg_won: true },
    { home: 'Lech', away: 'Pogoń', tip: 'X', odds: 3.2, leg_won: false },
    { home: 'Raków', away: 'Śląsk', tip: 'BTTS', odds: 1.7, leg_won: null },
  ];

  it('liczy trafione, chybione i oczekujace osobno', () => {
    wyrenderuj({ legs: nogi });
    expect(screen.getByText('1✓')).toBeInTheDocument();
    expect(screen.getByText('1✗')).toBeInTheDocument();
    expect(screen.getByText('1⏳')).toBeInTheDocument();
  });

  it('noga bez wyniku liczy sie jako oczekujaca, nie jako chybiona', () => {
    wyrenderuj({ legs: [{ home: 'A', away: 'B', tip: '1', odds: 2, leg_won: null }] });
    expect(screen.getByText('0✗')).toBeInTheDocument();
    expect(screen.getByText('1⏳')).toBeInTheDocument();
  });

  it('rozwija szczegoly nog po klinieciu', () => {
    wyrenderuj({ legs: nogi });
    expect(screen.queryByText(/Legia/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(/Kupon #149/));

    expect(screen.getByText(/Legia/)).toBeInTheDocument();
  });

  it('kupon bez nog nie rozwija sie w pusty panel', () => {
    wyrenderuj({ legs: [] });
    fireEvent.click(screen.getByText(/Kupon #149/));
    expect(screen.queryByText(/Typ:/)).not.toBeInTheDocument();
  });

  it('kupon reczny: licznik i rozwiniecie czytaja result oraz leg_won z backendu', () => {
    wyrenderuj({
      status: 'LOST',
      legs: [
        { home: 'Legia', away: 'Wisła', tip: '1', odds: 1.8, result: '2:0', leg_won: true },
        { home: 'Lech', away: 'Pogoń', tip: 'X', odds: 3.2, result: '1:0', leg_won: false },
      ],
    });
    expect(screen.getByText('1✓')).toBeInTheDocument();
    expect(screen.getByText('1✗')).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Kupon #149/));
    expect(screen.getByText('2:0')).toBeInTheDocument();
    expect(screen.getByText('1:0')).toBeInTheDocument();
  });
});

describe('wyplata z buka (kupon reczny)', () => {
  const pole = () => screen.getByLabelText(/Wypłata z buka/);

  it('puste pole = backend liczy sam (brak payout_pln w body)', async () => {
    const { apiFetch } = wyrenderuj();
    fireEvent.click(screen.getByText('WYGRANY'));
    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({ result: 'WON' });
  });

  it('wpisana kwota idzie jako payout_pln przy WYGRANY', async () => {
    const { apiFetch } = wyrenderuj();
    fireEvent.change(pole(), { target: { value: '123,45' } });
    fireEvent.click(screen.getByText('WYGRANY'));

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    const [sciezka, opcje] = apiFetch.mock.calls[0];
    expect(sciezka).toBe('/coupon/149/result');
    expect(JSON.parse(opcje.body)).toEqual({ result: 'WON', payout_pln: 123.45 });
  });

  it('kwota NIE jest wysylana przy PRZEGRANY (backend odrzuca ja z 400)', async () => {
    const { apiFetch } = wyrenderuj();
    fireEvent.change(pole(), { target: { value: '50' } });
    fireEvent.click(screen.getByText('PRZEGRANY'));

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({ result: 'LOST' });
  });

  it('zla kwota blokuje wysylke i pokazuje komunikat', () => {
    const { apiFetch } = wyrenderuj();
    fireEvent.change(pole(), { target: { value: 'abc' } });
    fireEvent.click(screen.getByText('WYGRANY'));

    expect(apiFetch).not.toHaveBeenCalled();
    expect(screen.getByText(/Wypłata musi być liczbą/)).toBeInTheDocument();
  });

  it('rozliczony WON pozwala skorygowac sama wyplate', async () => {
    const { apiFetch } = wyrenderuj({ status: 'WON', payout_pln: 10 });
    fireEvent.change(pole(), { target: { value: '99' } });
    fireEvent.click(screen.getByText('ZAPISZ WYPŁATĘ'));

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    const [sciezka, opcje] = apiFetch.mock.calls[0];
    expect(sciezka).toBe('/coupon/149/result');
    expect(JSON.parse(opcje.body)).toEqual({ result: 'WON', payout_pln: 99 });
  });

  it('korekta wymaga kwoty — pusta nic nie wysyla', () => {
    const { apiFetch } = wyrenderuj({ status: 'WON', payout_pln: 10 });
    fireEvent.click(screen.getByText('ZAPISZ WYPŁATĘ'));
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('korekty nie ma dla kuponu AI', () => {
    wyrenderuj({ status: 'WON', kupon_type: 'accumulator' });
    expect(screen.queryByText('ZAPISZ WYPŁATĘ')).not.toBeInTheDocument();
  });
});

describe('ikona statusu', () => {
  it('ANULOWANY ma wlasna ikone, inna niz zegar kuponu aktywnego', () => {
    const { container: aktywny } = render(
      <HistoryCouponRow c={kupon({ status: 'ACTIVE' })} apiFetch={vi.fn()} />,
    );
    const { container: anulowany } = render(
      <HistoryCouponRow c={kupon({ status: 'VOID' })} apiFetch={vi.fn()} />,
    );
    expect(aktywny.querySelector('svg.lucide-clock')).not.toBeNull();
    expect(aktywny.querySelector('svg.lucide-ban')).toBeNull();
    expect(anulowany.querySelector('svg.lucide-ban')).not.toBeNull();
    expect(anulowany.querySelector('svg.lucide-clock')).toBeNull();
  });
});

describe('format daty', () => {
  it('pokazuje czas warszawski w polskim formacie', () => {
    wyrenderuj({ created_at: '2026-08-15T10:00:00Z' });
    expect(screen.getByText('15.08.2026, 12:00:00')).toBeInTheDocument();
  });
});
