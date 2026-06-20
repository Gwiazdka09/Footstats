export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

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
