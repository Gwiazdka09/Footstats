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
          Ranking typerów na udostępnionych kuponach. Kliknij typera, by zobaczyć jego kupony.
        </p>
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
          Kwoty PLN to papierowy bankroll — nie są prawdziwymi pieniędzmi.
        </p>
      </div>

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
          <p>Brak danych — nikt jeszcze nie udostępnił kuponów.</p>
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
                  <p className="font-bold text-lg">{l.username}</p>
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
