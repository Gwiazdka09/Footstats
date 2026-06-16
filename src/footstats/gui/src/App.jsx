import React, { useState, useEffect, useMemo } from 'react';
import {
  Wallet, TrendingUp, Calendar, CheckCircle2, XCircle, Clock, ChevronRight, ChevronDown, LayoutDashboard, History, Settings, Menu, PlusCircle, LogOut, ChevronLeft, Send, Sparkles, Target, Trophy, Share2, ShieldCheck, Users, Trash2, UserPlus, X, Info, User
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

// Dekoduje payload JWT (bez weryfikacji podpisu — tylko do odczytu claimów typu "adm")
const decodeJwtPayload = (token) => {
  try {
    const payload = token.split('.')[1];
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
};

// Mapowanie ligi -> flaga kraju (emoji) dla kreatora kuponów
const LEAGUE_FLAGS = {
  "premier league": "🏴",
  "eng-premier league": "🏴",
  "championship": "🏴",
  "la liga": "🇪🇸",
  "esp-la liga": "🇪🇸",
  "bundesliga": "🇩🇪",
  "ger-bundesliga": "🇩🇪",
  "ligue 1": "🇫🇷",
  "fra-ligue 1": "🇫🇷",
  "serie a": "🇮🇹",
  "ita-serie a": "🇮🇹",
  "serie b": "🇮🇹",
  "pko bp ekstraklasa": "🇵🇱",
  "ekstraklasa": "🇵🇱",
  "eredivisie": "🇳🇱",
  "primeira liga": "🇵🇹",
  "jupiler pro league": "🇧🇪",
  "super lig": "🇹🇷",
  "brasileirao serie a": "🇧🇷",
  "bra-brasileirao serie a": "🇧🇷",
  "brasileirao serie b": "🇧🇷",
  "bra-brasileirao serie b": "🇧🇷",
  "liga mx": "🇲🇽",
  "world cup 2026": "🏆",
  "world cup": "🏆",
};

const getLeagueFlag = (liga) => LEAGUE_FLAGS[(liga || "").toLowerCase()] ?? "🌍";

// Polska odmiana rzeczownika "typ" (1 typ / 2-4 typy / 5+ typów)
const odmianaTypy = (n) => {
  if (n === 1) return "1 typ";
  const ostatnia = n % 10;
  const dwieOstatnie = n % 100;
  if (ostatnia >= 2 && ostatnia <= 4 && !(dwieOstatnie >= 12 && dwieOstatnie <= 14)) return `${n} typy`;
  return `${n} typów`;
};

const TIP_CATEGORIES = [
  { label: "Wynik meczu (1X2)", match: (t) => ["1", "1X", "X", "X2", "2"].includes(t.tip) },
  { label: "Obie strzelają", match: (t) => t.tip.startsWith("BTTS") },
  { label: "Liczba goli", match: (t) => /^(Over|Under)/.test(t.tip) },
];

const groupTips = (tips) => {
  const used = new Set();
  const groups = TIP_CATEGORIES.map((cat) => {
    const items = tips.filter((t) => cat.match(t));
    items.forEach((t) => used.add(t));
    return { label: cat.label, items };
  }).filter((g) => g.items.length > 0);
  const rest = tips.filter((t) => !used.has(t));
  if (rest.length > 0) groups.push({ label: "Inne", items: rest });
  return groups;
};

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
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [proposalToCopy, setProposalToCopy] = useState(null);
  const isAdmin = !!(token && decodeJwtPayload(token)?.adm);

  const navItems = [
    { key: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={20} /> },
    { key: 'wizard', label: 'Stwórz Kupon', icon: <PlusCircle size={20} /> },
    { key: 'history', label: 'Historia', icon: <History size={20} /> },
    { key: 'settings', label: 'Ustawienia', icon: <Settings size={20} /> },
    { key: 'leaderboard', label: 'Najlepsi typerzy', icon: <Trophy size={20} /> },
    ...(isAdmin ? [{ key: 'admin', label: 'Panel', icon: <ShieldCheck size={20} /> }] : []),
  ];

  // Authentication logout
  const handleLogout = () => {
    localStorage.removeItem('fs_token');
    localStorage.removeItem('fs_user');
    setToken(null);
    setUser('Użytkownik');
  };

  // Po zmianie nazwy użytkownika — nowy token (zawiera nowy login) + odśwież lokalny stan
  const handleAccountUpdate = ({ access_token, username }) => {
    localStorage.setItem('fs_token', access_token);
    localStorage.setItem('fs_user', username);
    setToken(access_token);
    setUser(username);
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
            {sidebarCollapsed ? <ChevronRight size={20} /> : <ChevronLeft size={20} />}
          </button>
        </div>
        
        <nav className="space-y-4 mb-12 flex-1">
          {navItems.map(item => (
            <NavItem
              key={item.key}
              icon={item.icon}
              label={item.label}
              active={view === item.key}
              collapsed={sidebarCollapsed}
              onClick={() => setView(item.key)}
            />
          ))}
        </nav>
        
        {/* User Info & Logout */}
        {!sidebarCollapsed && (
          <div className="mt-auto p-4 bg-white/5 rounded-xl border border-white/5">
            <p className="text-xs text-slate-500 uppercase tracking-tighter">Właściciel</p>
            <p className="font-bold text-slate-300 mb-2">{user}</p>
            <button 
              onClick={handleLogout}
              className="flex items-center gap-2 text-xs font-semibold text-rose-400 hover:text-rose-300 transition-colors w-full pt-2 border-t border-white/5"
            >
              <LogOut size={14} /> Wyloguj się
            </button>
          </div>
        )}
      </aside>

      {/* Mobile fullscreen nav overlay */}
      {mobileNavOpen && (
        <div className="mobile-nav-overlay">
          <div className="mobile-nav-header">
            <div className="brand text-2xl font-bold bg-gradient-to-r from-indigo-400 to-pink-400 bg-clip-text text-transparent">
              FootStats
            </div>
            <button onClick={() => setMobileNavOpen(false)} className="p-2 hover:bg-white/5 rounded-lg text-slate-400">
              <X size={24} />
            </button>
          </div>
          <nav>
            {navItems.map(item => (
              <NavItem
                key={item.key}
                icon={item.icon}
                label={item.label}
                active={view === item.key}
                collapsed={false}
                onClick={() => { setView(item.key); setMobileNavOpen(false); }}
              />
            ))}
          </nav>
          <div className="mt-auto p-4 bg-white/5 rounded-xl border border-white/5">
            <p className="text-xs text-slate-500 uppercase tracking-tighter">Właściciel</p>
            <p className="font-bold text-slate-300 mb-2">{user}</p>
            <button
              onClick={() => { setMobileNavOpen(false); handleLogout(); }}
              className="flex items-center gap-2 text-xs font-semibold text-rose-400 hover:text-rose-300 transition-colors w-full pt-2 border-t border-white/5"
            >
              <LogOut size={14} /> Wyloguj się
            </button>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex flex-col flex-1">
        <div className="mobile-topbar">
          <div className="brand text-xl font-bold bg-gradient-to-r from-indigo-400 to-pink-400 bg-clip-text text-transparent">
            FootStats
          </div>
          <button onClick={() => setMobileNavOpen(true)}>
            <Menu size={22} />
          </button>
        </div>
        <main className={`flex-1 main-content p-4 lg:p-12 ${sidebarCollapsed ? 'lg:ml-24' : 'lg:ml-72'}`}>
        <div className="container">
          <AnimatePresence mode="wait">
            {view === 'dashboard' && (
              <DashboardHome
                key="dash"
                user={user}
                status={status}
                coupons={coupons}
                calibration={calibration}
                isAdmin={isAdmin}
                apiFetch={apiFetch}
                onSeeAll={() => setView('history')}
                onCopyProposal={(p) => { setProposalToCopy(p); setView('wizard'); }}
              />
            )}
            {view === 'wizard' && (
              <CouponWizard
                key="wiz"
                apiFetch={apiFetch}
                initialProposal={proposalToCopy}
                onComplete={() => { setProposalToCopy(null); setView('dashboard'); fetchData(); }}
                onCancel={() => { setProposalToCopy(null); setView('dashboard'); }}
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
                status={status}
                user={user}
                isAdmin={isAdmin}
                onAccountUpdate={handleAccountUpdate}
                onLogout={handleLogout}
                apiFetch={apiFetch}
                onSave={() => fetchData()}
              />
            )}
            {view === 'leaderboard' && (
              <LeaderboardView
                key="leader"
                apiFetch={apiFetch}
              />
            )}
            {view === 'admin' && isAdmin && (
              <AdminPanelView
                key="admin"
                apiFetch={apiFetch}
                onSettled={() => fetchData()}
              />
            )}
          </AnimatePresence>
        </div>
        </main>
        <footer className="py-3 px-6 border-t border-white/5 text-center text-xs text-[var(--text-muted)]">
          FootStats nie jest bukmacherem, nie przyjmuje zakładów. Prognozy nie gwarantują wyników. Hazard 18+.{' '}
          <a href="https://footstats-api-949240532526.europe-west1.run.app/regulamin" target="_blank" rel="noreferrer" className="underline hover:text-[var(--text-main)]">Regulamin</a>
          {' · '}
          <a href="https://footstats-api-949240532526.europe-west1.run.app/polityka-prywatnosci" target="_blank" rel="noreferrer" className="underline hover:text-[var(--text-main)]">Polityka prywatności</a>
        </footer>
      </div>
    </div>
  );
};

// --- Authentication View ---

const LoginView = ({ setToken, setUser }) => {
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const extractError = async (response, fallback) => {
    try {
      const data = await response.json();
      if (typeof data.detail === 'string') return data.detail;
      if (Array.isArray(data.detail)) return data.detail.map(d => d.msg).join(', ');
    } catch {
      // brak JSON w odpowiedzi — użyj domyślnego komunikatu
    }
    return fallback;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    const isRegister = mode === 'register';
    try {
      const response = await fetch(`${API_BASE}/auth/${isRegister ? 'register' : 'login'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(isRegister ? { username, email, password } : { username, password })
      });
      if (!response.ok) {
        throw new Error(await extractError(response, isRegister ? "Nie udało się utworzyć konta" : "Błędne dane logowania"));
      }
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
          <p className="text-slate-400">
            {mode === 'login' ? 'Witaj ponownie. Zaloguj się do systemu.' : 'Stwórz konto, by zacząć korzystać z FootStats.'}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase mb-2">
              {mode === 'login' ? 'Login lub e-mail' : 'Login'}
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:outline-none focus:border-indigo-500 transition-colors"
              placeholder={mode === 'login' ? 'Login lub e-mail' : 'Twój login'}
              required
            />
          </div>
          {mode === 'register' && (
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase mb-2">E-mail</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:outline-none focus:border-indigo-500 transition-colors"
                placeholder="twoj@email.pl"
                required
              />
            </div>
          )}
          <div>
            <label className="block text-xs font-bold text-slate-500 uppercase mb-2">Hasło</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:outline-none focus:border-indigo-500 transition-colors"
              placeholder={mode === 'register' ? 'min. 8 znaków' : '••••••••'}
              minLength={mode === 'register' ? 8 : undefined}
              required
            />
          </div>
          {error && <p className="text-rose-400 text-sm">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-4 bg-indigo-500 hover:bg-indigo-600 rounded-xl font-bold transition-all shadow-lg shadow-indigo-500/20 disabled:opacity-50"
          >
            {loading
              ? (mode === 'login' ? 'Logowanie...' : 'Tworzenie konta...')
              : (mode === 'login' ? 'Zaloguj się' : 'Zarejestruj się')}
          </button>
        </form>

        <p className="text-center text-sm text-slate-400 mt-6">
          {mode === 'login' ? 'Nie masz konta?' : 'Masz już konto?'}{' '}
          <button
            type="button"
            onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}
            className="text-indigo-400 hover:text-indigo-300 font-bold"
          >
            {mode === 'login' ? 'Zarejestruj się' : 'Zaloguj się'}
          </button>
        </p>
      </motion.div>
    </div>
  );
};

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

// --- Wizard Component ---

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
                      <span className="font-bold text-indigo-400">{m.tips[0]?.tip} (@{m.tips[0]?.odds})</span>
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
                  <div className="mt-4">
                    <button
                      onClick={() => setBbOpen(bbOpen === m.id ? null : m.id)}
                      className="btn-see-all text-xs flex items-center gap-1.5"
                    >
                      🎰 {bbOpen === m.id ? 'Ukryj BetBuilder' : 'Zbuduj BetBuilder'}
                    </button>
                    {bbOpen === m.id && (
                      <BetBuilderPanel apiFetch={apiFetch} match={m} onAddCombo={addCombo} />
                    )}
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
          <p className="text-3xl font-bold leading-none">
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

const HistoryCouponRow = ({ c, apiFetch }) => {
  const [expanded, setExpanded] = useState(false);
  const [shared, setShared] = useState(!!c.shared);
  const [sharing, setSharing] = useState(false);
  const isWon = ['WON', 'WIN'].includes(c.status);
  const isLost = ['LOST', 'LOSE'].includes(c.status);
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
          <HistoryCouponRow key={c.id} c={c} apiFetch={apiFetch} />
        )) : (
          <div className="text-center p-24 glass-card text-slate-500">Historia jest pusta.</div>
        )}
      </div>
    </motion.div>
  );
}

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

const SettingsView = ({ config, status, apiFetch, onSave, user, isAdmin, onAccountUpdate, onLogout }) => {
  const [form, setForm] = useState(config || {});
  const [msg, setMsg] = useState('');
  const [loading, setLoading] = useState(false);

  const [bankroll, setBankroll] = useState(status?.bankroll ?? '');
  const [bankrollMsg, setBankrollMsg] = useState('');
  const [bankrollLoading, setBankrollLoading] = useState(false);

  const [me, setMe] = useState(null);

  useEffect(() => {
    apiFetch('/auth/me').then(setMe).catch(() => {});
  }, []);

  const [newUsername, setNewUsername] = useState('');
  const [usernamePassword, setUsernamePassword] = useState('');
  const [usernameMsg, setUsernameMsg] = useState('');
  const [usernameLoading, setUsernameLoading] = useState(false);

  const handleChangeUsername = async () => {
    setUsernameLoading(true);
    setUsernameMsg('');
    try {
      const data = await apiFetch('/auth/change-username', {
        method: 'POST',
        body: JSON.stringify({ current_password: usernamePassword, new_username: newUsername })
      });
      onAccountUpdate({ access_token: data.access_token, username: newUsername });
      setMe(m => ({ ...m, username: newUsername }));
      setNewUsername('');
      setUsernamePassword('');
      setUsernameMsg('Nazwa użytkownika zmieniona!');
    } catch (err) {
      setUsernameMsg('Błąd: ' + err.message);
    } finally {
      setUsernameLoading(false);
    }
  };

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [passwordMsg, setPasswordMsg] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);

  const handleChangePassword = async () => {
    setPasswordLoading(true);
    setPasswordMsg('');
    try {
      await apiFetch('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
      });
      setCurrentPassword('');
      setNewPassword('');
      setPasswordMsg('Hasło zmienione!');
    } catch (err) {
      setPasswordMsg('Błąd: ' + err.message);
    } finally {
      setPasswordLoading(false);
    }
  };

  // RODO: samodzielne usunięcie konta (DELETE /api/auth/me)
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteMsg, setDeleteMsg] = useState('');
  const [deleteLoading, setDeleteLoading] = useState(false);

  const handleDeleteAccount = async () => {
    setDeleteLoading(true);
    setDeleteMsg('');
    try {
      await apiFetch('/auth/me', {
        method: 'DELETE',
        body: JSON.stringify({ password: deletePassword }),
      });
      onLogout();
    } catch (err) {
      setDeleteMsg('Błąd: ' + err.message);
    } finally {
      setDeleteLoading(false);
    }
  };

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

  const handleSaveBankroll = async () => {
    setBankrollLoading(true);
    setBankrollMsg('');
    try {
      await apiFetch('/bankroll', {
        method: 'POST',
        body: JSON.stringify({ balance: parseFloat(bankroll) })
      });
      setBankrollMsg('Bankroll zapisany pomyślnie!');
      onSave();
    } catch (err) {
      setBankrollMsg('Błąd: ' + err.message);
    } finally {
      setBankrollLoading(false);
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
       <div className="space-y-8">
        <div className="glass-card p-8">
          <h3 className="text-lg font-bold mb-6 flex items-center gap-2 text-white"><Settings size={18} /> Algorytm & Ryzyko</h3>
          <div className="space-y-6">
            <ConfigInput
              label="Próg Pewniaczka (%)"
              value={form.pewniaczek_prog}
              onChange={v => setForm({...form, pewniaczek_prog: parseFloat(v)})}
              tooltip="Mecze z pewnością AI powyżej tego progu są oznaczane jako 'Pewniaki' — najwyższa kategoria zaufania w typach."
            />
            <ConfigInput
              label="Próg Kandydatów (%)"
              value={form.kandydat_prog}
              onChange={v => setForm({...form, kandydat_prog: parseFloat(v)})}
              tooltip="Minimalna pewność AI, by mecz pojawił się jako kandydat do analizy w kreatorze kuponów."
            />
            <ConfigInput
              label="Fractional Kelly (f/x)"
              value={form.kelly_fraction}
              onChange={v => setForm({...form, kelly_fraction: parseInt(v)})}
              tooltip="Część kryterium Kelly'ego do liczenia rekomendowanej stawki (np. 4 = 1/4 Kelly'ego). Niższa wartość = mniejsze rekomendowane stawki."
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
        <div className="glass-card p-8">
          <h3 className="text-lg font-bold mb-6 flex items-center gap-2 text-white">
            <Wallet size={18} /> Edycja Bankrolla
            <span
              title="Bankroll to Twój budżet używany WYŁĄCZNIE do liczenia rekomendowanych stawek (Kelly) w kreatorze kuponów. FootStats nie przyjmuje zakładów i nie obsługuje prawdziwych pieniędzy — to wartość pomocnicza do analizy."
              className="inline-flex text-slate-500 cursor-help"
            >
              <Info size={14} />
            </span>
          </h3>
          <div className="space-y-6">
            <ConfigInput
              label="Saldo (PLN)"
              value={bankroll}
              onChange={v => setBankroll(v)}
              tooltip="Wpisz aktualny budżet, jakim dysponujesz u swojego bukmachera — na tej podstawie liczone są rekomendowane stawki."
            />
            <button
              onClick={handleSaveBankroll}
              disabled={bankrollLoading}
              className="btn-primary w-full mt-4"
            >
              {bankrollLoading ? "Zapisywanie..." : "Zapisz bankroll"}
            </button>
            {bankrollMsg && <p className="text-sm text-center text-indigo-400">{bankrollMsg}</p>}
            <p className="text-slate-400 text-xs">
              Służy tylko do obliczania rekomendowanych stawek — FootStats nie przyjmuje zakładów na swojej stronie.
              Zaktualizuj po wpłacie/wypłacie z konta u bukmachera.
            </p>
          </div>
        </div>
       </div>
        <div className="glass-card p-8 h-full">
          <h3 className="text-lg font-bold mb-6 flex items-center gap-2 text-white"><TrendingUp size={18} /> Dane konta</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-8">
            <div className="bg-white/5 rounded-xl p-4 text-center">
              <p className="text-xs text-slate-500 uppercase tracking-widest mb-1">Balans</p>
              <p className="text-lg font-bold text-white">{status?.bankroll?.toFixed(2)} <span className="text-xs font-normal text-slate-500">PLN</span></p>
            </div>
            <div className="bg-white/5 rounded-xl p-4 text-center">
              <p className="text-xs text-slate-500 uppercase tracking-widest mb-1">ROI</p>
              <p className={`text-lg font-bold ${status?.stats?.roi_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {status?.stats?.roi_pct >= 0 ? '+' : ''}{status?.stats?.roi_pct}%
              </p>
            </div>
            <div className="bg-white/5 rounded-xl p-4 text-center">
              <p className="text-xs text-slate-500 uppercase tracking-widest mb-1">Wygrane (30 dni)</p>
              <p className="text-lg font-bold text-indigo-300">{status?.stats?.wins_last_30d || 0}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            <div className="bg-white/5 rounded-xl p-4">
              <p className="text-xs text-slate-500 uppercase tracking-widest mb-1 flex items-center gap-1.5"><User size={13} /> Login</p>
              <p className="text-base font-bold text-white">{me?.username || user || '—'}</p>
            </div>
            <div className="bg-white/5 rounded-xl p-4">
              <p className="text-xs text-slate-500 uppercase tracking-widest mb-1">E-mail</p>
              <p className="text-base font-bold text-white">{me?.email || '—'}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
              <h4 className="text-sm font-bold text-slate-300 uppercase tracking-widest mb-4">Zmiana nazwy użytkownika</h4>
              <div className="space-y-4">
                <ConfigInput
                  label="Nowy login"
                  value={newUsername}
                  onChange={setNewUsername}
                />
                <ConfigInput
                  label="Aktualne hasło"
                  type="password"
                  value={usernamePassword}
                  onChange={setUsernamePassword}
                />
                <button
                  onClick={handleChangeUsername}
                  disabled={usernameLoading || !newUsername || !usernamePassword}
                  className="btn-primary w-full"
                >
                  {usernameLoading ? "Zapisywanie..." : "Zmień nazwę użytkownika"}
                </button>
                {usernameMsg && <p className="text-sm text-center text-indigo-400">{usernameMsg}</p>}
              </div>
            </div>
            <div>
              <h4 className="text-sm font-bold text-slate-300 uppercase tracking-widest mb-4">Zmiana hasła</h4>
              <div className="space-y-4">
                <ConfigInput
                  label="Aktualne hasło"
                  type="password"
                  value={currentPassword}
                  onChange={setCurrentPassword}
                />
                <ConfigInput
                  label="Nowe hasło (min. 8 znaków)"
                  type="password"
                  value={newPassword}
                  onChange={setNewPassword}
                />
                <button
                  onClick={handleChangePassword}
                  disabled={passwordLoading || !currentPassword || newPassword.length < 8}
                  className="btn-primary w-full"
                >
                  {passwordLoading ? "Zapisywanie..." : "Zmień hasło"}
                </button>
                {passwordMsg && <p className="text-sm text-center text-indigo-400">{passwordMsg}</p>}
              </div>
            </div>
          </div>

          {!isAdmin && (
            <div className="mt-8 pt-8 border-t border-rose-500/20">
              <h4 className="text-sm font-bold text-rose-400 uppercase tracking-widest mb-2 flex items-center gap-2">
                <Trash2 size={16} /> Strefa niebezpieczna
              </h4>
              <p className="text-xs text-[var(--text-muted)] mb-4">
                Usunięcie konta jest nieodwracalne — Twoje dane (login, e-mail) zostaną zanonimizowane,
                a konto dezaktywowane (RODO, prawo do bycia zapomnianym).
              </p>
              {!deleteOpen ? (
                <button
                  onClick={() => setDeleteOpen(true)}
                  className="px-4 py-2.5 rounded-lg text-sm font-semibold border border-rose-500/40 text-rose-400 hover:bg-rose-500/10 transition-colors"
                >
                  Usuń moje konto
                </button>
              ) : (
                <div className="space-y-3">
                  <ConfigInput
                    label="Potwierdź hasłem"
                    type="password"
                    value={deletePassword}
                    onChange={setDeletePassword}
                  />
                  <div className="flex gap-3">
                    <button
                      onClick={handleDeleteAccount}
                      disabled={deleteLoading || !deletePassword}
                      className="px-4 py-2.5 rounded-lg text-sm font-bold bg-rose-500 hover:bg-rose-600 text-white transition-colors disabled:opacity-50"
                    >
                      {deleteLoading ? "Usuwanie..." : "Potwierdzam — usuń konto"}
                    </button>
                    <button
                      onClick={() => { setDeleteOpen(false); setDeletePassword(''); setDeleteMsg(''); }}
                      className="px-4 py-2.5 rounded-lg text-sm font-semibold text-slate-400 hover:text-white transition-colors"
                    >
                      Anuluj
                    </button>
                  </div>
                  {deleteMsg && <p className="text-sm text-rose-400">{deleteMsg}</p>}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
};

// --- Admin Panel View ---

const AdminPanelView = ({ apiFetch, onSettled }) => {
  const [settling, setSettling] = useState(false);
  const [settleMsg, setSettleMsg] = useState('');
  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [usersError, setUsersError] = useState('');
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newIsAdmin, setNewIsAdmin] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createMsg, setCreateMsg] = useState('');

  const loadUsers = async () => {
    setUsersLoading(true);
    setUsersError('');
    try {
      const data = await apiFetch('/admin/users');
      setUsers(data);
    } catch (err) {
      setUsersError(err.message);
    } finally {
      setUsersLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const handleSettle = async () => {
    setSettling(true);
    setSettleMsg('');
    try {
      const res = await apiFetch('/coupons/settle', {
        method: 'POST',
        body: JSON.stringify({ days_back: 10, dry_run: false })
      });
      setSettleMsg(res.message || 'Sprawdzanie zakończone.');
      onSettled();
    } catch (err) {
      setSettleMsg('Błąd: ' + err.message);
    } finally {
      setSettling(false);
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    setCreating(true);
    setCreateMsg('');
    try {
      await apiFetch('/admin/users', {
        method: 'POST',
        body: JSON.stringify({ username: newUsername, password: newPassword, is_admin: newIsAdmin })
      });
      setNewUsername('');
      setNewPassword('');
      setNewIsAdmin(false);
      setCreateMsg('Użytkownik utworzony.');
      loadUsers();
    } catch (err) {
      setCreateMsg('Błąd: ' + err.message);
    } finally {
      setCreating(false);
    }
  };

  const handleDeactivate = async (userId) => {
    try {
      await apiFetch(`/admin/users/${userId}`, { method: 'DELETE' });
      loadUsers();
    } catch (err) {
      setUsersError(err.message);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
    >
      <div className="mb-12">
        <h1 className="text-4xl font-bold mb-2">Panel administratora</h1>
        <p className="text-slate-400">Zarządzanie kontami i rozliczanie kuponów.</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
        <div className="glass-card p-8">
          <h3 className="text-lg font-bold mb-2 flex items-center gap-2"><ShieldCheck size={18} /> Sprawdzanie wyników</h3>
          <p className="text-slate-400 text-sm mb-6">Ręczne sprawdzenie wyników meczów i rozliczenie aktywnych kuponów (API-Football / FlashScore).</p>
          <button
            onClick={handleSettle}
            disabled={settling}
            className="btn-primary px-6 py-3 rounded-xl font-bold disabled:opacity-50"
          >
            {settling ? "Sprawdzanie..." : "Sprawdź wyniki meczów"}
          </button>
          {settleMsg && <p className="text-sm mt-4 text-indigo-400">{settleMsg}</p>}
        </div>
        <div className="glass-card p-8">
          <h3 className="text-lg font-bold mb-6 flex items-center gap-2"><UserPlus size={18} /> Nowy użytkownik</h3>
          <form onSubmit={handleCreateUser} className="space-y-4">
            <input
              type="text"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              placeholder="Login (min. 3 znaki)"
              required
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:outline-none focus:border-indigo-500 transition-colors"
            />
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Hasło (min. 8 znaków)"
              required
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:outline-none focus:border-indigo-500 transition-colors"
            />
            <label className="flex items-center gap-2 text-sm text-slate-400">
              <input type="checkbox" checked={newIsAdmin} onChange={(e) => setNewIsAdmin(e.target.checked)} />
              Konto administratora
            </label>
            <button type="submit" disabled={creating} className="btn-primary w-full py-3 rounded-xl font-bold disabled:opacity-50">
              {creating ? "Tworzenie..." : "Utwórz konto"}
            </button>
            {createMsg && <p className="text-sm text-center text-indigo-400">{createMsg}</p>}
          </form>
        </div>
      </div>
      <div className="glass-card p-8">
        <h3 className="text-lg font-bold mb-6 flex items-center gap-2"><Users size={18} /> Zarządzaj użytkownikami</h3>
        {usersLoading ? (
          <p className="text-slate-500">Wczytywanie...</p>
        ) : usersError ? (
          <p className="text-rose-400 text-sm">{usersError}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 uppercase text-xs border-b border-white/5">
                  <th className="py-2 pr-4">ID</th>
                  <th className="py-2 pr-4">Login</th>
                  <th className="py-2 pr-4">Admin</th>
                  <th className="py-2 pr-4">Aktywny</th>
                  <th className="py-2 pr-4"></th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-b border-white/5">
                    <td className="py-3 pr-4 text-slate-500">{u.id}</td>
                    <td className="py-3 pr-4 font-semibold">{u.username}</td>
                    <td className="py-3 pr-4">{u.is_admin ? '✅' : '—'}</td>
                    <td className="py-3 pr-4">{u.is_active ? '✅' : '❌'}</td>
                    <td className="py-3 pr-4 text-right">
                      {u.is_active && (
                        <button
                          onClick={() => handleDeactivate(u.id)}
                          className="text-rose-400 hover:text-rose-300 transition-colors"
                          title="Dezaktywuj konto"
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
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
          <p className="text-2xl font-bold text-white tracking-tighter">{coupon.total_odds?.toFixed(2)}</p>
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

const ConfigInput = ({ label, value, onChange, tooltip, type = "text" }) => (
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

export default App;
