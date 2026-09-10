import React, { useState } from 'react';
import BirthMonthYear, { birthYm } from './BirthMonthYear';

// Prośba o miesiąc/rok urodzenia dla kont założonych przed 10.09.2026.
// „Później” zamyka ją tylko do następnego logowania — decyzja usera: pytamy
// przy każdym logowaniu, dopóki nie wpisze.
const BirthPrompt = ({ apiFetch, onDone, onLater }) => {
  const [month, setMonth] = useState('');
  const [year, setYear] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await apiFetch('/auth/birth', {
        method: 'POST',
        body: JSON.stringify({ birth_ym: birthYm(month, year) }),
      });
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      // z-[400]: index.css daje .sidebar 100, mobile-topbar 200, toast 250,
      // mobile-nav-overlay 300 — przy niższej wartości sidebar zostawał nad nakładką.
      className="fixed inset-0 z-[400] flex items-center justify-center px-4"
      style={{ background: 'color-mix(in srgb, var(--bg-darker) 80%, transparent)' }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="prosba-wiek-tytul"
    >
      <form onSubmit={save} className="glass-card p-8 w-full max-w-md space-y-6">
        <div>
          <h2 id="prosba-wiek-tytul" className="text-2xl font-bold mb-2">Potwierdź wiek</h2>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            FootStats jest tylko dla osób pełnoletnich. Podaj miesiąc i rok urodzenia —
            zapytamy o to przy każdym logowaniu, dopóki go nie uzupełnisz.
          </p>
        </div>
        <BirthMonthYear month={month} year={year} onMonth={setMonth} onYear={setYear} idPrefix="prosba" />
        {error && <p className="text-sm" style={{ color: 'var(--accent-secondary)' }}>{error}</p>}
        <div className="flex flex-wrap justify-end gap-3">
          <button
            type="button"
            onClick={onLater}
            className="px-4 py-2 rounded-lg text-sm font-bold"
            style={{ color: 'var(--text-muted)', background: 'color-mix(in srgb, var(--text-muted) 10%, transparent)' }}
          >
            Później
          </button>
          <button type="submit" disabled={saving} className="btn-primary px-6 py-2 text-sm disabled:opacity-50">
            {saving ? 'Zapisywanie...' : 'Zapisz'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default BirthPrompt;
