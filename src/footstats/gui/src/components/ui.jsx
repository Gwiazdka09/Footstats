import React from 'react';
import { Calendar, CheckCircle2, XCircle, Clock, Info } from 'lucide-react';
import { motion } from 'framer-motion';

export const NavItem = ({ icon, label, active, collapsed, onClick }) => (
  <div
    onClick={onClick}
    className={`nav-item flex items-center gap-4 px-4 py-3 rounded-xl cursor-pointer transition-all ${active ? 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/25' : 'text-slate-400 hover:bg-white/5 hover:text-white'}`}
  >
    <div className={active ? 'text-indigo-400' : 'text-slate-500'}>{icon}</div>
    {!collapsed && <span className="nav-label font-semibold">{label}</span>}
  </div>
);

export const StatCard = ({ title, value, subtitle, icon, color, delay }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ delay }}
    className="glass-card p-8"
  >
    <div className="flex justify-between items-start mb-6">
      <div className={`p-3 bg-${color}-500/10 rounded-xl`}>{icon}</div>
    </div>
    <h3 className="text-slate-500 text-sm font-semibold uppercase tracking-wider mb-2">{title}</h3>
    <div className="metric-num text-4xl font-bold mb-2">{value}</div>
    <p className="text-slate-400 text-xs">{subtitle}</p>
  </motion.div>
);

export const CouponCard = ({ coupon, index }) => (
  <motion.div
    initial={{ opacity: 0, scale: 0.95 }}
    animate={{ opacity: 1, scale: 1 }}
    transition={{ delay: index * 0.1 }}
    className="glass-card overflow-hidden group hover:border-indigo-500/30 transition-all font-inter"
  >
    <div className="p-6 border-b border-white/5 flex justify-between items-center bg-white/5">
      <div className="flex items-center gap-3">
        <div className={`w-3 h-3 rounded-full ${['WON','WIN'].includes(coupon.status) ? 'bg-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.5)]' : ['LOST','LOSE'].includes(coupon.status) ? 'bg-rose-500' : 'bg-amber-500 animate-pulse outline outline-4 outline-amber-500/10'}`}></div>
        <span className="font-bold tracking-tight">Kupon #{coupon.id} <span className="text-xs text-slate-500 ml-2 font-normal">[{coupon.phase?.toUpperCase()}]</span></span>
      </div>
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Calendar size={12} /> {new Date(coupon.created_at).toLocaleDateString()}
      </div>
    </div>
    <div className="p-6 space-y-3">
      {(coupon.legs || []).map((leg, i) => {
        const won = leg.leg_won;
        const hasResult = leg.result != null;
        return (
          <div key={i} className={`flex justify-between items-start rounded-xl px-4 py-3 ${won === true ? 'bg-emerald-500/5 border border-emerald-500/15' : won === false ? 'bg-rose-500/5 border border-rose-500/15' : 'bg-white/[0.02] border border-white/5'}`}>
            <div className="flex items-start gap-3 flex-1 min-w-0">
              <div className="mt-0.5 shrink-0">
                {won === true
                  ? <CheckCircle2 size={16} className="text-emerald-400" />
                  : won === false
                    ? <XCircle size={16} className="text-rose-400" />
                    : <Clock size={16} className="text-amber-400 animate-pulse" />}
              </div>
              <div className="min-w-0">
                <p className="text-base font-bold text-slate-200 truncate">{leg.home} - {leg.away}</p>
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  <span className="text-sm text-slate-500">Typ:</span>
                  <span className="text-sm font-semibold text-slate-300">{leg.tip}</span>
                  {hasResult && (
                    <>
                      <span className="text-sm text-slate-600">→</span>
                      <span className={`text-sm font-bold ${won === true ? 'text-emerald-400' : won === false ? 'text-rose-400' : 'text-slate-400'}`}>{leg.result}</span>
                    </>
                  )}
                </div>
              </div>
            </div>
            <div className="text-sm font-bold bg-indigo-500/10 text-indigo-300 px-3 py-1.5 rounded-lg shrink-0 ml-2">@{leg.odds}</div>
          </div>
        );
      })}
    </div>
    <div className="px-6 py-5 bg-white/[0.04] flex justify-between items-center mt-auto border-t border-white/5">
      <div className="flex gap-10">
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-1">Kurs</p>
          <p className="metric-num text-2xl font-bold text-white">{coupon.total_odds?.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-1">Stawka</p>
          <p className="text-2xl font-bold text-indigo-400 tracking-tighter">{coupon.stake_pln} <span className="text-xs">PLN</span></p>
        </div>
      </div>
      <div className="text-right">
        <div className={`text-xs font-bold px-4 py-2 rounded-xl ${['WON','WIN'].includes(coupon.status) ? 'bg-emerald-500/10 text-emerald-400' : 'bg-white/5 text-slate-500'}`}>
          {['WON','WIN'].includes(coupon.status) ? 'ZWROT: ' + coupon.payout_pln + ' PLN' : coupon.status}
        </div>
      </div>
    </div>
  </motion.div>
);

export const ConfigInput = ({ label, value, onChange, tooltip, type = "text" }) => (
  <div>
    <label className="flex items-center gap-1.5 text-xs font-bold text-slate-500 uppercase mb-2">
      {label}
      {tooltip && (
        <span title={tooltip} className="inline-flex text-slate-500 cursor-help">
          <Info size={13} />
        </span>
      )}
    </label>
    <input
      type={type}
      value={value || ''}
      onChange={e => onChange(e.target.value)}
      className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-indigo-500 transition-colors"
    />
  </div>
);
