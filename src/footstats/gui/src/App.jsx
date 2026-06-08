import React, { useState, useEffect } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area 
} from 'recharts';
import { 
  Wallet, TrendingUp, Calendar, CheckCircle2, XCircle, Clock, Info, ChevronRight, LayoutDashboard, History, Settings, Menu, PlusCircle, LogOut, ChevronLeft, Send, Sparkles, Target
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

const App = () => {
  const [token, setToken] = useState(localStorage.getItem('fs_token'));
  const [user, setUser] = useState(localStorage.getItem('fs_user') || 'Użytkownik');
  const [status, setStatus] = useState(null);
  const [coupons, setCoupons] = useState([]);
  const [history, setHistory] = useState([]);
  const [config, setConfig] = useState(null);
  const [calibration, setCalibration] = useState(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('dashboard'); // 'dashboard', 'history', 'settings', 'wizard'
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Authentication logout
  const handleLogout = () => {
    localStorage.removeItem('fs_token');
    localStorage.removeItem('fs_user');
    setToken(null);
    setUser('Użytkownik');
  };

  // Generic fetcher with auth
  const apiFetch = async (endpoint, options = {}) => {
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers
    });

    if (response.status === 401) {
      handleLogout();
      throw new Error("Sesja wygasła. Zaloguj się ponownie.");
    }

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Błąd serwera" }));
      throw new Error(err.detail || "Coś poszło nie tak");
    }

    return response.json();
  };

  const fetchData = async () => {
    if (!token) return;
    try {
      const [statusData, couponsData, historyData, configData, calibrationData] = await Promise.all([
        apiFetch('/status'),
        apiFetch('/coupons/active'),
        apiFetch('/bankroll/history'),
        apiFetch('/settings').catch(() => apiFetch('/config')),
        apiFetch('/calibration').catch(() => null),
      ]);

      setStatus(statusData);
      setCoupons(couponsData);
      setHistory(historyData);
      setConfig(configData);
      setCalibration(calibrationData);
    } catch (error) {
      console.error("Błąd podczas pobierania danych:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (token) {
      fetchData();
      const interval = setInterval(fetchData, 30000);
      return () => clearInterval(interval);
    } else {
      setLoading(false);
    }
  }, [token]);

  if (!token) {
    return <LoginView setToken={(t) => { localStorage.setItem('fs_token', t); setToken(t); }} setUser={(u) => { localStorage.setItem('fs_user', u); setUser(u); }} />;
  }

  if (loading) return (
    <div className="flex items-center justify-center h-screen bg-[#020617] text-white">
      <div className="text-2xl font-bold animate-pulse">Ładowanie Twojego Imperium...</div>
    </div>
  );

  return (
    <div className="flex min-h-screen bg-[#0f172a] text-slate-100 overflow-x-hidden">
      
      {/* Sidebar - Full Height */}
      <aside className={`sidebar hidden lg:flex flex-col glass-card p-6 fixed h-screen border-y-0 border-l-0 rounded-none z-50 ${sidebarCollapsed ? 'collapsed' : 'w-64'}`}>
        <div className="flex justify-between items-center mb-12">
          {!sidebarCollapsed && (
            <div className="brand text-3xl font-bold bg-gradient-to-r from-indigo-400 to-pink-400 bg-clip-text text-transparent">
              FootStats
            </div>
          )}
          <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)} className="p-2 hover:bg-white/5 rounded-lg text-slate-400">
            <Menu size={20} />
          </button>
        </div>
        
        <nav className="space-y-4 mb-12 flex-1">
          <NavItem 
            icon={<LayoutDashboard size={20} />} 
            label="Dashboard" 
            active={view === 'dashboard'} 
            collapsed={sidebarCollapsed}
            onClick={() => setView('dashboard')}
          />
          <NavItem 
            icon={<PlusCircle size={20} />} 
            label="Stwórz Kupon" 
            active={view === 'wizard'} 
            collapsed={sidebarCollapsed}
            onClick={() => setView('wizard')}
          />
          <NavItem 
            icon={<History size={20} />} 
            label="Historia" 
            active={view === 'history'} 
            collapsed={sidebarCollapsed}
            onClick={() => setView('history')}
          />
          <NavItem 
            icon={<Settings size={20} />} 
            label="Ustawienia" 
            active={view === 'settings'} 
            collapsed={sidebarCollapsed}
            onClick={() => setView('settings')}
          />
        </nav>
        
        {/* User Info & Logout */}
        {!sidebarCollapsed && (
          <div className="mt-auto p-4 bg-white/5 rounded-xl border border-white/5">
            <p className="text-xs text-slate-500 uppercase tracking-tighter">Właściciel</p>
            <p className="font-bold text-slate-300 mb-2">{user}</p>
            <button 
              onClick={handleLogout}
              className="flex items-center gap-2 text-xs text-slate-500 hover:text-rose-400 transition-colors w-full pt-2 border-t border-white/5"
            >
              <LogOut size={14} /> Wyloguj się
            </button>
          </div>
        )}
      </aside>

      {/* Main Content Area */}
      <main className={`flex-1 main-content p-4 lg:p-12 ${sidebarCollapsed ? 'lg:ml-24' : 'lg:ml-72'}`}>
        <div className="container">
          <AnimatePresence mode="wait">
            {view === 'dashboard' && (
              <DashboardHome
                key="dash"
                user={user}
                status={status}
                history={history}
                coupons={coupons}
                calibration={calibration}
                onSeeAll={() => setView('history')}
                onCreateNew={() => setView('wizard')}
              />
            )}
            {view === 'wizard' && (
              <CouponWizard 
                key="wiz"
                apiFetch={apiFetch}
                onComplete={() => { setView('dashboard'); fetchData(); }}
                onCancel={() => setView('dashboard')}
              />
            )}
            {view === 'history' && (
              <HistoryView 
                key="hist"
                apiFetch={apiFetch}
              />
            )}
            {view === 'settings' && (
              <SettingsView 
                key="sett"
                config={config} 
                apiFetch={apiFetch}
                onSave={() => fetchData()}
              />
            )}
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
};

