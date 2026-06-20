import React, { useState, useEffect } from 'react';
import { ShieldCheck, Users, Trash2, UserPlus } from 'lucide-react';
import { motion } from 'framer-motion';

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

export default AdminPanelView;
