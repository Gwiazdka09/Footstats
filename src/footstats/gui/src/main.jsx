import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import CookieConsent from './CookieConsent.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
    <CookieConsent />
  </React.StrictMode>,
)
