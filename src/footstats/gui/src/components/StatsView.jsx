import React, { useState, useEffect } from 'react';
import { BarChart3, TrendingUp, Wallet, Flame, Trophy, ClipboardList } from 'lucide-react';
import { motion } from 'framer-motion';

// Ulamek 0-1 (win_rate/roi z backendu) -> "66.7%".
const formatPct = (fraction) => `${(fraction * 100).toFixed(1)}%`;

// Zysk PLN (papierowy bankroll) ze znakiem: "+10.00" / "-8.00".
const formatSigned = (value) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}`;

const StreakBadge = ({ streak }) => {
  if (streak === 0) {
    return <span style={{ color: 'var(--text-muted)' }}>—</span>;
  }
  const won = streak > 0;
  return (
    <span style={{ color: won ? 'var(--accent-primary)' : 'var(--accent-secondary)' }}>
      {won ? `W${streak}` : `L${Math.abs(streak)}`}
    </span>
  );
};

const CouponResultRow = ({ label, result }) => (
  <div className="flex justify-between items-center py-2">
    <span className="text-sm" style={{ color: 'var(--text-muted)' }}>{label}</span>
    {result ? (
      <span
        className="font-bold"
        style={{ color: result.profit_units >= 0 ? 'var(--accent-primary)' : 'var(--accent-secondary)' }}
      >
        Kupon #{result.coupon_id}: {formatSigned(result.profit_units)} PLN
      </span>
    ) : (
      <span style={{ color: 'var(--text-muted)' }}>Brak</span>
    )}
  </div>
);

const MetricTile = ({ icon, label, value, valueColor }) => (
  <div className="glass-card p-6">
    <div className="flex items-center gap-2 mb-3" style={{ color: 'var(--text-muted)' }}>
      {icon}
      <span className="text-xs font-bold uppercase tracking-widest">{label}</span>
    </div>
    <p className="metric-num text-3xl font-bold" style={valueColor ? { color: valueColor } : undefined}>
      {value}
    </p>
  </div>
);

const StatsView = ({ apiFetch }) => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    apiFetch('/stats/me')
      .then((data) => { setStats(data); setLoading(false); })
      .catch(() => {
        // Zawsze komunikat PL — niezaleznie od tresci bledu (503 Dane niedostepne / blad sieci).
        setError('Nie udało się pobrać statystyk — spróbuj ponownie później.');
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <div className="text-center py-20" style={{ color: 'var(--text-muted)' }}>Ładowanie statystyk...</div>;
  }

  if (error) {
    return (
      <div className="glass-card p-6 text-center" style={{ color: 'var(--accent-secondary)' }}>
        {error}
      </div>
    );
  }

  if (!stats || stats.settled_count === 0) {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <div className="mb-12">
          <h1 className="text-4xl font-bold mb-2">Statystyki</h1>
          <p style={{ color: 'var(--text-muted)' }}>Twoje statystyki liczone z rozliczonych kuponów.</p>
        </div>
        <div
          className="glass-card text-center py-20 px-12 flex flex-col items-center gap-4"
          style={{ color: 'var(--text-muted)' }}
        >
          <ClipboardList size={40} />
          <p>Brak rozliczonych kuponów — dodaj i rozlicz pierwszy.</p>
        </div>
      </motion.div>
    );
  }

  const roiColor = stats.roi >= 0 ? 'var(--accent-primary)' : 'var(--accent-secondary)';
  const profitColor = stats.profit_units >= 0 ? 'var(--accent-primary)' : 'var(--accent-secondary)';

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
    >
      <div className="mb-12">
        <h1 className="text-4xl font-bold mb-2">Statystyki</h1>
        <p style={{ color: 'var(--text-muted)' }}>
          {stats.settled_count}/{stats.total_coupons} rozliczonych kuponów.
        </p>
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
          Kwoty PLN to papierowy bankroll — nie są prawdziwymi pieniędzmi.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10">
        <MetricTile
          icon={<BarChart3 size={16} />}
          label="Win rate"
          value={<span className="stat-gradient">{formatPct(stats.win_rate)}</span>}
        />
        <MetricTile
          icon={<TrendingUp size={16} />}
          label="ROI"
          value={formatPct(stats.roi)}
          valueColor={roiColor}
        />
        <MetricTile
          icon={<Wallet size={16} />}
          label="Zysk"
          value={`${formatSigned(stats.profit_units)} PLN`}
          valueColor={profitColor}
        />
        <MetricTile
          icon={<Flame size={16} />}
          label="Seria"
          value={<StreakBadge streak={stats.current_streak} />}
        />
      </div>

      <div className="glass-card p-6">
        <div className="flex items-center gap-2 mb-4" style={{ color: 'var(--text-muted)' }}>
          <Trophy size={16} />
          <span className="text-xs font-bold uppercase tracking-widest">Rekordy</span>
        </div>
        <CouponResultRow label="Najlepszy kupon" result={stats.best_coupon} />
        <CouponResultRow label="Najgorszy kupon" result={stats.worst_coupon} />
      </div>
    </motion.div>
  );
};

export default StatsView;
