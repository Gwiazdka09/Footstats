import React, { useState, useEffect } from 'react';
import { CalendarDays, Clock, Trophy, ChevronRight } from 'lucide-react';
import { motion } from 'framer-motion';

// "2026-09-20" -> "20.09" (kompaktowo, tabela ma byc czytelna na mobile).
const formatData = (iso) => {
  if (!iso || iso.length < 10) return '—';
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
};

// Odliczanie do startu ligi. Ujemne = sezon juz trwa.
const OpisStartu = ({ dni, rozegranych, total }) => {
  if (dni === null || dni === undefined) {
    return <span style={{ color: 'var(--text-muted)' }}>—</span>;
  }
  if (dni > 0) {
    return (
      <span style={{ color: 'var(--accent-primary)' }}>
        start za {dni} {dni === 1 ? 'dzień' : 'dni'}
      </span>
    );
  }
  const postep = total ? Math.round((rozegranych / total) * 100) : 0;
  return (
    <span style={{ color: 'var(--text-muted)' }}>
      w trakcie · {rozegranych}/{total} ({postep}%)
    </span>
  );
};

const MeczRow = ({ mecz }) => (
  <div className="flex items-center gap-3 py-2 text-sm">
    <span className="shrink-0 font-bold" style={{ color: 'var(--accent-primary)', minWidth: '3rem' }}>
      {formatData(mecz.data)}
    </span>
    <span className="shrink-0" style={{ color: 'var(--text-muted)', minWidth: '3rem' }}>
      {mecz.godzina || '—'}
    </span>
    <span className="min-w-0 truncate">
      {mecz.gospodarz} <span style={{ color: 'var(--text-muted)' }}>vs</span> {mecz.goscie}
    </span>
  </div>
);

const LigaCard = ({ liga, onWybierz }) => (
  <div className="glass-card p-6">
    <div className="flex items-start justify-between gap-4 mb-4">
      <div className="min-w-0">
        <h3 className="font-bold truncate">{liga.nazwa}</h3>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {liga.kraj} · sezon {liga.sezon}
        </p>
      </div>
      <button
        type="button"
        className="btn-see-all shrink-0 flex items-center gap-1"
        onClick={() => onWybierz(liga.kod)}
      >
        Wszystkie <ChevronRight size={16} />
      </button>
    </div>

    <div className="mb-4 text-sm">
      <OpisStartu
        dni={liga.dni_do_startu}
        rozegranych={liga.meczow_rozegranych}
        total={liga.meczow_total}
      />
    </div>

    {liga.nastepne && liga.nastepne.length > 0 ? (
      <div>{liga.nastepne.map((m, i) => <MeczRow key={i} mecz={m} />)}</div>
    ) : (
      <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
        Brak nadchodzących meczów w tym terminarzu.
      </p>
    )}
  </div>
);

const TerminarzView = ({ apiFetch }) => {
  const [ligi, setLigi] = useState([]);
  const [wybrana, setWybrana] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    apiFetch('/terminarz?limit_na_lige=3')
      .then((dane) => { setLigi(dane.ligi || []); setLoading(false); })
      .catch(() => {
        setError('Nie udało się pobrać terminarza — spróbuj ponownie później.');
        setLoading(false);
      });
  }, []);

  const pokazLige = (kod) => {
    setWybrana({ kod, loading: true, mecze: [] });
    apiFetch(`/terminarz/${kod}?tylko_nadchodzace=true&limit=100`)
      .then((dane) => setWybrana({ ...dane, loading: false }))
      .catch(() => setWybrana({ kod, loading: false, mecze: [], blad: true }));
  };

  if (loading) {
    return (
      <div className="text-center py-20" style={{ color: 'var(--text-muted)' }}>
        Ładowanie terminarza...
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-card p-6 text-center" style={{ color: 'var(--accent-secondary)' }}>
        {error}
      </div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="mb-12">
        <h1 className="text-4xl font-bold mb-2">Terminarz</h1>
        <p style={{ color: 'var(--text-muted)' }}>
          Kalendarz lig — kiedy startują i co nas czeka najbliżej.
        </p>
      </div>

      {ligi.length === 0 ? (
        <div
          className="glass-card text-center py-20 px-12 flex flex-col items-center gap-4"
          style={{ color: 'var(--text-muted)' }}
        >
          <CalendarDays size={40} />
          <p>Brak dostępnych terminarzy.</p>
        </div>
      ) : (
        <div className="grid gap-6" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))' }}>
          {ligi.map((liga) => (
            <LigaCard key={liga.kod} liga={liga} onWybierz={pokazLige} />
          ))}
        </div>
      )}

      {wybrana && (
        <div className="mt-12">
          <div className="flex items-center gap-2 mb-4">
            <Trophy size={20} style={{ color: 'var(--accent-primary)' }} />
            <h2 className="text-2xl font-bold">{wybrana.liga || wybrana.kod}</h2>
          </div>
          <div className="glass-card p-6">
            {wybrana.loading && (
              <p style={{ color: 'var(--text-muted)' }}>Ładowanie...</p>
            )}
            {!wybrana.loading && wybrana.blad && (
              <p style={{ color: 'var(--accent-secondary)' }}>
                Nie udało się pobrać terminarza tej ligi.
              </p>
            )}
            {!wybrana.loading && !wybrana.blad && wybrana.mecze.length === 0 && (
              <p style={{ color: 'var(--text-muted)' }}>Brak nadchodzących meczów.</p>
            )}
            {!wybrana.loading && wybrana.mecze.length > 0 && (
              <div>
                <div
                  className="flex items-center gap-2 mb-4 text-xs font-bold uppercase tracking-widest"
                  style={{ color: 'var(--text-muted)' }}
                >
                  <Clock size={16} />
                  <span>{wybrana.mecze.length} nadchodzących</span>
                </div>
                {wybrana.mecze.map((m, i) => <MeczRow key={i} mecz={m} />)}
              </div>
            )}
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default TerminarzView;
