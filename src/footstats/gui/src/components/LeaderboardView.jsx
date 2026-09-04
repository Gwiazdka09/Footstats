import React, { useState, useEffect } from 'react';
import { Trophy } from 'lucide-react';
import { motion } from 'framer-motion';
import HistoryCouponRow from './HistoryCouponRow';

const SORT_OPTIONS = [
  { value: 'win_rate', label: 'Win rate' },
  { value: 'roi', label: 'ROI' },
  { value: 'profit', label: 'Zysk' },
];

const DAYS_OPTIONS = [
  { value: 0, label: 'Całość' },
  { value: 30, label: '30 dni' },
  { value: 7, label: '7 dni' },
];

// Zysk PLN (papierowy bankroll) ze znakiem: "+10.00" / "-8.00".
const formatSigned = (value) => `${value >= 0 ? '+' : ''}${(value ?? 0).toFixed(2)}`;

// "2 kupony" / "5 kuponów" — bez tego znacznik "mało danych" brzmi jak
// automat tłumaczony z angielskiego.
const odmianaKupony = (n) => {
  const setki = n % 100;
  if (setki >= 12 && setki <= 14) return 'kuponów';
  const dziesiatki = n % 10;
  return dziesiatki >= 2 && dziesiatki <= 4 ? 'kupony' : 'kuponów';
};

// Przycisk sortu/filtra: kolory inline (nie Tailwind-klasy) — index.css ma
// niewarstwowe `button { color: inherit; background: transparent }`, ktore bije
// warstwowe (@layer utilities) klasy Tailwind na <button> — patrz
// StatsView.jsx/HistoryCouponRow.jsx (ten sam wzorzec).
const ToggleButton = ({ active, label, onClick }) => (
  <button
    onClick={onClick}
    style={active
      ? {
          color: 'var(--accent-primary)',
          background: 'color-mix(in srgb, var(--accent-primary) 12%, transparent)',
        }
      : { color: 'var(--text-muted)', background: 'transparent' }}
    className="text-xs font-bold px-3 py-1.5 rounded-lg transition-colors"
  >
    {label}
  </button>
);

