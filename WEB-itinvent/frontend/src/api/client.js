/**
 * Axios API client for backend communication.
 */

import axios from 'axios';

const rawBase = String(import.meta.env.BASE_URL || '/');
const normalizedBase = rawBase === './' || rawBase === '.' ? '/' : rawBase;
const basePrefix = normalizedBase.endsWith('/') && normalizedBase.length > 1
  ? normalizedBase.slice(0, -1)
  : normalizedBase;

// Use app-relative /api by default so IIS virtual directories work too.
const derivedApiBase = basePrefix === '/' ? '/api' : `${basePrefix}/api`;
const API_BASE_URL = import.meta.env.VITE_API_URL || derivedApiBase;
export const API_V1_BASE = `${API_BASE_URL}/v1`;
const SCAN_HOSTS_404_KEY = 'itinvent_scan_hosts_404';
const SCAN_HOSTS_404_TTL_MS = 6 * 60 * 60 * 1000;

const readScanHosts404Flag = () => {
  try {
    const raw = String(window.localStorage.getItem(SCAN_HOSTS_404_KEY) || '').trim();
    const ts = Number(raw);
    if (!Number.isFinite(ts) || ts <= 0) return false;
    return (Date.now() - ts) < SCAN_HOSTS_404_TTL_MS;
  } catch {
    return false;
  }
};

let scanHostsEndpointUnavailable = readScanHosts404Flag();

