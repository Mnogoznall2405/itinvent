import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { createTheme } from '@mui/material/styles';
import { settingsAPI } from '../api/client';

const PreferencesContext = createContext(null);
const CACHE_KEY = 'web_preferences_cache';

const DEFAULT_PREFERENCES = {
  pinned_database: null,
  theme_mode: 'light',
  font_family: 'Inter',
  font_scale: 1.0,
};

const FONT_MAP = {
  Inter: '"Inter", "Segoe UI", "Roboto", sans-serif',
  Roboto: '"Roboto", "Segoe UI", Arial, sans-serif',
  'Segoe UI': '"Segoe UI", "Roboto", Arial, sans-serif',
};

function readCachedPreferences() {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return DEFAULT_PREFERENCES;
    const parsed = JSON.parse(raw);
    return { ...DEFAULT_PREFERENCES, ...parsed };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

function cachePreferences(value) {
  localStorage.setItem(CACHE_KEY, JSON.stringify(value));
}

export function PreferencesProvider({ children }) {
  const [preferences, setPreferences] = useState(() => readCachedPreferences());
  const [loading, setLoading] = useState(false);

  const refreshFromServer = useCallback(async () => {
    const hasUser = !!localStorage.getItem('user');
    if (!hasUser) return;
    setLoading(true);
    try {
      const data = await settingsAPI.getMySettings();
      const next = { ...DEFAULT_PREFERENCES, ...data };
      setPreferences(next);
      cachePreferences(next);
      if (next.pinned_database) {
        localStorage.setItem('selected_database', next.pinned_database);
      }
    } catch (error) {
      console.error('Failed to load preferences:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshFromServer();
    const authChanged = () => refreshFromServer();
    window.addEventListener('auth-changed', authChanged);
    return () => window.removeEventListener('auth-changed', authChanged);
  }, [refreshFromServer]);

  const savePreferences = useCallback(async (patch) => {
    const optimistic = { ...preferences, ...patch };
    setPreferences(optimistic);
    cachePreferences(optimistic);

    if (patch.pinned_database !== undefined) {
      const nextDb = patch.pinned_database;
      if (nextDb) localStorage.setItem('selected_database', nextDb);
      else localStorage.removeItem('selected_database');
    }

    const hasUser = !!localStorage.getItem('user');
    if (!hasUser) return optimistic;

    try {
      const saved = await settingsAPI.updateMySettings(patch);
      const next = { ...DEFAULT_PREFERENCES, ...saved };
      setPreferences(next);
      cachePreferences(next);
      return next;
    } catch (error) {
      console.error('Failed to save preferences:', error);
      throw error;
    }
  }, [preferences]);

  const theme = useMemo(() => {
    const mode = preferences.theme_mode === 'dark' ? 'dark' : 'light';
    const fontScale = Math.min(1.2, Math.max(0.9, Number(preferences.font_scale || 1)));
    const fontFamily = FONT_MAP[preferences.font_family] || FONT_MAP.Inter;

    return createTheme({
      palette: {
        mode,
        primary: { main: '#1976d2' },
        secondary: { main: '#00796b' },
        background: mode === 'dark'
          ? { default: '#111827', paper: '#1f2937' }
          : { default: '#f5f7fa', paper: '#ffffff' },
      },
      typography: {
        fontFamily,
        fontSize: Math.round(14 * fontScale),
      },
      shape: {
        borderRadius: 8,
      },
      components: {
        MuiButton: {
          styleOverrides: {
            root: { textTransform: 'none', fontWeight: 500 },
          },
        },
      },
    });
  }, [preferences.theme_mode, preferences.font_family, preferences.font_scale]);

  const value = useMemo(() => ({
    preferences,
    loading,
    savePreferences,
    refreshFromServer,
  }), [preferences, loading, savePreferences, refreshFromServer]);

  return (
    <PreferencesContext.Provider value={value}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </PreferencesContext.Provider>
  );
}

export function usePreferences() {
  const context = useContext(PreferencesContext);
  if (!context) {
    throw new Error('usePreferences must be used within PreferencesProvider');
  }
  return context;
}

export default PreferencesContext;
