import React, { useState, useEffect } from 'react';
import {
  Wallet, TrendingUp, CheckCircle2, Clock, ChevronRight, Target
} from 'lucide-react';
import { motion } from 'framer-motion';
import { getLeagueFlag } from '../lib/leagues';
import { StatCard, CouponCard } from './ui';

const RISK_LABELS = {
  low: { title: 'Niskie ryzyko', border: 'border-emerald-500/20', text: 'text-emerald-400' },
  medium: { title: 'Średnie ryzyko', border: 'border-amber-500/20', text: 'text-amber-400' },
  high: { title: 'Wysokie ryzyko', border: 'border-rose-500/20', text: 'text-rose-400' },
};

const DailyProposals = ({ apiFetch, onCopyProposal }) => {
  const [proposals, setProposals] = useState(null);

  useEffect(() => {
    apiFetch('/coupons/daily-proposals').then(setProposals).catch(() => setProposals(null));
  }, []);

  if (!proposals) return null;
  const tiers = ['low', 'medium', 'high'].filter(t => proposals[t]?.legs?.length > 0);
  if (tiers.length === 0) return null;

  return (
    <section className="mb-16">
      <h2 className="text-2xl font-bold mb-10">Propozycje dnia</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {tiers.map(tier => {
          const { title, border, text } = RISK_LABELS[tier];
          const p = proposals[tier];
          return (
            <div key={tier} className={`glass-card p-7 ${border} flex flex-col`}>
              <div className="flex justify-between items-center mb-5">
                <span className={`text-xs font-bold uppercase tracking-widest ${text}`}>{title}</span>
                <span className="text-xs text-slate-500">@{p.total_odds?.toFixed(2)}</span>
              </div>
              <div className="space-y-3 flex-1">
                {p.legs.map((leg, i) => (
                  <div key={i} className="text-base rounded-xl px-4 py-3 bg-white/[0.02] border border-white/5">
                    <p className="font-semibold">{getLeagueFlag(leg.liga)} {leg.home} - {leg.away}</p>
                    <p className="text-slate-500 text-sm mt-1">Typ: <span className="text-slate-300 font-bold">{leg.label}</span> @{leg.odds}</p>
                  </div>
                ))}
              </div>
              <button
                onClick={() => onCopyProposal?.(p)}
                className="w-full mt-5 py-3 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl font-bold text-sm transition-colors"
              >
                Skopiuj kupon
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
};

const DashboardHome = ({ user, status, coupons, calibration, isAdmin, apiFetch, onSeeAll, onCopyProposal }) => (
  <motion.div
    initial={{ opacity: 0, x: 20 }}
    animate={{ opacity: 1, x: 0 }}
    exit={{ opacity: 0, x: -20 }}
  >
    <header className="flex flex-col md:flex-row justify-between items-start md:items-center mb-16 gap-4">
      <div>
        <h1 className="text-4xl font-bold mb-2">Witaj, {user}</h1>
        <p className="text-slate-400">Twój asystent analityczny do kuponów jest online.</p>
      </div>
      <div className="glass-card px-8 py-5 flex items-center gap-5 border-indigo-500/20 bg-indigo-500/5">
        <div className="p-4 bg-indigo-500/20 rounded-2xl flex items-center justify-center">
          <Wallet className="text-indigo-400" size={28} />
        </div>
        <div>
          <p className="text-xs text-slate-400 uppercase tracking-widest font-bold mb-1">Dostępny Balans</p>
          <p className="text-3xl font-bold leading-none metric-num">
            <span className="stat-gradient">{status?.bankroll?.toFixed(2)}</span> <span className="text-lg font-normal text-indigo-300">PLN</span>
          </p>
        </div>
      </div>
    </header>

    <section className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-16">
      <StatCard
        title="Skuteczność (ROI)"
        value={`${status?.stats?.roi_pct >= 0 ? '+' : ''}${status?.stats?.roi_pct}%`}
        subtitle="Całkowity zwrot z inwestycji"
        icon={<TrendingUp className={status?.stats?.roi_pct >= 0 ? "text-emerald-400" : "text-rose-400"} />}
        color={status?.stats?.roi_pct >= 0 ? "emerald" : "rose"}
        delay={0.1}
      />
      <StatCard
        title="Wygrane (30 dni)"
        value={status?.stats?.wins_last_30d || 0}
        subtitle="Kupony rozliczone na plus"
        icon={<CheckCircle2 className="text-indigo-400" />}
        color="indigo"
        delay={0.2}
      />
      <StatCard
        title="Aktywne"
        value={coupons?.length || 0}
        subtitle="Oczekujące na wynik"
        icon={<Clock className="text-pink-400" />}
        color="pink"
        delay={0.3}
      />
    </section>

    {isAdmin && calibration && calibration.n_matches > 0 && (
      <section className="glass-card p-6 mb-8">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-5">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-500/10 rounded-xl">
              <Target className="text-indigo-400" size={18} />
            </div>
            <span className="text-sm font-bold text-white">Model Poisson</span>
          </div>
          <span className="text-xs text-slate-500">
            Ostatnia kalibracja:{' '}
            <span className="text-indigo-300 font-semibold">
              {calibration.updated_at ? new Date(calibration.updated_at).toLocaleDateString('pl-PL') : '—'}
            </span>
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white/5 rounded-xl p-4 text-center">
            <p className="text-xs text-slate-500 uppercase tracking-widest mb-1">Próbka</p>
            <p className="text-lg font-bold text-white">{calibration.n_matches} <span className="text-xs font-normal text-slate-500">meczów</span></p>
          </div>
          <div className="bg-white/5 rounded-xl p-4 text-center">
            <p className="text-xs text-slate-500 uppercase tracking-widest mb-1">λ dom</p>
            <p className="text-lg font-bold text-emerald-400">{calibration.factor_home?.toFixed(4)}</p>
          </div>
          <div className="bg-white/5 rounded-xl p-4 text-center">
            <p className="text-xs text-slate-500 uppercase tracking-widest mb-1">λ goście</p>
            <p className="text-lg font-bold text-pink-400">{calibration.factor_away?.toFixed(4)}</p>
          </div>
          {calibration.acc_1x2_pct != null && (
            <div className="bg-white/5 rounded-xl p-4 text-center">
              <p className="text-xs text-slate-500 uppercase tracking-widest mb-1">Dokładność 1X2</p>
              <p className="text-lg font-bold text-indigo-300">{calibration.acc_1x2_pct}%</p>
            </div>
          )}
        </div>
      </section>
    )}

    <DailyProposals apiFetch={apiFetch} onCopyProposal={onCopyProposal} />

    <section>
      <div className="flex justify-between items-center mb-10">
        <h2 className="text-2xl font-bold">Aktywne Predykcje</h2>
        <button onClick={onSeeAll} className="btn-see-all">
          Zobacz pełną historię <ChevronRight size={16} />
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
        {coupons && coupons.length > 0 ? coupons.map((c, i) => (
          <CouponCard key={c.id} coupon={c} index={i} />
        )) : (
          <div className="md:col-span-2 text-center p-12 glass-card text-slate-500">Brak aktywnych kuponów. Stwórz nowy!</div>
        )}
      </div>
    </section>
  </motion.div>
);

export default DashboardHome;
