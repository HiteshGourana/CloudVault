import axios from 'axios';

// Base API setup (proxied through Vite in development)
const API = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Auto-inject JWT token for authorized requests
API.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Auto-handle 401 Unauthorized errors (session expiration)
API.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      // Redirect to login if not already there
      if (!window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/register')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// ── Auth Service ────────────────────────────────────────────
export const authAPI = {
  register: (data) => API.post('/auth/register', data).then(res => res.data),
  login: (data) => API.post('/auth/login', data).then(res => res.data),
  getMe: () => API.get('/auth/me').then(res => res.data),
  logout: () => API.post('/auth/logout').then(res => res.data),
};

// ── AWS Connected Accounts Service ──────────────────────────
export const awsAPI = {
  connect: (data) => API.post('/aws/connect', data).then(res => res.data),
  disconnect: () => API.delete('/aws/disconnect').then(res => res.data), // ← must be DELETE
  status: () => API.get('/aws/status').then(res => res.data),
};

// ── S3 Buckets Service ──────────────────────────────────────
export const bucketsAPI = {
  list: () => API.get('/buckets').then(res => res.data),
  create: (bucketName, region = 'ap-south-1') => API.post('/buckets', { bucket_name: bucketName, region }).then(res => res.data),
  getDetails: (bucketName) => API.get(`/buckets/${bucketName}`).then(res => res.data),
  delete: (bucketName, forceEmpty = false) =>
    API.delete(`/buckets/${bucketName}`, { params: { force_empty: forceEmpty } }).then(res => res.data),
  exists: (bucketName) => API.post(`/buckets/${bucketName}/exists`).then(res => res.data),
  checkOwnership: (bucketName) => API.post(`/buckets/${bucketName}/ownership`).then(res => res.data),
};


// ── S3 Folders Prefix Service ────────────────────────────────
export const foldersAPI = {
  create: (data) => API.post('/folders', data).then(res => res.data),
  list: (params) => API.get('/folders', { params }).then(res => res.data),
  getTree: (params) => API.get('/folders/tree', { params }).then(res => res.data),
  // Backend FolderRename schema expects: { new_folder_name }
  rename: (id, name) => API.put(`/folders/${id}/rename`, { new_folder_name: name }).then(res => res.data),
  // Backend FolderMove schema expects: { new_parent_folder_id }
  move: (id, parentId) => API.put(`/folders/${id}/move`, { new_parent_folder_id: parentId }).then(res => res.data),
  delete: (id) => API.delete(`/folders/${id}`).then(res => res.data),
};

// ── Files Operations Service ─────────────────────────────────
export const filesAPI = {
  list: (params) => API.get('/files', { params }).then(res => res.data),
  uploadFile: (formData, onUploadProgress) => {
    return API.post('/upload/file', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress,
    }).then(res => res.data);
  },
  uploadFiles: (formData) => {
    return API.post('/upload/files', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }).then(res => res.data);
  },
  uploadFolder: (formData, onUploadProgress) => {
    return API.post('/upload/folder', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress,
    }).then(res => res.data);
  },
  getDownloadUrl: (fileId) => API.get(`/files/${fileId}/download`).then(res => res.data),
  // Backend FileRename schema expects: { new_file_name }
  rename: (id, name) => API.put(`/files/${id}/rename`, { new_file_name: name }).then(res => res.data),
  // Backend FileMove schema expects: { new_folder_id }
  move: (id, folderId) => API.put(`/files/${id}/move`, { new_folder_id: folderId ?? null }).then(res => res.data),
  // copy uses query param destination_folder_id
  copy: (id, folderId) => API.post(`/files/${id}/copy`, null, { params: { destination_folder_id: folderId ?? undefined } }).then(res => res.data),
  delete: (id) => API.delete(`/files/${id}`).then(res => res.data),
  bulkDelete: (fileIds) => API.post('/files/bulk/delete', { file_ids: fileIds }).then(res => res.data),
  restore: (id) => API.post(`/files/${id}/restore`).then(res => res.data),
  getTypesSummary: () => API.get('/files/types').then(res => res.data),
  syncBucket: (bucketName) => API.post('/files/sync', null, { params: { bucket_name: bucketName } }).then(res => res.data),
};

// ── Sharing Links Service ────────────────────────────────────
export const shareAPI = {
  createDownloadLink: (data) => API.post('/share/download', data).then(res => res.data),
  createUploadLink: (data) => API.post('/share/upload', data).then(res => res.data),
  list: () => API.get('/share').then(res => res.data),
  history: () => API.get('/share/history').then(res => res.data),
  delete: (id) => API.delete(`/share/${id}`).then(res => res.data),
};

// ── Dashboard Analytics Service ──────────────────────────────
export const dashboardAPI = {
  getOverview: () => API.get('/dashboard/overview').then(res => res.data),
  getStorageStats: () => API.get('/dashboard/storage').then(res => res.data),
  getFileCategories: () => API.get('/dashboard/files').then(res => res.data),
  getFolderMetrics: () => API.get('/dashboard/folders').then(res => res.data),
  getRecentActivity: () => API.get('/dashboard/recent').then(res => res.data),
};

// ── Monitoring Service ───────────────────────────────────────
export const systemAPI = {
  health: () => API.get('/health').then(res => res.data),
  metrics: () => API.get('/metrics').then(res => res.data),
  info: () => API.get('/system/info').then(res => res.data),
  getActivityLogs: (params) => API.get('/activity', { params }).then(res => res.data),
  getNotifications: () => API.get('/notifications').then(res => res.data),
};

export default API;
