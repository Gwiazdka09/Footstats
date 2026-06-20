import React, { useState, useEffect } from 'react';
import { Settings, Wallet, TrendingUp, Trash2, Info, User } from 'lucide-react';
import { motion } from 'framer-motion';
import { ConfigInput } from './ui';

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

  // FAZA 15.6: per-user Telegram chat_id
  const [telegramChatId, setTelegramChatId] = useState('');
  const [telegramMsg, setTelegramMsg] = useState('');
  const [telegramLoading, setTelegramLoading] = useState(false);

  useEffect(() => { if (me?.telegram_chat_id) setTelegramChatId(me.telegram_chat_id); }, [me]);

  const handleSaveTelegram = async () => {
    setTelegramLoading(true);
    setTelegramMsg('');
    try {
      await apiFetch('/auth/telegram', {
        method: 'POST',
        body: JSON.stringify({ chat_id: telegramChatId }),
      });
      setMe(m => ({ ...m, telegram_chat_id: telegramChatId || null }));
      setTelegramMsg(telegramChatId ? 'Telegram chat ID zapisany!' : 'Telegram odłączony.');
    } catch (err) {
      setTelegramMsg('Błąd: ' + err.message);
    } finally {
      setTelegramLoading(false);
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

          <div className="mt-8 pt-8 border-t border-white/5">
            <h4 className="text-sm font-bold text-slate-300 uppercase tracking-widest mb-2">Powiadomienia Telegram</h4>
            <p className="text-xs text-[var(--text-muted)] mb-4">
              Podaj swój chat ID (od @userinfobot), aby otrzymywać powiadomienia o kuponach na Telegram.
            </p>
            <div className="space-y-3 max-w-md">
              <ConfigInput
                label="Telegram chat ID"
                value={telegramChatId}
                onChange={setTelegramChatId}
              />
              <button
                onClick={handleSaveTelegram}
                disabled={telegramLoading}
                className="btn-primary"
              >
                {telegramLoading ? "Zapisywanie..." : "Zapisz Telegram"}
              </button>
              {telegramMsg && <p className="text-sm text-indigo-400">{telegramMsg}</p>}
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

export default SettingsView;
