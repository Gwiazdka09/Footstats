import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

// Odpowiednik `tests-no-prod.md` po stronie frontu: test NIE MA prawa dotknąć
// sieci. Domyślny `fetch` wybucha z czytelnym komunikatem, więc zapomniany mock
// od razu widać — zamiast cichego wisienia albo strzału w produkcyjne API.
beforeEach(() => {
  global.fetch = vi.fn(() => {
    throw new Error(
      'Test probowal uzyc fetch bez mocka. Zamockuj wywolanie albo uzyj vi.spyOn(global, "fetch").',
    );
  });
  localStorage.clear();
});

afterEach(() => {
  cleanup();
});

// jsdom nie implementuje `matchMedia`, a komponenty responsywne po nie sięgają.
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}
