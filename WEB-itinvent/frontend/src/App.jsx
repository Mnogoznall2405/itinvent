/**
 * Main App component with routing and authentication.
 */
import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { Box } from '@mui/material';
import { AuthProvider, useAuth } from './contexts/AuthContext';



// Pages
const Login = lazy(() => import('./pages/Login'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Tasks = lazy(() => import('./pages/Tasks'));
const Database = lazy(() => import('./pages/Database'));
const Networks = lazy(() => import('./pages/Networks'));
const Settings = lazy(() => import('./pages/Settings'));
const Statistics = lazy(() => import('./pages/Statistics'));
const Computers = lazy(() => import('./pages/Computers'));
const ScanCenter = lazy(() => import('./pages/ScanCenter'));
const Mfu = lazy(() => import('./pages/Mfu'));
const Mail = lazy(() => import('./pages/Mail'));
const AdUsers = lazy(() => import('./pages/AdUsers'));
const Vcs = lazy(() => import('./pages/Vcs'));

const routePermissions = [
  { path: '/dashboard', permission: 'dashboard.read' },
  { path: '/tasks', permission: 'tasks.read' },
  { path: '/database', permission: 'database.read' },
  { path: '/networks', permission: 'networks.read' },
  { path: '/mfu', permission: 'database.read' },
  { path: '/computers', permission: 'computers.read' },
  { path: '/scan-center', permission: 'scan.read' },
  { path: '/statistics', permission: 'statistics.read' },
  { path: '/settings', permission: 'settings.read' },
  { path: '/ad-users', permission: 'ad_users.read' },
  { path: '/vcs', permission: 'vcs.read' },
  { path: '/mail', permission: 'mail.access' },
];

const resolveFirstAccessiblePath = (hasPermission) => {
  const match = routePermissions.find((item) => hasPermission(item.permission));
  return match ? match.path : '/login';
};

/**
 * Protected Route component - redirects to login if not authenticated
 */
const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>Loading...</Box>;
  }

  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }

  return children || <Outlet />;
};

const HomeRedirect = () => {
  const { hasPermission } = useAuth();
  return <Navigate to={resolveFirstAccessiblePath(hasPermission)} replace />;
};

const PermissionRoute = ({ permission, children }) => {
  const { hasPermission } = useAuth();

  if (!permission || hasPermission(permission)) {
    return children || <Outlet />;
  }
  return <Navigate to={resolveFirstAccessiblePath(hasPermission)} replace />;
};

const PageFallback = () => (
  <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
    Загрузка...
  </Box>
);

function App() {
  const rawBase = String(import.meta.env.BASE_URL || '/');
  const normalizedBase = rawBase === './' || rawBase === '.' ? '/' : rawBase;
  const routerBase = normalizedBase.endsWith('/') && normalizedBase.length > 1 ? normalizedBase.slice(0, -1) : normalizedBase;

  return (
    <BrowserRouter basename={routerBase === '/' ? undefined : routerBase} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <AuthProvider>
        <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
          <Suspense fallback={<PageFallback />}>
            <Routes>
              {/* Public route */}
              <Route path="/login" element={<Login />} />

              {/* Protected routes */}
              <Route element={<ProtectedRoute />}>
                <Route path="/" element={<HomeRedirect />} />
                <Route path="/dashboard" element={<PermissionRoute permission="dashboard.read"><Dashboard /></PermissionRoute>} />
                <Route path="/tasks" element={<PermissionRoute permission="tasks.read"><Tasks /></PermissionRoute>} />
                <Route path="/database" element={<PermissionRoute permission="database.read"><Database /></PermissionRoute>} />
                <Route path="/networks" element={<PermissionRoute permission="networks.read"><Networks /></PermissionRoute>} />
                <Route path="/networks/:branchId" element={<PermissionRoute permission="networks.read"><Networks /></PermissionRoute>} />
                <Route path="/ad-users" element={<PermissionRoute permission="ad_users.read"><AdUsers /></PermissionRoute>} />
                <Route path="/vcs" element={<PermissionRoute permission="vcs.read"><Vcs /></PermissionRoute>} />
                <Route path="/mfu" element={<PermissionRoute permission="database.read"><Mfu /></PermissionRoute>} />
                <Route path="/computers" element={<PermissionRoute permission="computers.read"><Computers /></PermissionRoute>} />
                <Route path="/scan-center" element={<PermissionRoute permission="scan.read"><ScanCenter /></PermissionRoute>} />
                <Route path="/statistics" element={<PermissionRoute permission="statistics.read"><Statistics /></PermissionRoute>} />
                <Route path="/mail" element={<PermissionRoute permission="mail.access"><Mail /></PermissionRoute>} />
                <Route path="/settings" element={<PermissionRoute permission="settings.read"><Settings /></PermissionRoute>} />
              </Route>

              <Route path="*" element={<HomeRedirect />} />
            </Routes>
          </Suspense>
        </Box>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