const createClientRequestId = () => {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {
    // Fallback below.
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
};

const markScanHostsUnavailable = (value) => {
  scanHostsEndpointUnavailable = Boolean(value);
  try {
    if (scanHostsEndpointUnavailable) {
      window.localStorage.setItem(SCAN_HOSTS_404_KEY, String(Date.now()));
    } else {
      window.localStorage.removeItem(SCAN_HOSTS_404_KEY);
    }
  } catch {
    // no-op
  }
};

/**
 * Create axios instance with default configuration
 */
const apiClient = axios.create({
  baseURL: API_V1_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
  timeout: 30000,
});

/**
 * Request interceptor - add selected database to all requests
 */
apiClient.interceptors.request.use(
  (config) => {
    // For multipart uploads let the browser set boundary automatically.
    if (typeof FormData !== 'undefined' && config?.data instanceof FormData) {
      if (config.headers?.delete) {
        config.headers.delete('Content-Type');
        config.headers.delete('content-type');
      } else if (config.headers?.set) {
        config.headers.set('Content-Type', undefined);
        config.headers.set('content-type', undefined);
      } else if (config.headers) {
        delete config.headers['Content-Type'];
        delete config.headers['content-type'];
      }
    }

    const selectedDatabase = localStorage.getItem('selected_database');
    if (selectedDatabase) {
      config.headers['X-Database-ID'] = selectedDatabase;
    }
    if (!config.headers['X-Client-Request-ID']) {
      config.headers['X-Client-Request-ID'] = createClientRequestId();
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

/**
 * Response interceptor - handle 401 errors
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const requestUrl = String(error.config?.url || '');
      const isAuthBootstrapRequest =
        requestUrl.includes('/auth/me') ||
        requestUrl.includes('/settings/me') ||
        requestUrl.includes('/auth/login');

      // Session expired or invalid - clear cached user and notify app state.
      localStorage.removeItem('user');
      if (!isAuthBootstrapRequest) {
        window.dispatchEvent(new CustomEvent('auth-required', { detail: { requestUrl } }));
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;
export { apiClient };

/**
 * Auth API methods
 */
export const authAPI = {
  login: async (username, password) => {
    const response = await apiClient.post('/auth/login', { username, password });
    return response.data;
  },

  logout: async () => {
    const response = await apiClient.post('/auth/logout');
    return response.data;
  },

  getCurrentUser: async () => {
    const response = await apiClient.get('/auth/me');
    return response.data;
  },

  changePassword: async (oldPassword, newPassword) => {
    const response = await apiClient.post('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    });
    return response.data;
  },

  getSessions: async () => {
    const response = await apiClient.get('/auth/sessions');
    return response.data;
  },

  terminateSession: async (sessionId) => {
    const response = await apiClient.delete(`/auth/sessions/${encodeURIComponent(sessionId)}`);
    return response.data;
  },

  getUsers: async () => {
    const response = await apiClient.get('/auth/users');
    return response.data;
  },

  createUser: async (payload) => {
    const response = await apiClient.post('/auth/users', payload);
    return response.data;
  },

  updateUser: async (userId, payload) => {
    const response = await apiClient.patch(`/auth/users/${userId}`, payload);
    return response.data;
  },

  deleteUser: async (userId) => {
    const response = await apiClient.delete(`/auth/users/${userId}`);
    return response.data;
  },

  syncAD: async () => {
    const response = await apiClient.post('/auth/sync-ad');
    return response.data;
  },
};

export const settingsAPI = {
  getMySettings: async () => {
    const response = await apiClient.get('/settings/me');
    return response.data;
  },
  updateMySettings: async (payload) => {
    const response = await apiClient.patch('/settings/me', payload);
    return response.data;
  },
};

export const kbAPI = {
  getServices: async () => {
    const response = await apiClient.get('/kb/services');
    return response.data;
  },

  getCards: async (params = {}) => {
    const response = await apiClient.get('/kb/cards', { params });
    return response.data;
  },

  getCard: async (cardId) => {
    const response = await apiClient.get(`/kb/cards/${encodeURIComponent(cardId)}`);
    return response.data;
  },

  createCard: async (payload) => {
    const response = await apiClient.post('/kb/cards', payload);
    return response.data;
  },

  updateCard: async (cardId, payload) => {
    const response = await apiClient.patch(`/kb/cards/${encodeURIComponent(cardId)}`, payload);
    return response.data;
  },

  setCardStatus: async (cardId, payload) => {
    const response = await apiClient.post(`/kb/cards/${encodeURIComponent(cardId)}/status`, payload);
    return response.data;
  },

  getCategories: async () => {
    const response = await apiClient.get('/kb/categories');
    return response.data;
  },

  getArticles: async (params = {}) => {
    const response = await apiClient.get('/kb/articles', { params });
    return response.data;
  },

  getArticle: async (articleId) => {
    const response = await apiClient.get(`/kb/articles/${encodeURIComponent(articleId)}`);
    return response.data;
  },

  createArticle: async (payload) => {
    const response = await apiClient.post('/kb/articles', payload);
    return response.data;
  },

  updateArticle: async (articleId, payload) => {
    const response = await apiClient.patch(`/kb/articles/${encodeURIComponent(articleId)}`, payload);
    return response.data;
  },

  setArticleStatus: async (articleId, payload) => {
    const response = await apiClient.post(`/kb/articles/${encodeURIComponent(articleId)}/status`, payload);
    return response.data;
  },

  getFeed: async (params = {}) => {
    const response = await apiClient.get('/kb/feed', { params });
    return response.data;
  },

  uploadAttachment: async (articleId, file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post(`/kb/articles/${encodeURIComponent(articleId)}/attachments`, formData);
    return response.data;
  },

  downloadAttachment: async (articleId, attachmentId) => {
    const response = await apiClient.get(
      `/kb/articles/${encodeURIComponent(articleId)}/attachments/${encodeURIComponent(attachmentId)}`,
      { responseType: 'blob' },
    );
    return response;
  },

  removeAttachment: async (articleId, attachmentId) => {
    const response = await apiClient.delete(
      `/kb/articles/${encodeURIComponent(articleId)}/attachments/${encodeURIComponent(attachmentId)}`
    );
    return response.data;
  },
};

export const hubAPI = {
  getDashboard: async (params = {}) => {
    const response = await apiClient.get('/hub/dashboard', { params });
    return response.data;
  },

  getAnnouncements: async (params = {}) => {
    const response = await apiClient.get('/hub/announcements', { params });
    return response.data;
  },

  createAnnouncement: async (payload, files = []) => {
    const hasFiles = Array.isArray(files) && files.length > 0;
    if (!hasFiles) {
      const response = await apiClient.post('/hub/announcements', payload);
      return response.data;
    }
    const formData = new FormData();
    formData.append('title', String(payload?.title || ''));
    formData.append('preview', String(payload?.preview || ''));
    formData.append('body', String(payload?.body || ''));
    formData.append('priority', String(payload?.priority || 'normal'));
    files.forEach((file) => {
      if (file) {
        formData.append('files', file);
      }
    });
    const response = await apiClient.post('/hub/announcements', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  updateAnnouncement: async (announcementId, payload) => {
    const response = await apiClient.patch(`/hub/announcements/${encodeURIComponent(announcementId)}`, payload);
    return response.data;
  },

  deleteAnnouncement: async (announcementId) => {
    const response = await apiClient.delete(`/hub/announcements/${encodeURIComponent(announcementId)}`);
    return response.data;
  },

  markAnnouncementRead: async (announcementId) => {
    const response = await apiClient.post(`/hub/announcements/${encodeURIComponent(announcementId)}/mark-as-read`);
    return response.data;
  },

  getAnnouncementReads: async (announcementId) => {
    const response = await apiClient.get(`/hub/announcements/${encodeURIComponent(announcementId)}/reads`);
    return response.data;
  },

  downloadAnnouncementAttachment: async (announcementId, attachmentId) => {
    const response = await apiClient.get(
      `/hub/announcements/${encodeURIComponent(announcementId)}/attachments/${encodeURIComponent(attachmentId)}/file`,
      { responseType: 'blob' },
    );
    return response;
  },

  getAssignees: async () => {
    const response = await apiClient.get('/hub/users/assignees');
    return response.data;
  },

  getControllers: async () => {
    const response = await apiClient.get('/hub/users/controllers');
    return response.data;
  },

  transformMarkdown: async ({ text, context }) => {
    const response = await apiClient.post('/hub/markdown/transform', {
      text: String(text || ''),
      context: String(context || ''),
    });
    return response.data;
  },

  getTasks: async (params = {}) => {
    const response = await apiClient.get('/hub/tasks', { params });
    return response.data;
  },

  createTask: async (payload) => {
    const response = await apiClient.post('/hub/tasks', payload);
    return response.data;
  },

  updateTask: async (taskId, payload) => {
    const response = await apiClient.patch(`/hub/tasks/${encodeURIComponent(taskId)}`, payload);
    return response.data;
  },

  deleteTask: async (taskId) => {
    const response = await apiClient.delete(`/hub/tasks/${encodeURIComponent(taskId)}`);
    return response.data;
  },

  startTask: async (taskId) => {
    const response = await apiClient.post(`/hub/tasks/${encodeURIComponent(taskId)}/start`);
    return response.data;
  },

  submitTask: async ({ taskId, comment = '', file = null }) => {
    const formData = new FormData();
    formData.append('comment', String(comment || ''));
    if (file) {
      formData.append('file', file);
    }
    const response = await apiClient.post(`/hub/tasks/${encodeURIComponent(taskId)}/submit`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  uploadTaskAttachment: async ({ taskId, file }) => {
    const formData = new FormData();
    if (file) {
      formData.append('file', file);
    }
    const response = await apiClient.post(`/hub/tasks/${encodeURIComponent(taskId)}/attachments`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  reviewTask: async (taskId, payload) => {
    const response = await apiClient.post(`/hub/tasks/${encodeURIComponent(taskId)}/review`, payload);
    return response.data;
  },

  downloadTaskAttachment: async ({ taskId, attachmentId }) => {
    const response = await apiClient.get(
      `/hub/tasks/${encodeURIComponent(taskId)}/attachments/${encodeURIComponent(attachmentId)}/file`,
      { responseType: 'blob' },
    );
    return response;
  },

  downloadTaskReport: async (reportId) => {
    const response = await apiClient.get(`/hub/tasks/reports/${encodeURIComponent(reportId)}/file`, {
      responseType: 'blob',
    });
    return response;
  },

  getTaskComments: async (taskId) => {
    const response = await apiClient.get(`/hub/tasks/${encodeURIComponent(taskId)}/comments`);
    return response.data;
  },

  addTaskComment: async (taskId, body) => {
    const response = await apiClient.post(`/hub/tasks/${encodeURIComponent(taskId)}/comments`, { body });
    return response.data;
  },

  getTaskStatusLog: async (taskId) => {
    const response = await apiClient.get(`/hub/tasks/${encodeURIComponent(taskId)}/status-log`);
    return response.data;
  },

  pollNotifications: async (params = {}) => {
    const response = await apiClient.get('/hub/notifications/poll', { params });
    return response.data;
  },

  getUnreadCounts: async () => {
    const response = await apiClient.get('/hub/notifications/unread-counts');
    return response.data;
  },

  markNotificationRead: async (notificationId) => {
    const response = await apiClient.post(`/hub/notifications/${encodeURIComponent(notificationId)}/read`);
    return response.data;
  },
};

export const mailAPI = {
  getInbox: async (params = {}) => {
    const response = await apiClient.get('/mail/inbox', { params });
    return response.data;
  },

  searchContacts: async (q) => {
    const response = await apiClient.get('/mail/contacts', { params: { q } });
    return response.data?.items || [];
  },

  getMessage: async (messageId) => {
    const response = await apiClient.get(`/mail/messages/${encodeURIComponent(messageId)}`);
    return response.data;
  },

  markAsRead: async (messageId) => {
    const response = await apiClient.post(`/mail/messages/${encodeURIComponent(messageId)}/read`);
    return response.data;
  },

  getUnreadCount: async () => {
    const response = await apiClient.get('/mail/unread-count');
    return response.data;
  },

  sendMessage: async (payload) => {
    const response = await apiClient.post('/mail/messages/send', payload);
    return response.data;
  },

  sendMessageMultipart: async ({
    to,
    subject,
    body,
    isHtml,
    files,
    onUploadProgress,
    signal,
  }) => {
    const formData = new FormData();
    formData.append('to', to.join(';'));
    formData.append('subject', subject || '');
    formData.append('body', body || '');
    formData.append('is_html', isHtml ? 'true' : 'false');
    if (files && files.length > 0) {
      files.forEach((file) => {
        formData.append('files', file);
      });
    }
    const response = await apiClient.post('/mail/messages/send-multipart', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress,
      signal,
    });
    return response.data;
  },

  downloadAttachment: async (messageId, attachmentRef) => {
    const response = await apiClient.get(
      `/mail/messages/${encodeURIComponent(messageId)}/attachments/${encodeURIComponent(attachmentRef)}`,
      { responseType: 'blob' }
    );
    return response;
  },

  sendItRequest: async (payload) => {
    const response = await apiClient.post('/mail/messages/send-it-request', payload);
    return response.data;
  },

  sendItRequestMultipart: async ({
    templateId,
    fields,
    files,
    onUploadProgress,
    signal,
  }) => {
    const formData = new FormData();
    formData.append('template_id', String(templateId || ''));
    formData.append('fields_json', JSON.stringify(fields || {}));
    if (Array.isArray(files) && files.length > 0) {
      files.forEach((file) => {
        if (file) {
          formData.append('files', file);
        }
      });
    }
    const response = await apiClient.post('/mail/messages/send-it-request-multipart', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress,
      signal,
    });
    return response.data;
  },

  getTemplates: async (params = {}) => {
    const response = await apiClient.get('/mail/templates', { params });
    return response.data;
  },

  createTemplate: async (payload) => {
    const response = await apiClient.post('/mail/templates', payload);
    return response.data;
  },

  updateTemplate: async (templateId, payload) => {
    const response = await apiClient.patch(`/mail/templates/${encodeURIComponent(templateId)}`, payload);
    return response.data;
  },

  deleteTemplate: async (templateId) => {
    const response = await apiClient.delete(`/mail/templates/${encodeURIComponent(templateId)}`);
    return response.data;
  },

  getMyConfig: async () => {
    const response = await apiClient.get('/mail/config/me');
    return response.data;
  },

  updateMyConfig: async (payload) => {
    const response = await apiClient.patch('/mail/config/me', payload);
    return response.data;
  },

  updateUserConfig: async (userId, payload) => {
    const response = await apiClient.patch(`/mail/config/user/${userId}`, payload);
    return response.data;
  },

  testConnection: async (payload = {}) => {
    const response = await apiClient.post('/mail/test-connection', payload);
    return response.data;
  },
};

export const networksAPI = {
  getBranches: async (city = 'tmn') => {
    const response = await apiClient.get('/networks/branches', { params: { city } });
    return response.data;
  },

  createBranch: async (payload) => {
    const response = await apiClient.post('/networks/branches', payload);
    return response.data;
  },

  updateBranch: async (branchId, data) => {
    const response = await apiClient.patch(`/networks/branches/${branchId}`, data);
    return response.data;
  },

  deleteBranch: async (branchId) => {
    const response = await apiClient.delete(`/networks/branches/${branchId}`);
    return response.data;
  },

  getBranchOverview: async (branchId) => {
    const response = await apiClient.get(`/networks/branches/${branchId}/overview`);
    return response.data;
  },

  getDevices: async (branchId) => {
    const response = await apiClient.get(`/networks/branches/${branchId}/devices`);
    return response.data;
  },

  getPorts: async (deviceId, params = {}) => {
    const response = await apiClient.get(`/networks/devices/${deviceId}/ports`, { params });
    return response.data;
  },

  getBranchPorts: async (branchId, params = {}) => {
    const response = await apiClient.get(`/networks/branches/${branchId}/ports`, { params });
    return response.data;
  },

  getBranchSockets: async (branchId, params = {}) => {
    const response = await apiClient.get(`/networks/branches/${branchId}/sockets`, { params });
    return response.data;
  },

  createSocket: async (branchId, payload) => {
    const response = await apiClient.post(`/networks/branches/${branchId}/sockets`, payload);
    return response.data;
  },

  updateSocket: async (socketId, payload) => {
    const response = await apiClient.patch(`/networks/sockets/${socketId}`, payload);
    return response.data;
  },

  deleteSocket: async (socketId) => {
    const response = await apiClient.delete(`/networks/sockets/${socketId}`);
    return response.data;
  },

  bootstrapSockets: async (branchId, payload = {}) => {
    const response = await apiClient.post(`/networks/branches/${branchId}/sockets/bootstrap`, payload);
    return response.data;
  },

  importSocketsTemplate: async (branchId, formData) => {
    const response = await apiClient.post(`/networks/branches/${branchId}/sockets/import`, formData);
    return response.data;
  },

  importEquipment: async (branchId, formData) => {
    const response = await apiClient.post(`/networks/branches/${branchId}/equipment/import`, formData);
    return response.data;
  },

  getBranchDbMapping: async (branchId) => {
    const response = await apiClient.get(`/networks/branches/${branchId}/db-mapping`);
    return response.data;
  },

  updateBranchDbMapping: async (branchId, payload) => {
    const response = await apiClient.patch(`/networks/branches/${branchId}/db-mapping`, payload);
    return response.data;
  },

  syncSocketHostContext: async (branchId, payload = {}) => {
    const response = await apiClient.post(`/networks/branches/${branchId}/sockets/sync-host-context`, payload);
    return response.data;
  },

  resolveSocketFio: async (branchId, payload = {}) => {
    // Backward compatibility alias; prefer syncSocketHostContext in new code.
    return networksAPI.syncSocketHostContext(branchId, payload);
  },

  getMaps: async (branchId) => {
    const response = await apiClient.get(`/networks/branches/${branchId}/maps`);
    return response.data;
  },

  getMapPoints: async (branchId, mapId = null) => {
    const response = await apiClient.get(`/networks/branches/${branchId}/map-points`, {
      params: { map_id: mapId || undefined },
    });
    return response.data;
  },

  getAudit: async (params = {}) => {
    const response = await apiClient.get('/networks/audit', { params });
    return response.data;
  },

  importData: async (formData) => {
    const response = await apiClient.post('/networks/import', formData);
    return response.data;
  },

  createDevice: async (payload) => {
    const response = await apiClient.post('/networks/devices', payload);
    return response.data;
  },

  updateDevice: async (deviceId, payload) => {
    const response = await apiClient.patch(`/networks/devices/${deviceId}`, payload);
    return response.data;
  },

  deleteDevice: async (deviceId) => {
    const response = await apiClient.delete(`/networks/devices/${deviceId}`);
    return response.data;
  },

  bootstrapDevicePorts: async (deviceId, payload) => {
    const response = await apiClient.post(`/networks/devices/${deviceId}/bootstrap-ports`, payload);
    return response.data;
  },

  createPort: async (payload) => {
    const response = await apiClient.post('/networks/ports', payload);
    return response.data;
  },

  updatePort: async (portId, payload) => {
    const response = await apiClient.patch(`/networks/ports/${portId}`, payload);
    return response.data;
  },

  deletePort: async (portId) => {
    const response = await apiClient.delete(`/networks/ports/${portId}`);
    return response.data;
  },

  uploadMap: async (formData) => {
    const response = await apiClient.post('/networks/maps/upload', formData);
    return response.data;
  },

  updateMap: async (mapId, payload) => {
    const response = await apiClient.patch(`/networks/maps/${mapId}`, payload);
    return response.data;
  },

  deleteMap: async (mapId) => {
    const response = await apiClient.delete(`/networks/maps/${mapId}`);
    return response.data;
  },

  createMapPoint: async (payload) => {
    const response = await apiClient.post('/networks/map-points', payload);
    return response.data;
  },

  updateMapPoint: async (pointId, payload) => {
    const response = await apiClient.patch(`/networks/map-points/${pointId}`, payload);
    return response.data;
  },

  deleteMapPoint: async (pointId) => {
    const response = await apiClient.delete(`/networks/map-points/${pointId}`);
    return response.data;
  },

  downloadMapFile: async (mapId, params = {}) => {
    const response = await apiClient.get(`/networks/maps/${mapId}/file`, {
      params,
      responseType: 'blob',
    });
    return response;
  },
};

/**
 * Equipment API methods
 */
export const equipmentAPI = {
  getAgentComputers: async (options = {}) => {
    const scope = String(options?.scope || 'selected').toLowerCase() === 'all' ? 'all' : 'selected';
    const outlookStatus = String(options?.outlookStatus || '').trim().toLowerCase();
    const params = { scope };
    if (['ok', 'warning', 'critical', 'unknown'].includes(outlookStatus)) {
      params.outlook_status = outlookStatus;
    }
    const response = await apiClient.get('/inventory/computers', {
      params,
    });
    return response.data;
  },

  getAgentComputerChanges: async (limit = 50) => {
    const response = await apiClient.get('/inventory/changes', {
      params: { limit },
    });
    return response.data;
  },

  searchBySerial: async (query) => {
    const response = await apiClient.get('/equipment/search/serial', {
      params: { q: query },
    });
    return response.data;
  },

  searchUniversal: async (query, page = 1, limit = 50) => {
    const response = await apiClient.get('/equipment/search/universal', {
      params: { q: query, page, limit },
    });
    return response.data;
  },

  searchByEmployee: async (query, page = 1, limit = 50) => {
    const response = await apiClient.get('/equipment/search/employee', {
      params: { q: query, page, limit },
    });
    return response.data;
  },

  getEmployeeEquipment: async (ownerNo) => {
    const response = await apiClient.get(`/equipment/employee/${ownerNo}/items`);
    return response.data;
  },

  getByInvNo: async (invNo) => {
    const response = await apiClient.get(`/equipment/${invNo}`);
    return response.data;
  },

  getEquipmentActs: async (invNo) => {
    const response = await apiClient.get(`/equipment/${invNo}/acts`);
    return response.data;
  },

  downloadEquipmentActFile: async (docNo, params = {}) => {
    const response = await apiClient.get(`/equipment/acts/${docNo}/file`, {
      params,
      responseType: 'blob',
    });
    return response;
  },

  parseUploadedAct: async (file, options = {}) => {
    const formData = new FormData();
    formData.append('file', file);
    const manualMode = Boolean(options?.manualMode);
    const response = await apiClient.post('/equipment/acts/upload/parse', formData, {
      params: manualMode ? { manual_mode: true } : undefined,
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  getUploadedActDraft: async (draftId) => {
    const response = await apiClient.get(`/equipment/acts/upload/draft/${encodeURIComponent(draftId)}`);
    return response.data;
  },

  commitUploadedActDraft: async (payload) => {
    const response = await apiClient.post('/equipment/acts/upload/commit', payload);
    return response.data;
  },

  sendUploadedActEmail: async (payload) => {
    const response = await apiClient.post('/equipment/acts/upload/email', payload);
    return response.data;
  },

  getAllEquipment: async (page = 1, limit = 50) => {
    const response = await apiClient.get('/equipment/database', {
      params: { page, limit },
    });
    return response.data;
  },

  getAllEquipmentGrouped: async ({ page = 1, limit = 1000, branch } = {}) => {
    const response = await apiClient.get('/equipment/all-grouped', {
      params: { page, limit, branch: branch || undefined },
    });
    return response.data;
  },

  getAllConsumablesGrouped: async ({ page = 1, limit = 1000 } = {}) => {
    const response = await apiClient.get('/equipment/consumables-grouped', {
      params: { page, limit },
    });
    return response.data;
  },

  getByInvNos: async (invNos = []) => {
    const response = await apiClient.post('/equipment/by-inv-nos', {
      inv_nos: Array.isArray(invNos) ? invNos : [],
    });
    return response.data;
  },

  identifyWorkspace: async () => {
    const response = await apiClient.get('/discovery/identify-workspace');
    return response.data;
  },

  getBranches: async () => {
    const response = await apiClient.get('/equipment/branches');
    return response.data;
  },

  getBranchesList: async () => {
    const response = await apiClient.get('/equipment/branches-list');
    return response.data;
  },

  getLocations: async (branchId) => {
    const response = await apiClient.get(`/equipment/locations/${branchId}`);
    return response.data;
  },

  getTypes: async () => {
    const response = await apiClient.get('/equipment/types');
    return response.data;
  },

  getModels: async (typeNo, ciType = 1) => {
    const response = await apiClient.get('/equipment/models', {
      params: { type_no: typeNo, ci_type: ciType },
    });
    return response.data;
  },

  getStatuses: async () => {
    const response = await apiClient.get('/equipment/statuses');
    return response.data;
  },

  searchOwners: async (query, limit = 20) => {
    const response = await apiClient.get('/equipment/owners/search', {
      params: { q: query, limit },
    });
    return response.data;
  },

  getOwnerDepartments: async (limit = 500) => {
    const response = await apiClient.get('/equipment/owners/departments', {
      params: { limit },
    });
    return response.data;
  },

  updateByInvNo: async (invNo, payload) => {
    const response = await apiClient.patch(`/equipment/${invNo}`, payload);
    return response.data;
  },

  createEquipment: async (payload) => {
    const response = await apiClient.post('/equipment/create', payload);
    return response.data;
  },

  createConsumable: async (payload) => {
    const response = await apiClient.post('/equipment/consumables/create', payload);
    return response.data;
  },

  lookupConsumables: async (params = {}) => {
    const response = await apiClient.get('/equipment/consumables/lookup', { params });
    return response.data;
  },

  consumeConsumable: async (payload) => {
    const response = await apiClient.post('/equipment/consumables/consume', payload);
    return response.data;
  },

  updateConsumableQty: async (payload) => {
    const response = await apiClient.patch('/equipment/consumables/qty', payload);
    return response.data;
  },

  transfer: async (payload) => {
    const response = await apiClient.post('/equipment/transfer', payload);
    return response.data;
  },

  sendTransferActsEmail: async (payload) => {
    const response = await apiClient.post('/equipment/transfer/email', payload);
    return response.data;
  },

  downloadTransferAct: async (actId) => {
    const response = await apiClient.get(`/equipment/transfer/act/${actId}`, {
      responseType: 'blob',
    });
    return response;
  },
};

export const mfuAPI = {
  getDevices: async (params = {}) => {
    const response = await apiClient.get('/mfu/devices', { params });
    return response.data;
  },
  getMonthlyPages: async (params = {}) => {
    const response = await apiClient.get('/mfu/pages/monthly', { params });
    return response.data;
  },
};

const normalizeScanHost = (value) => String(value || '').trim().toUpperCase();

const toUnixTs = (value) => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  const parsed = Date.parse(String(value || ''));
  if (!Number.isFinite(parsed)) return 0;
  return Math.floor(parsed / 1000);
};

const severityRank = (value) => {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'high') return 3;
  if (normalized === 'medium') return 2;
  if (normalized === 'low') return 1;
  return 0;
};

const aggregateHostsFromIncidents = (items) => {
  const source = Array.isArray(items) ? items : [];
  const map = new Map();

  source.forEach((incident) => {
    const hostname = normalizeScanHost(incident?.hostname);
    if (!hostname) return;

    if (!map.has(hostname)) {
      map.set(hostname, {
        hostname,
        incidents_total: 0,
        incidents_new: 0,
        last_incident_at: 0,
        top_severity: 'none',
        extMap: new Map(),
        sourceKindMap: new Map(),
      });
    }

    const entry = map.get(hostname);
    entry.incidents_total += 1;

    const status = String(incident?.status || '').toLowerCase();
    if (status !== 'acknowledged') {
      entry.incidents_new += 1;
    }

    const ts = toUnixTs(incident?.created_at || incident?.detected_at || incident?.updated_at);
    if (ts > entry.last_incident_at) {
      entry.last_incident_at = ts;
    }

    const rank = severityRank(incident?.severity);
    if (rank > severityRank(entry.top_severity)) {
      entry.top_severity = rank === 3 ? 'high' : rank === 2 ? 'medium' : rank === 1 ? 'low' : 'none';
    }

    const ext = String(incident?.file_ext || incident?.extension || '').trim().toLowerCase();
    if (ext) {
      entry.extMap.set(ext, (entry.extMap.get(ext) || 0) + 1);
    }

    const sourceKind = String(incident?.source_kind || incident?.source || '').trim().toLowerCase();
    if (sourceKind) {
      entry.sourceKindMap.set(sourceKind, (entry.sourceKindMap.get(sourceKind) || 0) + 1);
    }
  });

  return Array.from(map.values()).map((entry) => {
    const topExts = Array.from(entry.extMap.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 3)
      .map(([ext]) => ext);

    const topSourceKinds = Array.from(entry.sourceKindMap.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 3)
      .map(([kind]) => kind);

    return {
      hostname: entry.hostname,
      incidents_total: entry.incidents_total,
      incidents_new: entry.incidents_new,
      last_incident_at: entry.last_incident_at,
      top_severity: entry.top_severity,
      top_exts: topExts,
      top_source_kinds: topSourceKinds,
    };
  });
};

const getHostsFallbackFromIncidents = async (params = {}) => {
  const limitValue = Number(params?.limit || 300);
  const incidentLimit = Number.isFinite(limitValue) ? Math.max(limitValue * 4, 500) : 500;
  const response = await apiClient.get('/scan/incidents', {
    params: { limit: incidentLimit, offset: 0 },
  });
  const items = response?.data?.items;
  return aggregateHostsFromIncidents(items);
};

export const scanAPI = {
  getDashboard: async () => {
    const response = await apiClient.get('/scan/dashboard');
    return response.data;
  },

  getHosts: async (params = {}) => {
    if (scanHostsEndpointUnavailable) {
      return getHostsFallbackFromIncidents(params);
    }
    try {
      const response = await apiClient.get('/scan/hosts', { params });
      return response.data;
    } catch (error) {
      const statusCode = Number(error?.response?.status || 0);
      if (statusCode !== 404) {
        throw error;
      }
      markScanHostsUnavailable(true);
      return getHostsFallbackFromIncidents(params);
    }
  },

  getIncidents: async (params = {}) => {
    const response = await apiClient.get('/scan/incidents', { params });
    return response.data;
  },

  ackIncident: async (incidentId, ackBy = '') => {
    const response = await apiClient.post(`/scan/incidents/${encodeURIComponent(incidentId)}/ack`, {
      ack_by: ackBy,
    });
    return response.data;
  },

  getAgents: async () => {
    const response = await apiClient.get('/scan/agents');
    return response.data;
  },

  createTask: async (payload) => {
    const response = await apiClient.post('/scan/tasks', payload);
    return response.data;
  },
};

/**
 * AD Users API
 */
export const adUsersAPI = {
  getPasswordStatus: async () => {
    const { data } = await apiClient.get('/ad-users/password-status');
    return data;
  },
  assignBranch: async (payload) => {
    const { data } = await apiClient.post('/ad-users/assign-branch', payload);
    return data;
  }
};
