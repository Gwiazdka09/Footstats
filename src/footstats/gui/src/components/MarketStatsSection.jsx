import React from 'react';
import { Layers } from 'lucide-react';

const BRAK = '—';
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const pct = (fraction) => (isNum(fraction) ? `${(fraction * 100).toFixed(0)}%` : BRAK);
// Różnica w punktach procentowych ze znakiem: "+5.2 pp" / "-3.0 pp".
const diffPp = (v) => (isNum(v) ? `${v >= 0 ? '+' : ''}${v.toFixed(1)} pp` : BRAK);

const MarketRow = ({ stat }) => (
  <div className="py-3" data-testid="market-row">
    <div className="flex justify-between items-center gap-2">
      <span className="font-bold">{stat.market}</span>
      <span className="metric-num font-bold">{stat.wins}/{stat.n}</span>
    </div>
    <div
      className="flex flex-wrap justify-between gap-x-4 text-sm mt-1"
      style={{ color: 'var(--text-muted)' }}
    >
      <span>trafność {pct(stat.hit_rate)}</span>
      <span>kurs implikuje {pct(stat.implied_prob)}</span>
      <span>różnica {diffPp(stat.edge_pp)}</span>
    </div>
    {stat.n_za_male && (
      <span className="text-xs" style={{ color: 'var(--accent-secondary)' }}>
        mała próba (n&lt;20)
      </span>
    )}
    {Array.isArray(stat.skladniki) && stat.skladniki.length > 0 && (
      <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
        człony: {stat.skladniki.join(', ')}
      </p>
    )}
  </div>
);

const MarketStatsSection = ({ stats }) => {
  const lista = Array.isArray(stats) ? stats : [];
  return (
    <div className="glass-card p-6">
      <div className="flex items-center gap-2 mb-4" style={{ color: 'var(--text-muted)' }}>
        <Layers size={16} />
        <span className="text-xs font-bold uppercase tracking-widest">Twoje typy wg rodzaju</span>
      </div>
      {lista.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>
          Brak rozliczonych nóg — pojawią się po pierwszych rozliczeniach
        </p>
      ) : (
        <>
          {lista.map((stat) => <MarketRow key={stat.market} stat={stat} />)}
          <p className="text-xs mt-3" style={{ color: 'var(--text-muted)' }}>
            Pomiar Twoich rozliczonych nóg, nie prognoza. Liczą się tylko nogi z ustalonym wynikiem.
          </p>
        </>
      )}
    </div>
  );
};

export default MarketStatsSection;
