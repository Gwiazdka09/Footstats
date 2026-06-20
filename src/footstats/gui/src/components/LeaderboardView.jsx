import React, { useState, useEffect } from 'react';
import { Trophy } from 'lucide-react';
import { motion } from 'framer-motion';
import HistoryCouponRow from './HistoryCouponRow';

const LeaderboardView = ({ apiFetch }) => {
  const [leaders, setLeaders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [sharedCoupons, setSharedCoupons] = useState([]);
  const [loadingCoupons, setLoadingCoupons] = useState(false);

  useEffect(() => {
    apiFetch('/leaderboard').then(data => {
      setLeaders(data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

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

  if (loading) return <div className="text-center py-20">Ładowanie rankingu...</div>;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
    >
      <div className="mb-12">
        <h1 className="text-4xl font-bold mb-2 flex items-center gap-3"><Trophy className="text-amber-400" /> Najlepsi typerzy</h1>
        <p className="text-slate-400">Ranking wg win rate na udostępnionych kuponach. Kliknij typera, by zobaczyć jego kupony.</p>
      </div>

      {leaders.length === 0 ? (
        <div className="glass-card text-center py-20 px-12 text-slate-500 flex flex-col items-center gap-4">
          <Trophy size={40} className="text-slate-600" />
          <p>Brak danych — nikt jeszcze nie udostępnił kuponów.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 mb-10">
          {leaders.map((l, i) => (
            <div
              key={l.user_id}
              onClick={() => selectUser(l.username)}
              className={`glass-card p-6 flex items-center justify-between gap-6 cursor-pointer transition-colors ${selected === l.username ? 'border-2 border-indigo-500' : ''}`}
            >
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-full bg-indigo-500/10 flex items-center justify-center font-bold text-indigo-400">
                  #{i + 1}
                </div>
                <p className="font-bold text-lg">{l.username}</p>
              </div>
              <div className="flex gap-8 text-center">
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-widest">Win rate</p>
                  <p className="font-bold text-emerald-400">{l.win_rate}%</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-widest">Kupony</p>
                  <p className="font-bold">{l.wins}/{l.total}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {selected && (
        <div>
          <h2 className="text-2xl font-bold mb-6">Kupony: {selected}</h2>
          {loadingCoupons ? (
            <div className="text-center py-12 text-slate-500">Ładowanie kuponów...</div>
          ) : sharedCoupons.length > 0 ? (
            <div className="grid grid-cols-1 gap-4">
              {sharedCoupons.map(c => (
                <HistoryCouponRow key={c.id} c={c} apiFetch={apiFetch} />
              ))}
            </div>
          ) : (
            <div className="text-center p-12 glass-card text-slate-500">Ten typer nie udostępnił żadnych kuponów.</div>
          )}
        </div>
      )}
    </motion.div>
  );
};

export default LeaderboardView;
