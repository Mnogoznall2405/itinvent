import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const envDir = resolve(currentDir, '..', '..');
  const env = loadEnv(mode, envDir, '');
  const backendHost = env.VITE_BACKEND_HOST || 'localhost';
  const backendPort = env.VITE_BACKEND_PORT || '8001';
  const backendTarget = `http://${backendHost}:${backendPort}`;
  const scanBackendTarget = env.VITE_SCAN_BACKEND_TARGET || 'http://localhost:8011';
  // In production default to absolute root paths to avoid /route/assets/* requests on refresh.
  // If app is deployed to a virtual directory, override with VITE_BASE_PATH (example: /itinvent/).
  const normalizeBasePath = (value) => {
    const raw = String(value || '').trim();
    if (!raw) return '/';
    if (raw === '.' || raw === './') return '/';
    const withLeading = raw.startsWith('/') ? raw : `/${raw}`;
    return withLeading.endsWith('/') ? withLeading : `${withLeading}/`;
  };
  const basePath = mode === 'development' ? '/' : normalizeBasePath(env.VITE_BASE_PATH || '/');

  return {
    envDir,
    base: basePath,
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api/v1/scan': {
          target: scanBackendTarget,
          changeOrigin: true,
        },
        '/api': {
          target: backendTarget,
          changeOrigin: true,
        }
      }
    },
    optimizeDeps: {
      include: ['react', 'react-dom', '@emotion/react', '@emotion/styled'],
    },
  };
});
