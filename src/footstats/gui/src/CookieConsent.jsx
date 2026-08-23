import React, { useEffect, useRef, useState } from 'react';
import { legalUrl } from './lib/api';

const STORAGE_KEY = 'fs_cookie_consent';

const CookieConsent = () => {
  const [visible, setVisible] = useState(() => !localStorage.getItem(STORAGE_KEY));
  const banerRef = useRef(null);

  // F6: baner jest `fixed`, wiec NIE zajmuje miejsca w ukladzie — na 390px
  // rozwija sie do dwoch wierszy i przykrywa to, co jest najnizej (zmierzone
  // 17.08: link „Masz juz konto? Zaloguj sie" w widoku rejestracji).
  //
  // Rezerwujemy miejsce na dole strony, tyle ile baner realnie zajmuje, i oddajemy
  // je po zamknieciu. Celowo GLOBALNIE, a nie marginesem w widoku rejestracji:
  // baner wisi nad KAZDYM ekranem, wiec lokalna latka zalatwilaby jeden i zostawila
  // reszte. Wysokosc mierzymy, bo zalezy od szerokosci ekranu i dlugosci tekstu.
  useEffect(() => {
    if (!visible) return undefined;
    const el = banerRef.current;
    if (!el) return undefined;

    const ustawMiejsce = () => {
      document.body.style.paddingBottom = `${el.offsetHeight}px`;
    };
    ustawMiejsce();

    // ResizeObserver nie istnieje w jsdom (testy) ani w starszych przegladarkach —
    // wtedy zostaje sam nasluch `resize`, ktory lapie obrot ekranu.
    const obserwator =
      typeof ResizeObserver !== 'undefined' ? new ResizeObserver(ustawMiejsce) : null;
    if (obserwator) obserwator.observe(el);
    window.addEventListener('resize', ustawMiejsce);

    return () => {
      if (obserwator) obserwator.disconnect();
      window.removeEventListener('resize', ustawMiejsce);
      document.body.style.paddingBottom = '';
    };
  }, [visible]);

  if (!visible) return null;

  const accept = () => {
    localStorage.setItem(STORAGE_KEY, 'accepted');
    setVisible(false);
  };

  return (
    <div ref={banerRef} className="fixed bottom-0 left-0 right-0 z-[400] p-4 flex justify-center">
      <div className="glass-card w-full max-w-3xl p-4 sm:p-5 flex flex-col sm:flex-row items-center gap-4">
        <p className="text-sm text-[var(--text-muted)] flex-1">
          Używamy niezbędnych plików cookie / local storage (np. token sesji), aby aplikacja działała.
          Szczegóły w{' '}
          <a href={legalUrl('polityka-prywatnosci')} target="_blank" rel="noreferrer" className="text-[var(--accent-primary)] hover:underline">
            polityce prywatności
          </a>.
        </p>
        <button onClick={accept} className="btn-primary shrink-0">
          Rozumiem
        </button>
      </div>
    </div>
  );
};

export default CookieConsent;
