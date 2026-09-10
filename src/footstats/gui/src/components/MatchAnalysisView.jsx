import { useState, useEffect } from 'react';
import { Swords, Shield, Target } from 'lucide-react';

// 10.09: sama statystyka drużyn — bez paska 1X2, Over/BTTS i „Analizy AI”
// (nasze typy nie pokazują się w GUI poza kreatorem „Stwórz Kupon”).

function TeamCol({ stats, align }) {
  return (
    <div className={align === 'right' ? 'text-right' : ''}>
      <div className="font-semibold" style={{ color: 'var(--text-main)' }}>{stats.team}</div>
      <div className="flex gap-3 mt-1 text-sm" style={{ color: 'var(--text-muted)',
        justifyContent: align === 'right' ? 'flex-end' : 'flex-start' }}>
        <span className="inline-flex items-center gap-1"><Target size={16} />{stats.gf_pg ?? '—'}</span>
        <span className="inline-flex items-center gap-1"><Shield size={16} />{stats.ga_pg ?? '—'}</span>
      </div>
      {stats.rating != null && (
        <div className="text-xs mt-1" style={{ color: 'var(--accent-primary)' }}>
          rating {Number(stats.rating).toFixed(2)}
        </div>
      )}
    </div>
  );
}

function TopScorers({ list, align }) {
  if (!list?.length) return null;
  return (
    <div className={`text-xs mt-2 ${align === 'right' ? 'text-right' : ''}`}
      style={{ color: 'var(--text-muted)' }}>
      <span style={{ color: 'var(--accent-primary)' }}>⚽ </span>
      {list.map(s => `${s.name} ${Math.round(s.goal_share * 100)}%`).join(' · ')}
    </div>
  );
}

function Injuries({ list, align }) {
  if (!list?.length) return null;
  return (
    <ul className={`text-xs mt-2 space-y-0.5 ${align === 'right' ? 'text-right' : ''}`}
      style={{ color: 'var(--text-muted)' }}>
      {list.map((i, k) => (
        <li key={k}>
          <span style={{ color: i.goal_share >= 0.15 ? 'var(--accent-secondary)' : 'var(--text-muted)' }}>
            {i.name}{i.goal_share ? ` · ${Math.round(i.goal_share * 100)}% goli` : ''}
          </span>
        </li>
      ))}
    </ul>
  );
}

function MatchCard({ card }) {
  return (
    <div className="glass-card p-5">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs px-2 py-0.5 rounded-full"
          style={{ background: 'rgba(129,140,248,0.12)', color: 'var(--accent-primary)' }}>
          {card.liga}
        </span>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{card.data}</span>
      </div>

      <div className="grid grid-cols-[1fr_auto_1fr] items-start gap-3 my-3">
        <TeamCol stats={card.home_stats} align="left" />
        <div className="flex flex-col items-center pt-1">
          <Swords size={20} style={{ color: 'var(--text-muted)' }} />
          <span className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>vs</span>
        </div>
        <TeamCol stats={card.away_stats} align="right" />
      </div>

      {(card.top_scorers_home?.length > 0 || card.top_scorers_away?.length > 0) && (
        <div className="grid grid-cols-2 gap-3 mt-1">
          <TopScorers list={card.top_scorers_home} align="left" />
          <TopScorers list={card.top_scorers_away} align="right" />
        </div>
      )}

      {(card.injuries_home?.length > 0 || card.injuries_away?.length > 0) && (
        <div className="grid grid-cols-2 gap-3 mt-2">
          <Injuries list={card.injuries_home} align="left" />
          <Injuries list={card.injuries_away} align="right" />
        </div>
      )}
    </div>
  );
}

export default function MatchAnalysisView({ apiFetch }) {
  const [cards, setCards] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    apiFetch('/analyses/matches')
      .then(d => { setCards(d.matches || []); if (d.error) setErr(d.error); })
      .catch(e => setErr(e.message || 'Błąd połączenia'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <h2 className="brand text-2xl mb-1" style={{ color: 'var(--text-main)' }}>Analizy meczów</h2>
      <p className="mb-6" style={{ color: 'var(--text-muted)' }}>
        Najważniejsze mecze tygodnia — gole zdobyte i stracone na mecz, strzelcy, kontuzje.
      </p>
      <p className="mb-6 -mt-4 text-xs inline-flex items-center gap-3" style={{ color: 'var(--text-muted)' }}>
        <span className="inline-flex items-center gap-1"><Target size={16} /> gole zdobyte / mecz</span>
        <span className="inline-flex items-center gap-1"><Shield size={16} /> gole stracone / mecz</span>
      </p>

      {err && <div className="glass-card p-4 mb-4" style={{ color: 'var(--accent-secondary)' }}>{err}</div>}
      {cards === null && <p style={{ color: 'var(--text-muted)' }}>Ładowanie…</p>}
      {cards?.length === 0 && !err && (
        <p style={{ color: 'var(--text-muted)' }}>Brak ważnych meczów w tym tygodniu.</p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {cards?.map((c, i) => <MatchCard key={i} card={c} />)}
      </div>
    </div>
  );
}
