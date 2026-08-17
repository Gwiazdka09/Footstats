import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import CookieConsent from './CookieConsent.jsx'
import './index.css'

// Analityka Vercela (`<Analytics />`, `<SpeedInsights />`) USUNIĘTA 17.08.2026.
// Montowała się bezwarunkowo, więc oba skrypty trafiały do DOM zanim ktokolwiek
// dotknął banera zgody — a `fs_cookie_consent` nie bramkowało niczego. Baner
// twierdził przy tym, że używamy wyłącznie plików NIEZBĘDNYCH, i polityka
// prywatności o analityce milczała. Przy kierunku „prywatny użytek + znajomi"
// statystyki odwiedzin nie są do niczego potrzebne, więc zamiast dokładać
// bramkowanie zgody — usuwamy źródło problemu. Teraz treść banera jest prawdziwa.
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
    <CookieConsent />
  </React.StrictMode>,
)
