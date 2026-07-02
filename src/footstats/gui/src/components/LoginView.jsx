import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { API_BASE } from '../lib/api';

const LoginView = ({ setToken, setUser }) => {
  const [mode, setMode] = useState('login'); // 'login' | 'register' | 'forgot' | 'reset'
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);

  // Link resetu (email) → /reset-password?token=... — wykryj token i przełącz tryb.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get('token');
    if (t && window.location.pathname.includes('reset-password')) {
      setResetToken(t);
      setMode('reset');
    }
  }, []);

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

  const post = (path, body) => fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  const switchMode = (m) => { setMode(m); setError(''); setNotice(''); };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setNotice('');
    try {
      if (mode === 'forgot') {
        const response = await post('/auth/forgot-password', { email });
        const data = await response.json().catch(() => ({}));
        setNotice(data.message || 'Jeśli konto istnieje, wysłaliśmy link resetu na e-mail.');
        return;
      }
      if (mode === 'reset') {
        const response = await post('/auth/reset-password', { token: resetToken, new_password: password });
        if (!response.ok) throw new Error(await extractError(response, 'Nie udało się zresetować hasła'));
        setNotice('Hasło zmienione. Możesz się zalogować.');
        setMode('login');
        setPassword('');
        return;
      }
      const isRegister = mode === 'register';
      const response = await post(`/auth/${isRegister ? 'register' : 'login'}`, isRegister ? { username, email, password } : { username, password });
      if (!response.ok) {
        throw new Error(await extractError(response, isRegister ? 'Nie udało się utworzyć konta' : 'Błędne dane logowania'));
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

  const subtitle = {
    login: 'Witaj ponownie. Zaloguj się do systemu.',
    register: 'Stwórz konto, by zacząć korzystać z FootStats.',
    forgot: 'Podaj e-mail — wyślemy link do resetu hasła.',
    reset: 'Ustaw nowe hasło do swojego konta.',
  }[mode];

  const submitLabel = {
    login: loading ? 'Logowanie...' : 'Zaloguj się',
    register: loading ? 'Tworzenie konta...' : 'Zarejestruj się',
    forgot: loading ? 'Wysyłanie...' : 'Wyślij link resetu',
    reset: loading ? 'Zapisywanie...' : 'Ustaw nowe hasło',
  }[mode];

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
          <p className="text-slate-400">{subtitle}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {(mode === 'login' || mode === 'register') && (
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
          )}
          {(mode === 'register' || mode === 'forgot') && (
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
          {(mode === 'login' || mode === 'register' || mode === 'reset') && (
            <div>
              <label className="block text-xs font-bold text-slate-500 uppercase mb-2">
                {mode === 'reset' ? 'Nowe hasło' : 'Hasło'}
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:outline-none focus:border-indigo-500 transition-colors"
                placeholder={mode === 'login' ? '••••••••' : 'min. 8 znaków'}
                minLength={mode === 'login' ? undefined : 8}
                required
              />
            </div>
          )}
          {error && <p className="text-rose-400 text-sm">{error}</p>}
          {notice && <p className="text-emerald-400 text-sm">{notice}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-4 bg-indigo-500 hover:bg-indigo-600 rounded-xl font-bold transition-all shadow-lg shadow-indigo-500/20 disabled:opacity-50"
          >
            {submitLabel}
          </button>
        </form>

        {mode === 'login' && (
          <p className="text-center text-sm text-slate-500 mt-4">
            <button type="button" onClick={() => switchMode('forgot')} className="hover:text-indigo-300">
              Zapomniałeś hasła?
            </button>
          </p>
        )}

        <p className="text-center text-sm text-slate-400 mt-6">
          {mode === 'login' && (<>Nie masz konta?{' '}
            <button type="button" onClick={() => switchMode('register')} className="text-indigo-400 hover:text-indigo-300 font-bold">Zarejestruj się</button></>)}
          {mode === 'register' && (<>Masz już konto?{' '}
            <button type="button" onClick={() => switchMode('login')} className="text-indigo-400 hover:text-indigo-300 font-bold">Zaloguj się</button></>)}
          {(mode === 'forgot' || mode === 'reset') && (
            <button type="button" onClick={() => switchMode('login')} className="text-indigo-400 hover:text-indigo-300 font-bold">← Wróć do logowania</button>
          )}
        </p>
      </motion.div>
    </div>
  );
};

export default LoginView;
