import React, { useState } from 'react';
import { CheckCircle2, XCircle, Clock, ChevronRight, Share2 } from 'lucide-react';
import { odmianaTypy } from '../lib/tips';

const HistoryCouponRow = ({ c, apiFetch, onRefresh }) => {
  const [expanded, setExpanded] = useState(false);
  const [shared, setShared] = useState(!!c.shared);
  const [sharing, setSharing] = useState(false);
  const [settling, setSettling] = useState(false);
  const [settleError, setSettleError] = useState('');
  const isWon = ['WON', 'WIN'].includes(c.status);
  const isLost = ['LOST', 'LOSE'].includes(c.status);
  const isManualActive = c.status === 'ACTIVE' && c.kupon_type === 'manual';
  const legs = c.legs || [];
  const wonCount = legs.filter(l => l.leg_won === true).length;
  const lostCount = legs.filter(l => l.leg_won === false).length;

  const toggleShare = async (e) => {
    e.stopPropagation();
    if (sharing) return;
    setSharing(true);
    try {
      await apiFetch(`/coupon/${c.id}/share`, {
        method: 'PATCH',
        body: JSON.stringify({ shared: !shared }),
      });
      setShared(s => !s);
    } catch (err) {
      console.error('Błąd udostępniania kuponu:', err);
    } finally {
      setSharing(false);
    }
  };

  const markResult = async (result) => {
    if (settling) return;
    setSettling(true);
    setSettleError('');
    try {
      await apiFetch(`/coupon/${c.id}/result`, {
        method: 'PATCH',
        body: JSON.stringify({ result }),
      });
      onRefresh && onRefresh();
    } catch (err) {
      setSettleError(err.message);
    } finally {
      setSettling(false);
    }
  };

  return (
    <div className="glass-card overflow-hidden">
      <div
        className="p-6 flex flex-col md:flex-row justify-between items-center gap-6 cursor-pointer hover:bg-white/[0.02] transition-colors"
        onClick={() => legs.length > 0 && setExpanded(e => !e)}
      >
        <div className="flex items-center gap-4">
          <div className={`w-12 h-12 rounded-full flex items-center justify-center ${isWon ? 'bg-emerald-500/10 text-emerald-400' : isLost ? 'bg-rose-500/10 text-rose-400' : 'bg-amber-500/10 text-amber-400'}`}>
            {isWon ? <CheckCircle2 /> : isLost ? <XCircle /> : <Clock />}
          </div>
          <div>
            <p className="font-bold text-lg">Kupon #{c.id} - {c.phase?.toUpperCase()}</p>
            <p className="text-sm text-slate-500">{new Date(c.created_at).toLocaleString()}</p>
            {legs.length > 0 && (
              <p className="text-xs text-slate-600 mt-0.5">
                <span className="text-emerald-400">{wonCount}✓</span>
                {' / '}
                <span className="text-rose-400">{lostCount}✗</span>
                {' / '}
                <span className="text-slate-500">{legs.length - wonCount - lostCount}⏳</span>
                {' '}
                <span className="text-slate-600">({odmianaTypy(legs.length)})</span>
              </p>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-8 text-center items-center">
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-widest">Kurs</p>
            <p className="font-bold">@{c.total_odds?.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-widest">Stawka</p>
            <p className="font-bold">{c.stake_pln} PLN</p>
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-widest">Wypłata</p>
            <p className={`font-bold ${isWon ? 'text-emerald-400' : 'text-slate-500'}`}>{c.payout_pln ? `${c.payout_pln} PLN` : '---'}</p>
          </div>
          <button
            onClick={toggleShare}
            disabled={sharing}
            title={shared ? 'Cofnij udostępnienie' : 'Udostępnij na liście Najlepsi typerzy'}
            className={`p-2 rounded-lg transition-colors ${shared ? 'text-indigo-400 bg-indigo-500/10' : 'text-slate-500 hover:text-indigo-400 hover:bg-white/5'}`}
          >
            <Share2 size={16} />
          </button>
          {legs.length > 0 && (
            <ChevronRight size={16} className={`text-slate-600 transition-transform ${expanded ? 'rotate-90' : ''}`} />
          )}
        </div>
      </div>

      {isManualActive && (
        <div className="px-6 pb-4 flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-500 uppercase tracking-widest">Oznacz wynik:</span>
          {/* Kolory inline (nie Tailwind-klasy): index.css ma niewarstwowe
              `button { color: inherit; background: transparent }`, ktore bije
              warstwowe (@layer utilities) klasy Tailwind na <button> — patrz
              StatsView.jsx/ProgressChart.jsx (ten sam wzorzec). */}
          <button
            onClick={() => markResult('WON')}
            disabled={settling}
            style={{
              color: 'var(--accent-primary)',
              background: 'color-mix(in srgb, var(--accent-primary) 12%, transparent)',
            }}
            className="text-xs font-bold px-3 py-1.5 rounded-lg disabled:opacity-50 hover:opacity-80 transition-opacity"
          >
            WYGRANY
          </button>
          <button
            onClick={() => markResult('LOST')}
            disabled={settling}
            style={{
              color: 'var(--accent-secondary)',
              background: 'color-mix(in srgb, var(--accent-secondary) 12%, transparent)',
            }}
            className="text-xs font-bold px-3 py-1.5 rounded-lg disabled:opacity-50 hover:opacity-80 transition-opacity"
          >
            PRZEGRANY
          </button>
          <button
            onClick={() => markResult('VOID')}
            disabled={settling}
            style={{
              color: 'var(--text-muted)',
              background: 'color-mix(in srgb, var(--text-muted) 12%, transparent)',
            }}
            className="text-xs font-bold px-3 py-1.5 rounded-lg disabled:opacity-50 hover:opacity-80 transition-opacity"
          >
            ANULOWANY
          </button>
          {settleError && <span className="text-xs" style={{ color: 'var(--accent-secondary)' }}>{settleError}</span>}
        </div>
      )}

      {expanded && legs.length > 0 && (
        <div className="px-6 pb-6 space-y-2 border-t border-white/5 pt-4">
          {legs.map((leg, i) => {
            const won = leg.leg_won;
            return (
              <div key={i} className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${won === true ? 'bg-emerald-500/5 border border-emerald-500/15' : won === false ? 'bg-rose-500/5 border border-rose-500/15' : 'bg-white/[0.02] border border-white/5'}`}>
                <div className="shrink-0">
                  {won === true
                    ? <CheckCircle2 size={14} className="text-emerald-400" />
                    : won === false
                      ? <XCircle size={14} className="text-rose-400" />
                      : <Clock size={14} className="text-amber-400" />}
                </div>
                <span className="font-semibold text-slate-200 flex-1 truncate">{leg.home} - {leg.away}</span>
                <span className="text-slate-400 shrink-0">Typ: <span className="font-bold text-slate-200">{leg.tip}</span></span>
                {leg.prob != null && (
                  <span className="text-xs text-slate-500 shrink-0" title="Pewność modelu">{Math.round(leg.prob)}%</span>
                )}
                {leg.result != null && (
                  <span className={`font-bold shrink-0 ml-2 ${won === true ? 'text-emerald-400' : won === false ? 'text-rose-400' : 'text-slate-400'}`}>{leg.result}</span>
                )}
                <span className="text-xs text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded shrink-0">@{leg.odds}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default HistoryCouponRow;
