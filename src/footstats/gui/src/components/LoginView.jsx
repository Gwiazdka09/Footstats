import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { API_BASE } from '../lib/api';

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

export default LoginView;
