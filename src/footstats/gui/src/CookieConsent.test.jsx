import React from 'react';
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import CookieConsent from './CookieConsent';

/**
 * Baner zgody. Do 17.08.2026 mowil nieprawde: twierdzil, ze uzywamy WYLACZNIE
 * plikow niezbednych, a `main.jsx` montowal przy tym analityke Vercela — ktora
 * ladowala sie zanim ktokolwiek dotknal przycisku. Analityka zostala usunieta,
 * wiec tresc jest teraz prawdziwa.
 *
 * Test `NIE montuje analityki` pilnuje, zeby nie wrocila po cichu razem z jakas
 * inna zmiana. Gdyby ktos swiadomie ja przywrocil, musi tez dorobic bramkowanie
 * zgoda i dopisac ja do polityki prywatnosci — i wtedy zaktualizowac ten test.
 */
describe('baner zgody', () => {
  it('pokazuje sie, gdy zgody jeszcze nie ma', () => {
    render(<CookieConsent />);
    expect(screen.getByText('Rozumiem')).toBeInTheDocument();
  });

  it('NIE pokazuje sie, gdy zgoda juz zapisana', () => {
    localStorage.setItem('fs_cookie_consent', 'accepted');
    render(<CookieConsent />);
    expect(screen.queryByText('Rozumiem')).not.toBeInTheDocument();
  });

  it('klikniecie zapisuje zgode i chowa baner', () => {
    render(<CookieConsent />);

    fireEvent.click(screen.getByText('Rozumiem'));

    expect(localStorage.getItem('fs_cookie_consent')).toBe('accepted');
    expect(screen.queryByText('Rozumiem')).not.toBeInTheDocument();
  });

  it('link do polityki jest wyliczany, nie zaszyty na sztywno', () => {
    render(<CookieConsent />);
    const link = screen.getByRole('link', { name: /polityce prywatności/i });
    // Zaszyty na sztywno adres Cloud Run umarlby po cichu po zmianie hostingu.
    expect(link.getAttribute('href')).not.toContain('949240532526');
    expect(link.getAttribute('href')).toMatch(/polityka-prywatnosci$/);
  });

  it('link otwiera sie bezpiecznie w nowej karcie', () => {
    render(<CookieConsent />);
    const link = screen.getByRole('link', { name: /polityce prywatności/i });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('rel')).toContain('noreferrer');
  });

  it('tresc mowi o plikach NIEZBEDNYCH — i to musi pozostac prawda', () => {
    render(<CookieConsent />);
    expect(screen.getByText(/niezbędnych plików cookie/i)).toBeInTheDocument();
  });
});

/**
 * F6 — baner zaslanial tresc na dole ekranu.
 *
 * Zmierzone 17.08 przy 390px w widoku rejestracji: link „Masz juz konto?
 * Zaloguj sie" chowal sie pod banerem. Baner jest `fixed bottom-0`, wiec nie
 * zajmuje miejsca w ukladzie — na mobile rozwija sie do dwoch wierszy i przykrywa
 * to, co jest najnizej.
 *
 * Naprawa jest celowo GLOBALNA, a nie lokalna dla ekranu rejestracji: baner
 * wisi nad KAZDYM widokiem, wiec dokladanie marginesu w jednym komponencie
 * zalatwialoby jeden ekran i zostawialo reszte. Rezerwujemy miejsce na dole
 * strony na tyle, ile baner realnie zajmuje, i oddajemy je po zamknieciu.
 */
describe('baner nie zaslania tresci', () => {
  it('rezerwuje miejsce na dole strony, dopoki wisi', () => {
    render(<CookieConsent />);
    expect(document.body.style.paddingBottom).not.toBe('');
  });

  it('oddaje miejsce po zamknieciu', () => {
    render(<CookieConsent />);

    fireEvent.click(screen.getByText('Rozumiem'));

    expect(document.body.style.paddingBottom).toBe('');
  });

  it('nie rezerwuje miejsca, gdy zgoda juz jest', () => {
    localStorage.setItem('fs_cookie_consent', 'accepted');
    render(<CookieConsent />);
    expect(document.body.style.paddingBottom).toBe('');
  });

  it('sprzata po odmontowaniu', () => {
    const { unmount } = render(<CookieConsent />);

    unmount();

    expect(document.body.style.paddingBottom).toBe('');
  });
});
