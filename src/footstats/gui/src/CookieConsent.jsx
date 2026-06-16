import React, { useState } from 'react';

const STORAGE_KEY = 'fs_cookie_consent';

const CookieConsent = () => {
  const [visible, setVisible] = useState(() => !localStorage.getItem(STORAGE_KEY));

  if (!visible) return null;

  const accept = () => {
    localStorage.setItem(STORAGE_KEY, 'accepted');
    setVisible(false);
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 z-[400] p-4 flex justify-center">
      <div className="glass-card w-full max-w-3xl p-4 sm:p-5 flex flex-col sm:flex-row items-center gap-4">
        <p className="text-sm text-[var(--text-muted)] flex-1">
          Używamy niezbędnych plików cookie / local storage (np. token sesji), aby aplikacja działała.
          Szczegóły w{' '}
          <a href="https://footstats-api-949240532526.europe-west1.run.app/polityka-prywatnosci" target="_blank" rel="noreferrer" className="text-[var(--accent-primary)] hover:underline">
            polityce prywatności
          </a>.
        </p>
        <button onClick={accept} className="btn-primary shrink-0">
          Rozumiem
        </button>
      </div>
    </div>
  );
};

export default CookieConsent;
