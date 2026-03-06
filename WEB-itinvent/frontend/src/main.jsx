import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { PreferencesProvider } from './contexts/PreferencesContext'
import './index.css'

const CHUNK_RELOAD_TS_KEY = 'itinvent_chunk_reload_ts';
const CHUNK_RELOAD_WINDOW_MS = 15000;

const tryRecoverChunkLoad = () => {
  try {
    const now = Date.now();
    const prev = Number(sessionStorage.getItem(CHUNK_RELOAD_TS_KEY) || '0');
    if (!Number.isFinite(prev) || (now - prev) > CHUNK_RELOAD_WINDOW_MS) {
      sessionStorage.setItem(CHUNK_RELOAD_TS_KEY, String(now));
      window.location.reload();
      return;
    }
  } catch (error) {
    console.error('Chunk reload recovery failed', error);
  }
};

window.addEventListener('vite:preloadError', (event) => {
  event.preventDefault();
  tryRecoverChunkLoad();
});

window.addEventListener('unhandledrejection', (event) => {
  const reason = event?.reason;
  const message = String(reason?.message || reason || '');
  if (message.includes('Failed to fetch dynamically imported module')) {
    event.preventDefault?.();
    tryRecoverChunkLoad();
  }
});

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <PreferencesProvider>
      <App />
    </PreferencesProvider>
  </React.StrictMode>,
)
