import React, { useEffect, useState } from 'react';
import { Sparkles, X, PlusCircle, Trash2 } from 'lucide-react';

const EMPTY_LEG = { home: '', away: '', tip: '', odds: '' };
const BOOKMAKERS = ['STS', 'Fortuna', 'Superbet', 'Betclic', 'Fuksiarz', 'Bzzoiro'];
const PREVIEW_DEBOUNCE_MS = 400;

// Dziennik kuponów (J4b): formularz ręcznego wpisu kuponu obstawionego u innego
// bukmachera. Walidacja klienta jest lustrem walidacji backendu (_validate_manual_coupon),
// żeby błąd 400 był wyjątkiem, nie regułą.
const ManualCouponForm = ({ apiFetch, onClose, onSaved }) => {
  const [legs, setLegs] = useState([{ ...EMPTY_LEG }]);
  const [stakePln, setStakePln] = useState('');
  const [bookmaker, setBookmaker] = useState('');
  const [matchDate, setMatchDate] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  // J6 (Etap B): podgląd naszego sygnału (typ/pewność/prob) — index-aligned z `legs`.
  const [signals, setSignals] = useState([]);

  // Podgląd sygnału: debounce po każdej zmianie nóg/daty, tylko gdy przynajmniej
  // jedna noga ma wypełnione home+away. Błąd sieci/API → cicho (brak sygnału),
  // nie blokuje ani nie psuje formularza (nie dotyka `error`/submitu).
  useEffect(() => {
    const majaczaCosWypelnione = legs.some(l => l.home.trim() && l.away.trim());
    if (!majaczaCosWypelnione) {
      setSignals([]);
      return undefined;
    }
    const timer = setTimeout(() => {
      apiFetch('/coupon/preview-signal', {
        method: 'POST',
        body: JSON.stringify({
          legs: legs.map(l => ({ home: l.home.trim(), away: l.away.trim(), tip: l.tip.trim() })),
          match_date: matchDate || null,
        }),
      })
        .then(setSignals)
        .catch(() => setSignals([]));
    }, PREVIEW_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [legs, matchDate, apiFetch]);

  const addLeg = () => setLegs(prev => [...prev, { ...EMPTY_LEG }]);

  const removeLeg = (index) => setLegs(prev => prev.filter((_, i) => i !== index));

  const updateLeg = (index, field, value) => {
    setLegs(prev => prev.map((leg, i) => (i === index ? { ...leg, [field]: value } : leg)));
  };

  const totalOddsPreview = legs.length > 0 && legs.every(l => parseFloat(l.odds) > 1)
    ? legs.reduce((acc, l) => acc * parseFloat(l.odds), 1).toFixed(2)
    : null;

  const validateClient = () => {
    if (legs.length === 0) return 'Kupon musi mieć co najmniej jedną nogę';
    for (const leg of legs) {
      if (!leg.home.trim() || !leg.away.trim() || !leg.tip.trim()) {
        return 'Uzupełnij gospodarza, gościa i typ dla każdej nogi';
      }
      const odds = parseFloat(leg.odds);
      if (!odds || odds <= 1.0) {
        return 'Kurs każdej nogi musi być większy niż 1.0';
      }
    }
    if (!stakePln || parseFloat(stakePln) <= 0) {
      return 'Stawka musi być dodatnia';
    }
    return null;
  };

  const handleSubmit = async () => {
    const clientError = validateClient();
    if (clientError) {
      setError(clientError);
      return;
    }
    setError('');
    setSubmitting(true);
    try {
      await apiFetch('/coupon/manual', {
        method: 'POST',
        body: JSON.stringify({
          legs: legs.map(l => ({
            home: l.home.trim(), away: l.away.trim(), tip: l.tip.trim(), odds: parseFloat(l.odds),
          })),
          stake_pln: parseFloat(stakePln),
          bookmaker: bookmaker.trim() || null,
          match_date: matchDate || null,
        }),
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[400] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="glass-card w-full max-w-2xl max-h-[90vh] overflow-y-auto p-8">
        <div className="flex justify-between items-start mb-8">
          <div>
            <h2 className="text-2xl font-bold mb-1">Dodaj kupon ręcznie</h2>
            <p className="text-sm text-slate-400">Zapisz w dzienniku kupon obstawiony u innego bukmachera.</p>
          </div>
          <button onClick={onClose} className="p-2 text-slate-500 hover:text-white transition-colors">
            <X size={20} />
          </button>
        </div>

        <div className="space-y-3 mb-6">
          {legs.map((leg, i) => (
            <div
              key={i}
              className="grid grid-cols-1 md:grid-cols-[1fr_1fr_1fr_100px_auto] gap-3 items-center bg-white/[0.02] border border-white/5 rounded-xl p-4"
            >
              <input
                type="text"
                placeholder="Gospodarz"
                value={leg.home}
                onChange={(e) => updateLeg(i, 'home', e.target.value)}
                maxLength={120}
                className="min-w-0 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 transition-colors"
              />
              <input
                type="text"
                placeholder="Gość"
                value={leg.away}
                onChange={(e) => updateLeg(i, 'away', e.target.value)}
                maxLength={120}
                className="min-w-0 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 transition-colors"
              />
              <div className="min-w-0 flex flex-col gap-1">
                <input
                  type="text"
                  placeholder="Typ (np. 1)"
                  value={leg.tip}
                  onChange={(e) => updateLeg(i, 'tip', e.target.value)}
                  maxLength={120}
                  className="min-w-0 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 transition-colors"
                />
                {signals[i]?.matched && (
                  <div
                    className="flex items-center gap-1 text-xs px-1"
                    style={{ color: signals[i].agrees === true ? 'var(--accent-primary)' : signals[i].agrees === false ? 'var(--accent-secondary)' : 'var(--text-muted)' }}
                  >
                    <Sparkles size={16} />
                    <span>
                      Nasz typ: <strong>{signals[i].our_tip}</strong> @{signals[i].our_confidence_pct}%
                    </span>
                  </div>
                )}
              </div>
              <input
                type="number"
                step="0.01"
                min="1.01"
                placeholder="Kurs"
                value={leg.odds}
                onChange={(e) => updateLeg(i, 'odds', e.target.value)}
                className="min-w-0 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 transition-colors"
              />
              <button
                onClick={() => removeLeg(i)}
                disabled={legs.length === 1}
                title="Usuń nogę"
                className="p-2 text-slate-500 hover:text-pink-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors justify-self-end"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>

        <button onClick={addLeg} className="btn-see-all mb-8">
          <PlusCircle size={16} /> Dodaj nogę
        </button>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase mb-2">Stawka (PLN)</label>
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={stakePln}
              onChange={(e) => setStakePln(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase mb-2">Bukmacher</label>
            <input
              type="text"
              list="manual-coupon-bookmakers"
              value={bookmaker}
              onChange={(e) => setBookmaker(e.target.value)}
              maxLength={60}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 focus:outline-none focus:border-indigo-500 transition-colors"
            />
            <datalist id="manual-coupon-bookmakers">
              {BOOKMAKERS.map(b => <option key={b} value={b} />)}
            </datalist>
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase mb-2">Data (opcjonalnie)</label>
            <input
              type="date"
              value={matchDate}
              onChange={(e) => setMatchDate(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>
        </div>

        <div className="flex justify-between items-center mb-6 px-1">
          <span className="text-sm text-slate-400">Kurs łączny</span>
          <span className="font-bold text-lg text-indigo-400">{totalOddsPreview ? `@${totalOddsPreview}` : '—'}</span>
        </div>

        {error && <p className="text-sm text-pink-400 mb-4">{error}</p>}

        <div className="flex gap-4">
          <button onClick={onClose} className="flex-1 py-3 text-slate-500 font-bold hover:text-white transition-colors">
            Anuluj
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="flex-[2] btn-primary py-3 disabled:opacity-50"
          >
            {submitting ? 'Zapisywanie...' : 'Zapisz kupon'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ManualCouponForm;
