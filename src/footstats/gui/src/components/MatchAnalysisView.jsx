import { useState, useEffect } from 'react';
import { API_BASE } from '../lib/api';
import { Swords, Sparkles, Shield, Target, Activity, Loader2 } from 'lucide-react';

// Pasek 1X2 (indigo dom / muted remis / pink wyjazd) — jedno accent-pairing
function ProbBar({ pw, pr, pp }) {
  const seg = [
    { v: pw, c: 'var(--accent-primary)', l: '1' },
    { v: pr, c: 'var(--text-muted)', l: 'X' },
    { v: pp, c: 'var(--accent-secondary)', l: '2' },
  ];
  return (
    <div>
      <div className="flex h-2 rounded-full overflow-hidden">
        {seg.map((s, i) => (
          <div key={i} style={{ width: `${s.v || 0}%`, background: s.c }} />
        ))}
      </div>
      <div className="flex justify-between mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>
        {seg.map((s, i) => <span key={i}>{s.l} {s.v != null ? `${Math.round(s.v)}%` : '—'}</span>)}
      </div>
    </div>
  );
}

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
  const [ai, setAi] = useState(null);
  const [loading, setLoading] = useState(false);
  const m = card.model || {};

  const analizuj = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/analyses/llm`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(card),
      });
      const d = await r.json();
      setAi(d.analysis || d.error || 'Brak analizy');
    } catch {
      setAi('Błąd połączenia');
    } finally {
      setLoading(false);
    }
  };

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

      <ProbBar pw={m.pw} pr={m.pr} pp={m.pp} />

      <div className="flex gap-4 mt-3 text-sm" style={{ color: 'var(--text-muted)' }}>
        <span className="inline-flex items-center gap-1"><Activity size={16} />Over 2.5: {m.o25 != null ? `${Math.round(m.o25)}%` : '—'}</span>
        <span>BTTS: {m.bt != null ? `${Math.round(m.bt)}%` : '—'}</span>
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

      {ai ? (
        <p className="text-sm mt-4 leading-relaxed" style={{ color: 'var(--text-main)' }}>{ai}</p>
      ) : (
        <button className="btn-primary mt-4 inline-flex items-center gap-2 text-sm"
          onClick={analizuj} disabled={loading}>
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
          {loading ? 'Analizuję…' : 'Analiza AI'}
        </button>
      )}
    </div>
  );
}

export default function MatchAnalysisView() {
  const [cards, setCards] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/analyses/matches`)
      .then(r => r.json())
      .then(d => { setCards(d.matches || []); if (d.error) setErr(d.error); })
      .catch(() => setErr('Błąd połączenia'));
  }, []);

  return (
    <div>
      <h2 className="brand text-2xl mb-1" style={{ color: 'var(--text-main)' }}>Analizy meczów</h2>
      <p className="mb-6" style={{ color: 'var(--text-muted)' }}>
        Najważniejsze mecze — gole/mecz, kontuzje, model i analiza AI.
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
