import React, { useState, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';

// --- Markets Panel (FAZA 20): pełny katalog rynków bramkowych, grupowany jak STS ---
const MarketsPanel = ({ apiFetch, match, selections, onSelectTip }) => {
  const [grupy, setGrupy] = useState(null);
  const [loading, setLoading] = useState(false);
  const [collapsed, setCollapsed] = useState({});

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const res = await apiFetch('/markets/catalog', {
          method: 'POST',
          body: JSON.stringify({
            prob_home_win: (match.prob_home || 0) / 100,
            prob_away_win: (match.prob_away || 0) / 100,
            prob_over_25: (match.prob_over || 0) / 100,
            odds: match.odds || {},
          }),
        });
        if (alive) setGrupy(res.grupy || []);
      } catch { /* cichy fallback */ } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [match.id]);

  const sel = selections.find(s => s.match_id === match.id);

  return (
    <div className="mt-5 pt-5 border-t border-white/5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-bold uppercase tracking-widest text-[var(--accent-primary)]">
          📊 Wszystkie rynki (Poisson)
        </span>
        {loading && <span className="text-xs text-slate-600">Liczenie…</span>}
      </div>
      <div className="space-y-3">
        {(grupy || []).map((g) => {
          const isCollapsed = collapsed[g.grupa];
          return (
            <div key={g.grupa}>
              <button
                onClick={() => setCollapsed(c => ({ ...c, [g.grupa]: !c[g.grupa] }))}
                className="w-full flex items-center justify-between py-1.5 text-left"
              >
                <span className="text-xs font-bold uppercase tracking-wider text-slate-500">{g.grupa}</span>
                <ChevronDown size={14} className={`text-slate-600 transition-transform ${isCollapsed ? '-rotate-90' : ''}`} />
              </button>
              {!isCollapsed && (
                <div className="flex flex-wrap gap-2">
                  {g.rynki.map((r) => {
                    const isSel = sel && sel.tip === r.tip;
                    return (
                      <button
                        key={r.tip}
                        onClick={() => onSelectTip(match.id, r.tip, r.kurs, r.szansa, match.home, match.away)}
                        title={r.zrodlo === 'bzzoiro' ? 'kurs Bzzoiro' : 'kurs szacowany (fair)'}
                        className={`px-3 py-2 rounded-lg text-xs border transition-all text-left ${
                          isSel
                            ? 'bg-[var(--accent-primary)] border-[var(--accent-primary)] text-white'
                            : 'bg-white/5 border-white/10 text-slate-300 hover:bg-white/10'
                        }`}
                      >
                        <span className="block font-bold">{r.rynek}</span>
                        <span className="opacity-80">@{r.kurs}</span>
                        <span className="opacity-60 ml-1">{r.szansa}%</span>
                        {r.zrodlo === 'fair' && <span className="opacity-40 ml-1">~</span>}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-[11px] text-slate-600">~ = kurs szacowany (fair, model). Bez ~ = kurs Bzzoiro.</p>
    </div>
  );
};

export default MarketsPanel;
