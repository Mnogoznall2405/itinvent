/**
 * Authentication Context - manages user authentication state across the app.
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authAPI } from '../api/client';

const AuthContext = createContext(null);
const rolePermissionFallback = {
  viewer: [
    'dashboard.read',
    'tasks.read',
    'database.read',
    'networks.read',
    'computers.read',
    'scan.read',
    'statistics.read',
    'settings.read',
    'vcs.read',
  ],
  operator: [
    'dashboard.read',
    'announcements.write',
    'tasks.read',
    'tasks.write',
    'database.read',
    'database.write',
    'networks.read',
    'networks.write',
    'computers.read',
    'scan.read',
    'scan.ack',
    'scan.tasks',
    'statistics.read',
    'kb.read',
    'kb.write',
    'mail.access',
    'settings.read',
  ],
  admin: [
    'dashboard.read',
    'announcements.write',
    'tasks.read',
    'tasks.write',
    'tasks.review',
    'database.read',
    'database.write',
    'networks.read',
    'networks.write',
    'computers.read',
    'computers.read_all',
    'scan.read',
    'scan.ack',
    'scan.tasks',
    'statistics.read',
    'kb.read',
    'kb.write',
    'kb.publish',
    'mail.access',
    'settings.read',
    'settings.users.manage',
    'settings.sessions.manage',
    'vcs.read',
    'vcs.manage',
  ],
};

const normalizeUserWithPermissions = (value) => {
  if (!value || typeof value !== 'object') return null;
  const role = String(value.role || 'viewer').trim().toLowerCase() || 'viewer';
  const rawPermissions = Array.isArray(value.permissions) ? value.permissions : rolePermissionFallback[role] || rolePermissionFallback.viewer;
  const permissions = [...new Set(rawPermissions.map((item) => String(item || '').trim()).filter(Boolean))];
  return { ...value, role, permissions };
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Restore cached user and validate active cookie session
  useEffect(() => {
    const savedUser = localStorage.getItem('user');

    if (savedUser) {
      try {
        setUser(normalizeUserWithPermissions(JSON.parse(savedUser)));
      } catch (e) {
        console.error('Failed to parse saved user:', e);
        localStorage.removeItem('user');
      }
    }

    const verifySession = async () => {
      try {
        const currentUser = normalizeUserWithPermissions(await authAPI.getCurrentUser());
        setUser(currentUser || null);
        if (currentUser && typeof currentUser === 'object') {
          localStorage.setItem('user', JSON.stringify(currentUser));
        } else {
          localStorage.removeItem('user');
        }
      } catch {
        setUser(null);
        localStorage.removeItem('user');
      } finally {
        setLoading(false);
      }
    };

    verifySession();
  }, []);

  useEffect(() => {
    const onAuthRequired = () => {
      localStorage.removeItem('user');
      setUser(null);
      setLoading(false);
      window.dispatchEvent(new Event('auth-changed'));
    };
    window.addEventListener('auth-required', onAuthRequired);
    return () => window.removeEventListener('auth-required', onAuthRequired);
  }, []);

  /**
   * Login with username and password
   */
  const login = useCallback(async (username, password) => {
    setError(null);
    try {
      const response = await authAPI.login(username, password);
      const user = normalizeUserWithPermissions(response?.user);

      // Store user only; token lives in HttpOnly cookie.
      localStorage.setItem('user', JSON.stringify(user));

      setUser(user);
      window.dispatchEvent(new Event('auth-changed'));
      return { success: true, user };
    } catch (err) {
      const message = err.response?.data?.detail || 'Ошибка входа';
      setError(message);
      return { success: false, error: message };
    }
  }, []);

  /**
   * Logout current user
   */
  const logout = useCallback(async () => {
    try {
      await authAPI.logout();
    } catch (err) {
      console.error('Logout error:', err);
    } finally {
      // Always clear local user cache
      localStorage.removeItem('user');
      setUser(null);
      window.dispatchEvent(new Event('auth-changed'));
    }
  }, []);

  /**
   * Check if user is authenticated
   */
  const isAuthenticated = useCallback(() => {
    return !!user;
  }, [user]);

  const hasPermission = useCallback((permission) => {
    const target = String(permission || '').trim();
    if (!target) return false;
    const permissions = Array.isArray(user?.permissions) ? user.permissions : [];
    return permissions.includes(target);
  }, [user]);

  const hasAnyPermission = useCallback((permissions) => {
    if (!Array.isArray(permissions) || permissions.length === 0) return false;
    return permissions.some((permission) => hasPermission(permission));
  }, [hasPermission]);

  const value = {
    user,
    loading,
    error,
    login,
    logout,
    isAuthenticated,
    hasPermission,
    hasAnyPermission,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export default AuthContext;