// --- Authentication View ---

const LoginView = ({ setToken, setUser }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      if (!response.ok) throw new Error("Błędne dane logowania");
      const data = await response.json();
      setUser(username);
      setToken(data.access_token);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-[#020617]">
      <motion.div 
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="glass-card p-10 w-full max-w-md border-indigo-500/30"
      >
        <div className="text-center mb-10">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-indigo-400 to-pink-400 bg-clip-text text-transparent mb-2">
            FootStats
          </h1>
          <p className="text-slate-400">Witaj ponownie. Zaloguj się do systemu.</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-6">
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase mb-2">Użytkownik</label>
            <input 
              type="text" 
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:outline-none focus:border-indigo-500 transition-colors"
              placeholder="Twój login"
              required
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase mb-2">Hasło</label>
            <input 
              type="password" 
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:outline-none focus:border-indigo-500 transition-colors"
              placeholder="••••••••"
              required
            />
          </div>
          {error && <p className="text-rose-400 text-sm">{error}</p>}
          <button 
            type="submit" 
            disabled={loading}
            className="w-full py-4 bg-indigo-500 hover:bg-indigo-600 rounded-xl font-bold transition-all shadow-lg shadow-indigo-500/20 disabled:opacity-50"
          >
            {loading ? "Logowanie..." : "Zaloguj się"}
          </button>
        </form>
      </motion.div>
    </div>
  );
};

// --- Wizard Component ---

