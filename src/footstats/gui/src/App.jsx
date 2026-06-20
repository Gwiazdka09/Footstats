import React, { useState, useEffect } from 'react';
import {
  LayoutDashboard, History, Settings, Menu, PlusCircle, LogOut, ChevronLeft, ChevronRight, ShieldCheck, Trophy, X
} from 'lucide-react';
import { AnimatePresence } from 'framer-motion';

import { API_BASE, decodeJwtPayload } from './lib/api';
import { NavItem } from './components/ui';
import LoginView from './components/LoginView';
import DashboardHome from './components/DashboardHome';
import CouponWizard from './components/Wizard/CouponWizard';
import HistoryView from './components/HistoryView';
import LeaderboardView from './components/LeaderboardView';
import SettingsView from './components/SettingsView';
import AdminPanelView from './components/AdminPanelView';

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

export default App;
