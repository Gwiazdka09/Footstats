export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

/**
 * Adres strony prawnej (regulamin, polityka prywatności).
 *
 * Te strony serwuje API, nie front, więc ścieżka względna by ich nie znalazła.
 * Wcześniej w trzech miejscach siedział zaszyty na sztywno surowy adres Cloud Run —
 * po zmianie hostingu wszystkie trzy linki umarłyby po cichu, każdy osobno.
 * Teraz dzielą los aplikacji: jeśli `API_BASE` jest zły, i tak nic nie działa.
 *
 * `API_BASE` kończy się na `/api`, a strony prawne stoją w korzeniu — stąd
 * odcięcie sufiksu.
 */
export const legalUrl = (sciezka) =>
  `${API_BASE.replace(/\/api\/?$/, "")}/${sciezka}`;

// Dekoduje payload JWT (bez weryfikacji podpisu — tylko do odczytu claimów typu "adm")
export const decodeJwtPayload = (token) => {
  try {
    const payload = token.split('.')[1];
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
};
