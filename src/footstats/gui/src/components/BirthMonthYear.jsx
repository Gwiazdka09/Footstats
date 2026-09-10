import React from 'react';

// Miesiąc + rok urodzenia (bez dnia — minimalizacja danych). Wspólne dla
// rejestracji i prośby o uzupełnienie wieku, żeby oba miejsca wysyłały ten
// sam format 'RRRR-MM', który sprawdza backend (`walidacja_konta`).
const MIESIACE = ['Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec', 'Lipiec',
  'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień'];

const ROK_TERAZ = new Date().getFullYear();
// Od najmłodszego dopuszczalnego rocznika w dół; reszta granicy (miesiąc) po stronie API.
const LATA = Array.from({ length: ROK_TERAZ - 18 - 1920 + 1 }, (_, i) => ROK_TERAZ - 18 - i);

export const birthYm = (month, year) =>
  (month && year ? `${year}-${String(month).padStart(2, '0')}` : '');

const selectClass = 'w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:outline-none focus:border-indigo-500 transition-colors';

const BirthMonthYear = ({ month, year, onMonth, onYear, idPrefix = 'urodzenie' }) => (
  <div>
    <span className="block text-xs font-bold text-slate-500 uppercase mb-2">Miesiąc i rok urodzenia</span>
    <div className="grid grid-cols-2 gap-3">
      <select
        id={`${idPrefix}-miesiac`}
        aria-label="Miesiąc urodzenia"
        value={month}
        onChange={(e) => onMonth(e.target.value)}
        className={selectClass}
        style={{ colorScheme: 'dark' }}
        required
      >
        <option value="">Miesiąc</option>
        {MIESIACE.map((nazwa, i) => <option key={nazwa} value={i + 1}>{nazwa}</option>)}
      </select>
      <select
        id={`${idPrefix}-rok`}
        aria-label="Rok urodzenia"
        value={year}
        onChange={(e) => onYear(e.target.value)}
        className={selectClass}
        style={{ colorScheme: 'dark' }}
        required
      >
        <option value="">Rok</option>
        {LATA.map(r => <option key={r} value={r}>{r}</option>)}
      </select>
    </div>
    <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
      Serwis tylko dla osób, które ukończyły 18 lat. Dnia urodzenia nie zbieramy.
    </p>
  </div>
);

export default BirthMonthYear;
