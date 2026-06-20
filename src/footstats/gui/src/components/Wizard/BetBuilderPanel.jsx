import React, { useState, useEffect } from 'react';

// --- BetBuilder Panel (FAZA 18.2) ---
// Combo z 1 meczu z regułami korelacji z backendu (single source of truth).
// Sprzeczne (1+2) i trywialne (1 ⇒ Over 0.5) typy są blokowane.
const BetBuilderPanel = ({ apiFetch, match, onAddCombo }) => {
  const [selected, setSelected] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    const fetchMarkets = async () => {
      setLoading(true);
      try {
        const res = await apiFetch('/betbuilder/markets', {
          method: 'POST',
          body: JSON.stringify({
            prob_home_win: (match.prob_home || 0) / 100,
            prob_away_win: (match.prob_away || 0) / 100,
            prob_over_25: (match.prob_over || 0) / 100,
            selected,
          }),
        });
        if (alive) setData(res);
      } catch { /* cichy fallback */ } finally {
        if (alive) setLoading(false);
      }
    };
    fetchMarkets();
    return () => { alive = false; };
  }, [selected]);

  const toggle = (rynek, allowed, wybrany) => {
    if (wybrany) setSelected(prev => prev.filter(r => r !== rynek));
    else if (allowed) setSelected(prev => [...prev, rynek]);
  };

  const comboSzansa = data?.combo_szansa ?? 0;
  const comboOdds = comboSzansa > 0 ? +(100 / comboSzansa).toFixed(2) : 0;

  return (
    <div className="mt-5 pt-5 border-t border-white/5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-bold uppercase tracking-widest text-[var(--accent-secondary)]">
          🎰 BetBuilder (combo z tego meczu)
        </span>
        {selected.length > 0 && (
          <span className="text-xs text-[var(--text-muted)]">
            Szansa combo: <span className="text-[var(--accent-primary)] font-bold">{comboSzansa}%</span> · kurs ~{comboOdds}
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {(data?.rynki || []).map((r) => {
          const blocked = !r.allowed && !r.wybrany;
          return (
            <button
              key={r.rynek}
              onClick={() => toggle(r.rynek, r.allowed, r.wybrany)}
              disabled={blocked}
              title={r.powod || ''}
              className={`px-3 py-2 rounded-lg text-xs border transition-all text-left ${
                r.wybrany
                  ? 'bg-[var(--accent-primary)] border-[var(--accent-primary)] text-white'
                  : blocked
                    ? 'bg-white/[0.02] border-white/5 text-slate-600 cursor-not-allowed line-through'
                    : 'bg-white/5 border-white/10 text-slate-300 hover:bg-white/10'
              }`}
            >
              <span className="block font-bold">{r.rynek}</span>
              <span className="opacity-70">{r.szansa}%</span>
            </button>
          );
        })}
      </div>
      {selected.length >= 2 && (
        <button
          onClick={() => onAddCombo(match, selected, comboSzansa, comboOdds)}
          className="btn-primary mt-4 px-5 py-2.5 text-sm"
        >
          Dodaj combo do kuponu ({selected.length} zdarzeń)
        </button>
      )}
      {selected.length === 1 && (
        <p className="mt-3 text-xs text-[var(--text-muted)]">Wybierz min. 2 zdarzenia aby zbudować BetBuilder.</p>
      )}
      {loading && <p className="mt-2 text-xs text-slate-600">Przeliczanie reguł…</p>}
    </div>
  );
};

export default BetBuilderPanel;
