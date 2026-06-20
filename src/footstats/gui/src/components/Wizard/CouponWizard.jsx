import React, { useState, useEffect, useMemo } from 'react';
import {
  Calendar, CheckCircle2, ChevronRight, ChevronDown, Sparkles, Target
} from 'lucide-react';
import { motion } from 'framer-motion';
import { getLeagueFlag } from '../../lib/leagues';
import { groupTips } from '../../lib/tips';
import MarketsPanel from './MarketsPanel';
import BetBuilderPanel from './BetBuilderPanel';

const CouponWizard = ({ apiFetch, onComplete, onCancel, initialProposal }) => {
  const [step, setStep] = useState(initialProposal ? 4 : 1);
  const [matches, setMatches] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [analysis, setAnalysis] = useState([]);
  const [selections, setSelections] = useState(() =>
    initialProposal
      ? initialProposal.legs.map(leg => ({
          match_id: String(leg.match_id),
          home: leg.home,
          away: leg.away,
          tip: leg.tip,
          odds: leg.odds,
          win_prob: leg.prob,
        }))
      : []
  );
  const [kelly, setKelly] = useState(null);
  const [stake, setStake] = useState(2.0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadMatches = async () => {
    setLoading(true);
    try {
      const data = await apiFetch('/matches/today');
      setMatches(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initialProposal) {
      calculateKelly();
    } else {
      loadMatches();
    }
  }, []);

  const toggleMatch = (id) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const groupedMatches = useMemo(() => {
    const groups = {};
    for (const m of matches) {
      const liga = m.liga || 'Inne';
      if (!groups[liga]) groups[liga] = [];
      groups[liga].push(m);
    }
    return Object.entries(groups);
  }, [matches]);

  const [collapsedLeagues, setCollapsedLeagues] = useState([]);

  const toggleLeagueSection = (liga) => {
    setCollapsedLeagues(prev =>
      prev.includes(liga) ? prev.filter(l => l !== liga) : [...prev, liga]
    );
  };

  const toggleLeague = (liga, leagueMatches) => {
    const ids = leagueMatches.map(m => m.id);
    const allSelected = ids.every(id => selectedIds.includes(id));
    setSelectedIds(prev =>
      allSelected
        ? prev.filter(id => !ids.includes(id))
        : [...new Set([...prev, ...ids])]
    );
  };

  const handleAnalyze = async () => {
    setLoading(true);
    setStep(2);
    try {
      const data = await apiFetch('/matches/analyze', {
        method: 'POST',
        body: JSON.stringify({ match_ids: selectedIds })
      });
      setAnalysis(data);
      setStep(3);
    } catch (err) {
      setError(err.message);
      setStep(1);
    } finally {
      setLoading(false);
    }
  };

  const selectTip = (matchId, tip, odds, prob, home, away) => {
    setSelections(prev => {
      const filtered = prev.filter(s => s.match_id !== matchId);
      return [...filtered, { match_id: matchId, home, away, tip, odds, win_prob: prob }];
    });
  };

  const [bbOpen, setBbOpen] = useState(null);
  const [marketsOpen, setMarketsOpen] = useState(null);

  const addCombo = (match, markets, comboSzansa, comboOdds) => {
    const tip = `BB: ${markets.join(' + ')}`;
    setSelections(prev => {
      const filtered = prev.filter(s => s.match_id !== match.id);
      return [...filtered, {
        match_id: match.id, home: match.home, away: match.away,
        tip, odds: comboOdds, win_prob: comboSzansa,
      }];
    });
    setBbOpen(null);
  };

  const calculateKelly = async () => {
    setLoading(true);
    try {
      const data = await apiFetch('/coupon/kelly', {
        method: 'POST',
        body: JSON.stringify({ selections })
      });
      setKelly(data);
      setStake(data.stake_pln);
      setStep(4);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const placeCoupon = async () => {
    setLoading(true);
    try {
      const totalOdds = selections.reduce((acc, s) => acc * s.odds, 1.0);
      await apiFetch('/coupon/place', {
        method: 'POST',
        body: JSON.stringify({
          selections,
          total_odds: totalOdds,
          stake_pln: stake,
          match_date: new Date().toISOString().split('T')[0]
        })
      });
      onComplete();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="max-w-4xl mx-auto"
    >
      <header className="mb-10 flex justify-between items-end">
        <div>
          <h1 className="text-4xl font-bold mb-2">Kreator Kuponu</h1>
          <p className="text-slate-400">Przejdź przez kroki, aby stworzyć optymalny kupon.</p>
        </div>
        <button onClick={onCancel} className="text-slate-500 hover:text-white transition-colors">Anuluj</button>
      </header>

      {/* Progress Bar */}
      <div className="flex items-center gap-2 mb-12">
        {[1, 2, 3, 4, 5].map((s) => (
          <React.Fragment key={s}>
            <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold transition-all ${step === s ? 'bg-white/5 border-2 border-indigo-400 text-indigo-300 scale-110' : step > s ? 'bg-emerald-500 text-white' : 'bg-white/5 text-slate-500'}`}>
              {step > s ? <CheckCircle2 size={18} /> : s}
            </div>
            {s < 5 && <div className={`flex-1 h-1 rounded-full ${step > s ? 'bg-emerald-500' : 'bg-white/5'}`} />}
          </React.Fragment>
        ))}
      </div>

      {/* Steps Content */}
      <div className="min-h-[400px]">
        {step === 1 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
            <h3 className="text-xl font-bold flex items-center gap-2 text-indigo-300">
              <Calendar size={20} /> Krok 1: Wybierz mecze na dziś
            </h3>
            {loading ? (
              <div className="text-center py-20 text-slate-500">Pobieranie oferty...</div>
            ) : (
              <div className="space-y-3">
                {groupedMatches.map(([liga, leagueMatches]) => {
                  const collapsed = collapsedLeagues.includes(liga);
                  const allSelected = leagueMatches.every(m => selectedIds.includes(m.id));
                  return (
                    <div key={liga}>
                      <div
                        onClick={() => toggleLeagueSection(liga)}
                        className="flex items-center gap-4 px-4 py-3 rounded-lg hover:bg-white/5 transition-all cursor-pointer select-none"
                      >
                        <div
                          onClick={(e) => { e.stopPropagation(); toggleLeague(liga, leagueMatches); }}
                          className={`w-5 h-5 rounded border-2 flex items-center justify-center shrink-0 transition-all ${allSelected ? 'border-indigo-500 bg-indigo-500/20' : 'border-white/20'}`}
                        >
                          {allSelected && <CheckCircle2 size={14} className="text-indigo-400" />}
                        </div>
                        <span className="text-base text-indigo-400 font-semibold uppercase tracking-wide flex-1">{getLeagueFlag(liga)} {liga}</span>
                        <span className="text-xs text-slate-500">{leagueMatches.length} mecz{leagueMatches.length === 1 ? '' : leagueMatches.length < 5 ? 'e' : 'y'}</span>
                        <ChevronDown size={16} className={`text-slate-500 transition-transform ${collapsed ? '-rotate-90' : ''}`} />
                      </div>
                      {!collapsed && (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2 pl-2">
                          {leagueMatches.map(m => (
                            <div
                              key={m.id}
                              onClick={() => toggleMatch(m.id)}
                              className={`glass-card p-6 cursor-pointer border-2 transition-all ${selectedIds.includes(m.id) ? 'border-indigo-500 bg-indigo-500/5' : 'border-transparent'}`}
                            >
                              <div className="flex justify-between items-start mb-2">
                                <span className="text-xs font-bold uppercase tracking-widest text-indigo-400">{getLeagueFlag(m.liga)} {m.liga}</span>
                                <span className="text-xs text-slate-500">
                                  {m.data && new Date(m.data).toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit' })} {m.godzina}
                                </span>
                              </div>
                              <p className="font-bold text-lg">{m.gosp} vs {m.gosc}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            <div className="wizard-action-bar">
              <button
                onClick={handleAnalyze}
                disabled={selectedIds.length === 0 || loading}
                className="btn-primary px-8 py-4 flex items-center gap-2 shadow-lg disabled:opacity-50"
              >
                Analizuj wybrane ({selectedIds.length}) <ChevronRight size={18} />
              </button>
            </div>
            {/* Spacer so content doesn't sit under the fixed action bar */}
            <div className="pt-32" />
          </motion.div>
        )}

        {step === 2 && (
          <div className="flex flex-col items-center justify-center py-20 space-y-6">
            <Sparkles className="text-indigo-400 animate-pulse" size={64} />
            <div className="text-center">
              <h3 className="text-2xl font-bold mb-2">Głęboka Analiza ML</h3>
              <p className="text-slate-500">Mielimy dane, składy i historyczne H2H...</p>
            </div>
          </div>
        )}

        {step === 3 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-8">
            <h3 className="text-xl font-bold flex items-center gap-2 text-indigo-300">
              <Target size={20} /> Krok 3: Wybierz typy
            </h3>
            <div className="space-y-6">
              {analysis.map(m => (
                <div key={m.id} className="glass-card p-6">
                  <div className="flex justify-between items-center mb-6">
                    <div>
                      <p className="font-bold text-lg">{m.home} - {m.away}</p>
                      <p className="text-xs text-slate-500">{getLeagueFlag(m.liga)} {m.liga}</p>
                    </div>
                    <div className="text-right">
                      <span className="text-xs text-slate-500 block">Sugerowany typ:</span>
                      <span className="font-bold text-indigo-400">{(m.suggested_tip || m.tips[0])?.tip} (@{(m.suggested_tip || m.tips[0])?.odds})</span>
                    </div>
                  </div>
                  <div className="space-y-4">
                    {groupTips(m.tips).map((group) => (
                      <div key={group.label}>
                        <span className="text-xs font-bold uppercase tracking-widest text-slate-500 block mb-2">{group.label}</span>
                        <div className="flex flex-wrap gap-3">
                          {group.items.map((t, idx) => {
                            const isSelected = selections.find(s => s.match_id === m.id && s.tip === t.tip);
                            return (
                              <button
                                key={idx}
                                onClick={() => selectTip(m.id, t.tip, t.odds, t.prob, m.home, m.away)}
                                className={`min-w-28 flex-1 p-4 rounded-xl border transition-all text-center ${isSelected ? 'bg-indigo-500 border-indigo-400 text-white shadow-lg' : 'bg-white/5 border-white/10 text-slate-400 hover:bg-white/10'}`}
                              >
                                <span className="block font-bold">{t.tip}</span>
                                <span className="text-sm opacity-80">@{t.odds}</span>
                                <div className="mt-2 h-1 bg-black/20 rounded-full overflow-hidden">
                                  <div className="h-full bg-white/40" style={{ width: `${t.prob}%` }} />
                                </div>
                                <span className="text-xs mt-1 block">{t.prob}%</span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      onClick={() => { setMarketsOpen(marketsOpen === m.id ? null : m.id); setBbOpen(null); }}
                      className="btn-see-all text-xs flex items-center gap-1.5"
                    >
                      📊 {marketsOpen === m.id ? 'Ukryj rynki' : 'Wszystkie rynki'}
                    </button>
                    <button
                      onClick={() => { setBbOpen(bbOpen === m.id ? null : m.id); setMarketsOpen(null); }}
                      className="btn-see-all text-xs flex items-center gap-1.5"
                    >
                      🎰 {bbOpen === m.id ? 'Ukryj BetBuilder' : 'Zbuduj BetBuilder'}
                    </button>
                  </div>
                  {marketsOpen === m.id && (
                    <MarketsPanel apiFetch={apiFetch} match={m} selections={selections} onSelectTip={selectTip} />
                  )}
                  {bbOpen === m.id && (
                    <BetBuilderPanel apiFetch={apiFetch} match={m} onAddCombo={addCombo} />
                  )}
                </div>
              ))}
            </div>
            <div className="flex justify-between pt-8">
              <button onClick={() => setStep(1)} className="text-slate-500 font-bold">← Wróć</button>
              <button
                onClick={calculateKelly}
                disabled={selections.length === 0}
                className="btn-primary px-8 py-4 flex items-center gap-2 disabled:opacity-50"
              >
                Oblicz Stawkę Kelly <ChevronRight size={18} />
              </button>
            </div>
          </motion.div>
        )}

        {step === 4 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-center py-10">
            <div className="glass-card p-10 w-full max-w-lg border-emerald-500/20">
              <h3 className="text-2xl font-bold mb-8 text-center text-emerald-400">Optymalizacja Finansowa</h3>
              <div className="space-y-4 mb-10">
                <div className="flex justify-between py-2 border-b border-white/5">
                  <span className="text-slate-400">Kurs całkowity</span>
                  <span className="font-bold">@{kelly?.total_odds.toFixed(2)}</span>
                </div>
                <div className="flex justify-between py-2 border-b border-white/5">
                  <span className="text-slate-400">Szansa na sukces</span>
                  <span className="font-bold text-indigo-400">{kelly?.win_prob_pct}%</span>
                </div>
                <div className="flex justify-between py-2 border-b border-white/5">
                  <span className="text-slate-400">Sugerowana stawka (Kelly)</span>
                  <span className="font-bold text-xl text-emerald-400">{kelly?.stake_pln.toFixed(2)} PLN</span>
                </div>
              </div>
              <div className="mb-10">
                <label className="block text-xs font-bold text-slate-500 uppercase mb-3">Twoja Stawka (PLN)</label>
                <input
                  type="number"
                  value={stake}
                  onChange={(e) => setStake(parseFloat(e.target.value))}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-6 py-4 text-2xl font-bold text-center focus:outline-none focus:border-emerald-500 transition-colors"
                />
              </div>
              <button
                onClick={() => setStep(5)}
                className="w-full py-4 bg-emerald-500 hover:bg-emerald-600 rounded-xl font-bold transition-all shadow-lg shadow-emerald-500/20"
              >
                Podsumowanie i zakład
              </button>
            </div>
          </motion.div>
        )}

        {step === 5 && (
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="flex justify-center py-10">
            <div className="glass-card p-10 w-full max-w-lg border-indigo-500/30 bg-indigo-500/5">
              <h3 className="text-2xl font-bold mb-2 text-center">Ostatnie Potwierdzenie</h3>
              <p className="text-slate-500 text-center text-sm mb-10">Sprawdź szczegóły przed wysłaniem na serwer.</p>

              <div className="space-y-4 mb-10">
                {selections.map((s, i) => (
                  <div key={i} className="flex justify-between items-center text-sm">
                    <span>{s.home} vs {s.away}</span>
                    <span className="font-bold text-indigo-300">{s.tip} (@{s.odds})</span>
                  </div>
                ))}
              </div>

              <div className="p-6 bg-white/5 rounded-2xl border border-white/5 space-y-3 mb-10">
                <div className="flex justify-between text-slate-400">
                  <span>Kurs łączny</span>
                  <span className="font-bold text-white">@{selections.reduce((acc, s) => acc * s.odds, 1.0).toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>Stawka</span>
                  <span className="font-bold text-indigo-400">{stake.toFixed(2)} PLN</span>
                </div>
                <div className="flex justify-between text-lg font-bold border-t border-white/10 pt-3">
                  <span>Do wygrania</span>
                  <span className="text-emerald-400">{(stake * selections.reduce((acc, s) => acc * s.odds, 1.0)).toFixed(2)} PLN</span>
                </div>
              </div>

              {error && <p className="text-rose-400 text-sm mb-4 text-center">{error}</p>}

              <div className="flex gap-4">
                <button onClick={() => setStep(4)} className="flex-1 py-4 text-slate-500 font-bold hover:text-white transition-colors">Wróć</button>
                <button
                  onClick={placeCoupon}
                  disabled={loading}
                  className="flex-[2] py-4 bg-gradient-to-r from-indigo-500 to-pink-500 hover:from-indigo-600 hover:to-pink-600 rounded-xl font-bold transition-all shadow-xl shadow-indigo-500/30"
                >
                  {loading ? "Wysyłanie..." : "POSTAW KUPON"}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </div>
    </motion.div>
  );
};

export default CouponWizard;