const LeaderboardView = ({ apiFetch }) => {
  const [leaders, setLeaders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState('win_rate');
  const [days, setDays] = useState(0);
  const [selected, setSelected] = useState(null);
  const [sharedCoupons, setSharedCoupons] = useState([]);
  const [loadingCoupons, setLoadingCoupons] = useState(false);
  const [pending, setPending] = useState([]);
  const [optIn, setOptIn] = useState(null);
  const [savingOptIn, setSavingOptIn] = useState(false);

  useEffect(() => {
    apiFetch('/leaderboard/pending').then(setPending).catch(() => setPending([]));
    apiFetch('/auth/me')
      .then(me => setOptIn(!!me.leaderboard_opt_in))
      .catch(() => setOptIn(null));
  }, []);

  const toggleOptIn = async () => {
    if (savingOptIn || optIn === null) return;
    setSavingOptIn(true);
    try {
      await apiFetch('/me/leaderboard', {
        method: 'PATCH',
        body: JSON.stringify({ shared: !optIn }),
      });
      setOptIn(v => !v);
      const dane = await apiFetch(`/leaderboard?sort=${sort}&days=${days}`);
      setLeaders(dane);
    } catch (err) {
      console.error('Błąd zmiany zgody na ranking:', err);
    } finally {
      setSavingOptIn(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    apiFetch(`/leaderboard?sort=${sort}&days=${days}`)
      .then(data => {
        setLeaders(data);
        setLoading(false);
      })
      .catch(() => {
        setLeaders([]);
        setLoading(false);
      });
  }, [sort, days]);

  const selectUser = async (username) => {
    setSelected(username);
    setLoadingCoupons(true);
    try {
      const data = await apiFetch(`/leaderboard/${encodeURIComponent(username)}/coupons`);
      setSharedCoupons(data);
    } catch {
      setSharedCoupons([]);
    } finally {
      setLoadingCoupons(false);
    }
  };

  if (loading) {
    return <div className="text-center py-20" style={{ color: 'var(--text-muted)' }}>Ładowanie rankingu...</div>;
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
    >
      <div className="mb-8">
        <h1 className="text-4xl font-bold mb-2 flex items-center gap-3">
          <Trophy size={20} style={{ color: 'var(--accent-primary)' }} /> Najlepsi typerzy
        </h1>
        <p style={{ color: 'var(--text-muted)' }}>
          Wynik liczy się ze <strong>wszystkich</strong> rozliczonych kuponów typera — nie tylko
          z tych, które pokazał. Kliknij typera, by zobaczyć jego udostępnione kupony.
        </p>
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
          Kwoty PLN to papierowy bankroll — nie są prawdziwymi pieniędzmi.
        </p>
      </div>

      {optIn !== null && (
        <div className="glass-card p-4 mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="font-bold text-sm">Chcę być na liście typerów</p>
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
              Wejście na listę pokazuje innym Twój wynik ze wszystkich rozliczonych kuponów,
              także tych nieudostępnionych. Same kupony pozostają widoczne tylko te,
              które sam udostępnisz.
            </p>
          </div>
          <button
            onClick={toggleOptIn}
            disabled={savingOptIn}
            className="text-xs font-bold px-4 py-2 rounded-lg transition-colors shrink-0"
            style={optIn
              ? { color: 'var(--accent-primary)',
                  background: 'color-mix(in srgb, var(--accent-primary) 12%, transparent)' }
              : { color: 'var(--text-muted)',
                  background: 'color-mix(in srgb, var(--text-muted) 10%, transparent)' }}
          >
            {optIn ? 'Jestem na liście' : 'Dołącz do listy'}
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-6 mb-8">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>
            Sortuj
          </span>
          <div className="flex gap-1">
            {SORT_OPTIONS.map(opt => (
              <ToggleButton key={opt.value} active={sort === opt.value} label={opt.label} onClick={() => setSort(opt.value)} />
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>
            Okres
          </span>
          <div className="flex gap-1">
            {DAYS_OPTIONS.map(opt => (
              <ToggleButton key={opt.value} active={days === opt.value} label={opt.label} onClick={() => setDays(opt.value)} />
            ))}
          </div>
        </div>
      </div>

      {leaders.length === 0 ? (
        <div className="glass-card text-center py-20 px-12 flex flex-col items-center gap-4" style={{ color: 'var(--text-muted)' }}>
          <Trophy size={40} />
          <p>Nikt nie jest jeszcze na liście.</p>
          <p className="text-xs max-w-md">
            Żeby się tu pojawić, trzeba dołączyć do listy powyżej i mieć co najmniej dwa
            rozliczone kupony. Nierozstrzygnięte nie liczą się do wyniku — czekają niżej.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 mb-10">
          {leaders.map((l, i) => {
            const roiColor = l.roi >= 0 ? 'var(--accent-primary)' : 'var(--accent-secondary)';
            const profitColor = l.profit_pln >= 0 ? 'var(--accent-primary)' : 'var(--accent-secondary)';
            return (
              <div
                key={l.user_id}
                onClick={() => selectUser(l.username)}
                className="glass-card p-6 flex flex-col md:flex-row items-center justify-between gap-6 cursor-pointer transition-colors"
                style={selected === l.username ? { border: '2px solid var(--accent-primary)' } : undefined}
              >
                <div className="flex items-center gap-4">
                  <div
                    className="w-10 h-10 rounded-full flex items-center justify-center font-bold"
                    style={{
                      background: 'color-mix(in srgb, var(--accent-primary) 10%, transparent)',
                      color: 'var(--accent-primary)',
                    }}
                  >
                    #{i + 1}
                  </div>
                  <div>
                    <p className="font-bold text-lg">{l.username}</p>
                    {l.malo_danych && (
                      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                        mało danych — {l.total} {odmianaKupony(l.total)}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-8 text-center">
                  <div>
                    <p className="text-xs uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Win rate</p>
                    <p className="font-bold">{l.win_rate}%</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>ROI</p>
                    <p className="font-bold" style={{ color: roiColor }}>{l.roi >= 0 ? '+' : ''}{l.roi}%</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Zysk</p>
                    <p className="font-bold" style={{ color: profitColor }}>{formatSigned(l.profit_pln)} PLN</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Kupony</p>
                    <p className="font-bold">{l.wins}/{l.total}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {pending.length > 0 && (
        <div className="mb-10">
          <h2 className="text-2xl font-bold mb-2">Świeżo udostępnione</h2>
          <p className="text-xs mb-6" style={{ color: 'var(--text-muted)' }}>
            Kupony czekające na rozstrzygnięcie. Do rankingu wejdą dopiero po rozliczeniu —
            wynik nierozstrzygnięty nie jest wynikiem.
          </p>
          <div className="grid grid-cols-1 gap-4">
            {pending.map(c => (
              <div key={c.id} className="glass-card p-4 flex items-center justify-between gap-4">
                <p className="font-bold">{c.username}</p>
                <div className="flex gap-6 text-sm text-right">
                  <div>
                    <p className="text-xs uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Kurs</p>
                    <p className="font-bold">{c.total_odds ? Number(c.total_odds).toFixed(2) : '—'}</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Stawka</p>
                    <p className="font-bold">{c.stake_pln ?? '—'} PLN</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {selected && (
        <div>
          <h2 className="text-2xl font-bold mb-6">Kupony: {selected}</h2>
          {loadingCoupons ? (
            <div className="text-center py-12" style={{ color: 'var(--text-muted)' }}>Ładowanie kuponów...</div>
          ) : sharedCoupons.length > 0 ? (
            <div className="grid grid-cols-1 gap-4">
              {sharedCoupons.map(c => (
                <HistoryCouponRow key={c.id} c={c} apiFetch={apiFetch} />
              ))}
            </div>
          ) : (
            <div className="text-center p-12 glass-card" style={{ color: 'var(--text-muted)' }}>
              Ten typer nie udostępnił żadnych kuponów.
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
};

export default LeaderboardView;