const CouponWizard = ({ apiFetch, onComplete, onCancel }) => {
  const [step, setStep] = useState(1);
  const [matches, setMatches] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [analysis, setAnalysis] = useState([]);
  const [selections, setSelections] = useState([]);
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
    loadMatches();
  }, []);

  const toggleMatch = (id) => {
    setSelectedIds(prev => 
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
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
            <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold transition-all ${step === s ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/20 scale-110' : step > s ? 'bg-emerald-500 text-white' : 'bg-white/5 text-slate-500'}`}>
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
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {matches.map(m => (
                  <div 
                    key={m.id} 
                    onClick={() => toggleMatch(m.id)}
                    className={`glass-card p-6 cursor-pointer border-2 transition-all ${selectedIds.includes(m.id) ? 'border-indigo-500 bg-indigo-500/5' : 'border-transparent'}`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <span className="text-[10px] font-bold uppercase tracking-widest text-indigo-400">{m.liga}</span>
                      <span className="text-[10px] text-slate-500">{m.godzina}</span>
                    </div>
                    <p className="font-bold text-lg">{m.gosp} vs {m.gosc}</p>
                  </div>
                ))}
              </div>
            )}
            <div className="flex justify-end pt-8">
              <button 
                onClick={handleAnalyze}
                disabled={selectedIds.length === 0 || loading}
                className="btn-primary px-8 py-4 flex items-center gap-2 disabled:opacity-50"
              >
                Analizuj wybrane ({selectedIds.length}) <ChevronRight size={18} />
              </button>
            </div>
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
                      <p className="text-xs text-slate-500">{m.liga}</p>
                    </div>
                    <div className="text-right">
                      <span className="text-xs text-slate-500 block">Sugerowany typ:</span>
                      <span className="font-bold text-indigo-400">{m.tips[0]?.tip} (@{m.tips[0]?.odds})</span>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    {m.tips.map((t, idx) => {
                      const isSelected = selections.find(s => s.match_id === m.id && s.tip === t.tip);
                      return (
                        <button 
                          key={idx}
                          onClick={() => selectTip(m.id, t.tip, t.odds, t.prob, m.home, m.away)}
                          className={`flex-1 min-w-[120px] p-4 rounded-xl border transition-all text-center ${isSelected ? 'bg-indigo-500 border-indigo-400 text-white shadow-lg' : 'bg-white/5 border-white/10 text-slate-400 hover:bg-white/10'}`}
                        >
                          <span className="block font-bold">{t.tip}</span>
                          <span className="text-sm opacity-80">@{t.odds}</span>
                          <div className="mt-2 h-1 bg-black/20 rounded-full overflow-hidden">
                            <div className="h-full bg-white/40" style={{ width: `${t.prob}%` }} />
                          </div>
                          <span className="text-[10px] mt-1 block">{t.prob}%</span>
                        </button>
                      );
                    })}
                  </div>
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

// --- Sub Views ---

const DashboardHome = ({ user, status, history, coupons, calibration, onSeeAll, onCreateNew }) => (
  <motion.div 
    initial={{ opacity: 0, x: 20 }}
    animate={{ opacity: 1, x: 0 }}
    exit={{ opacity: 0, x: -20 }}
  >
    <header className="flex flex-col md:flex-row justify-between items-start md:items-center mb-16 gap-4">
      <div>
        <h1 className="text-4xl font-bold mb-2">Witaj, {user}</h1>
        <p className="text-slate-400">Twoje imperium bukmacherskie jest online.</p>
      </div>
      <div className="flex gap-4">
        <button 
          onClick={onCreateNew}
          className="btn-primary flex items-center gap-2 px-6 py-4"
        >
          <PlusCircle size={20} /> Stwórz Kupon
        </button>
        <div className="glass-card px-10 py-6 flex items-center gap-5 border-indigo-500/20 bg-indigo-500/5">
          <div className="p-4 bg-indigo-500/20 rounded-2xl">
            <Wallet className="text-indigo-400" size={28} />
          </div>
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-widest font-bold mb-1">Dostępny Balans</p>
            <p className="text-3xl font-bold text-white leading-none">
              {status?.bankroll?.toFixed(2)} <span className="text-lg font-normal text-indigo-300">PLN</span>
            </p>
          </div>
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

    {calibration && (
      <section className="glass-card p-6 mb-8 flex flex-wrap gap-6 items-center">
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400 uppercase tracking-widest font-bold">Model Poisson</span>
          <span className="text-xs text-slate-500">|</span>
          <span className="text-xs text-slate-300">
            Ostatnia kalibracja:{' '}
            <span className="text-indigo-300 font-semibold">
              {calibration.updated_at ? new Date(calibration.updated_at).toLocaleDateString('pl-PL') : '—'}
            </span>
          </span>
        </div>
        <div className="flex gap-6 text-xs text-slate-400">
          <span>Próbka: <span className="text-white font-semibold">{calibration.n_matches} meczów</span></span>
          <span>λ dom: <span className="text-emerald-400 font-semibold">{calibration.factor_home?.toFixed(4)}</span></span>
          <span>λ goście: <span className="text-pink-400 font-semibold">{calibration.factor_away?.toFixed(4)}</span></span>
          {calibration.acc_1x2_pct != null && (
            <span>Dokładność 1X2: <span className="text-indigo-300 font-semibold">{calibration.acc_1x2_pct}%</span></span>
          )}
        </div>
      </section>
    )}

    <section className="glass-card p-10 mb-16">
      <h2 className="text-xl font-bold mb-10 flex items-center gap-2">
        <TrendingUp size={24} className="text-indigo-400" /> Progresja Bankrolla
      </h2>
      <div className="h-[350px] w-full">
        {history && history.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={history}>
              <defs>
                <linearGradient id="colorBal" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#818cf8" stopOpacity={0.4}/>
                  <stop offset="95%" stopColor="#818cf8" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis dataKey="timestamp" hide />
              <YAxis hide domain={['auto', 'auto']} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '12px', color: '#fff', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.5)' }}
                labelFormatter={(label) => new Date(label).toLocaleDateString()}
              />
              <Area type="monotone" dataKey="new_balance" stroke="#818cf8" strokeWidth={4} fillOpacity={1} fill="url(#colorBal)" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-full text-slate-600">Brak danych historycznych</div>
        )}
      </div>
    </section>

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

const HistoryCouponRow = ({ c }) => {
  const [expanded, setExpanded] = useState(false);
  const isWon = ['WON', 'WIN'].includes(c.status);
  const isLost = ['LOST', 'LOSE'].includes(c.status);
  const legs = c.legs || [];
  const wonCount = legs.filter(l => l.leg_won === true).length;
  const lostCount = legs.filter(l => l.leg_won === false).length;

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
                <span className="text-slate-600">({legs.length} typów)</span>
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
          {legs.length > 0 && (
            <ChevronRight size={16} className={`text-slate-600 transition-transform ${expanded ? 'rotate-90' : ''}`} />
          )}
        </div>
      </div>

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

const HistoryView = ({ apiFetch }) => {
  const [coupons, setCoupons] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch('/coupons?limit=50').then(data => {
      setCoupons(data);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="text-center py-20">Ładowanie historii...</div>;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
    >
      <div className="mb-12">
        <h1 className="text-4xl font-bold mb-2">Pełna Historia</h1>
        <p className="text-slate-400">Podgląd wszystkich Twoich kuponów. Kliknij kupon by rozwinąć typy.</p>
      </div>
      <div className="grid grid-cols-1 gap-4">
        {coupons.length > 0 ? coupons.map((c) => (
          <HistoryCouponRow key={c.id} c={c} />
        )) : (
          <div className="text-center p-24 glass-card text-slate-500">Historia jest pusta.</div>
        )}
      </div>
    </motion.div>
  );
}

const SettingsView = ({ config, apiFetch, onSave }) => {
  const [form, setForm] = useState(config || {});
  const [msg, setMsg] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSave = async () => {
    setLoading(true);
    try {
      await apiFetch('/settings', {
        method: 'POST',
        body: JSON.stringify(form)
      });
      setMsg('Ustawienia zapisane pomyślnie!');
      onSave();
    } catch (err) {
      setMsg('Błąd: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
    >
      <div className="mb-12">
        <h1 className="text-4xl font-bold mb-2">Ustawienia Bota</h1>
        <p className="text-slate-400">Konfiguracja parametrów bota dla Twojego konta.</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="glass-card p-8">
          <h3 className="text-lg font-bold mb-6 flex items-center gap-2"><Settings size={18} /> Algorytm & Ryzyko</h3>
          <div className="space-y-6">
            <ConfigInput 
              label="Próg Pewniaczka (%)" 
              value={form.pewniaczek_prog} 
              onChange={v => setForm({...form, pewniaczka_prog: parseFloat(v)})}
            />
            <ConfigInput 
              label="Próg Kandydatów (%)" 
              value={form.kandydat_prog} 
              onChange={v => setForm({...form, kandydat_prog: parseFloat(v)})}
            />
            <ConfigInput 
              label="Fractional Kelly (f/x)" 
              value={form.kelly_fraction} 
              onChange={v => setForm({...form, kelly_fraction: parseInt(v)})}
            />
            <button 
              onClick={handleSave}
              disabled={loading}
              className="btn-primary w-full mt-4"
            >
              {loading ? "Zapisywanie..." : "Zapisz ustawienia"}
            </button>
            {msg && <p className="text-sm text-center text-indigo-400">{msg}</p>}
          </div>
        </div>
        <div className="glass-card p-8 text-center flex flex-col items-center justify-center">
          <Info size={48} className="text-indigo-400 mb-6" />
          <p className="text-slate-400">Te ustawienia wpływają na sposób, w jaki bot wybiera mecze i sugeruje stawki Kelly'ego na Twoim koncie.</p>
        </div>
      </div>
    </motion.div>
  );
};

// --- Helpers ---

const NavItem = ({ icon, label, active, collapsed, onClick }) => (
  <div 
    onClick={onClick}
    className={`nav-item flex items-center gap-4 px-4 py-3 rounded-xl cursor-pointer transition-all ${active ? 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/25' : 'text-slate-400 hover:bg-white/5 hover:text-white'}`}
  >
    <div className={active ? 'text-indigo-400' : 'text-slate-500'}>{icon}</div>
    {!collapsed && <span className="nav-label font-semibold">{label}</span>}
  </div>
);

const StatCard = ({ title, value, subtitle, icon, color, delay }) => (
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
    <div className="text-4xl font-bold mb-2 tracking-tight">{value}</div>
    <p className="text-slate-400 text-xs">{subtitle}</p>
  </motion.div>
);

const CouponCard = ({ coupon, index }) => (
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
    <div className="p-6 space-y-4">
      {(coupon.legs || []).map((leg, i) => {
        const won = leg.leg_won;
        const hasResult = leg.result != null;
        return (
          <div key={i} className={`flex justify-between items-start rounded-xl px-3 py-2 ${won === true ? 'bg-emerald-500/5 border border-emerald-500/15' : won === false ? 'bg-rose-500/5 border border-rose-500/15' : 'bg-white/[0.02] border border-white/5'}`}>
            <div className="flex items-start gap-3 flex-1 min-w-0">
              <div className="mt-0.5 shrink-0">
                {won === true
                  ? <CheckCircle2 size={16} className="text-emerald-400" />
                  : won === false
                    ? <XCircle size={16} className="text-rose-400" />
                    : <Clock size={16} className="text-amber-400 animate-pulse" />}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-bold text-slate-200 truncate">{leg.home} - {leg.away}</p>
                <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                  <span className="text-xs text-slate-500">Typ:</span>
                  <span className="text-xs font-semibold text-slate-300">{leg.tip}</span>
                  {hasResult && (
                    <>
                      <span className="text-xs text-slate-600">→</span>
                      <span className={`text-xs font-bold ${won === true ? 'text-emerald-400' : won === false ? 'text-rose-400' : 'text-slate-400'}`}>{leg.result}</span>
                    </>
                  )}
                </div>
              </div>
            </div>
            <div className="text-sm font-bold bg-indigo-500/10 text-indigo-300 px-3 py-1 rounded-lg shrink-0 ml-2">@{leg.odds}</div>
          </div>
        );
      })}
    </div>
    <div className="px-6 py-5 bg-white/[0.04] flex justify-between items-center mt-auto border-t border-white/5">
      <div className="flex gap-10">
        <div>
          <p className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-1">Kurs</p>
          <p className="text-2xl font-bold text-white tracking-tighter">{coupon.total_odds?.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-1">Stawka</p>
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

const ConfigInput = ({ label, value, onChange }) => (
  <div>
    <label className="block text-xs font-bold text-slate-500 uppercase mb-2">{label}</label>
    <input 
      type="text" 
      value={value || ''} 
      onChange={e => onChange(e.target.value)}
      className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:outline-none focus:border-indigo-500 transition-colors"
    />
  </div>
);

export default App;
