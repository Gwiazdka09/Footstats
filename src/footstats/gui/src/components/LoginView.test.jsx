import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import LoginView from './LoginView';

/**
 * Dostepnosc formularza logowania (F2 z audytu 17.08).
 *
 * Etykiety `<label>` byly w kodzie, ale NIE POWIAZANE z polami — bez `htmlFor`/`id`
 * i bez zagniezdzenia inputa w labelu. Wizualnie wygladalo poprawnie, natomiast
 * czytnik ekranu odczytywal wylacznie `placeholder`, ktory znika po pierwszym
 * znaku. Klikniecie w etykiete tez nie ustawialo fokusu.
 *
 * `getByLabelText` pyta drzewo dostepnosci dokladnie tak, jak zrobilby to czytnik,
 * wiec ten test przechodzi tylko przy REALNYM powiazaniu — nie da sie go oszukac
 * samym dopisaniem tekstu obok pola.
 */
const wyrenderuj = () =>
  render(<LoginView setToken={vi.fn()} setUser={vi.fn()} />);

describe('formularz logowania — dostepnosc', () => {
  it('pole loginu ma etykiete powiazana z polem', () => {
    wyrenderuj();
    expect(screen.getByLabelText(/login lub e-mail/i)).toHaveAttribute('type', 'text');
  });

  it('pole hasla ma etykiete powiazana z polem', () => {
    wyrenderuj();
    expect(screen.getByLabelText(/^hasło$/i)).toHaveAttribute('type', 'password');
  });

  it('przycisk wyslania ma czytelna nazwe', () => {
    wyrenderuj();
    expect(screen.getByRole('button', { name: /zaloguj się/i })).toBeInTheDocument();
  });

  it('formularz da sie obsluzyc z klawiatury — pola sa polami formularza', () => {
    wyrenderuj();
    const login = screen.getByLabelText(/login lub e-mail/i);
    const haslo = screen.getByLabelText(/^hasło$/i);
    expect(login.tagName).toBe('INPUT');
    expect(haslo.tagName).toBe('INPUT');
    expect(login).toBeRequired();
    expect(haslo).toBeRequired();
  });

  it('kazde pole ma WLASNY identyfikator', () => {
    // Zduplikowane `id` laczy etykiete z niewlasciwym polem — czytnik odczyta
    // wtedy zla nazwe, a klikniecie w etykiete ustawi fokus w cudzym polu.
    wyrenderuj();
    const idki = [...document.querySelectorAll('input[id]')].map((e) => e.id);
    expect(new Set(idki).size).toBe(idki.length);
  });
});
