import axios from 'axios';

const API_BASE_URL = 
  (typeof import.meta !== 'undefined' && import.meta.env && (import.meta.env.VITE_API_BASE_URL || import.meta.env.REACT_APP_API_URL)) ||
  (typeof process !== 'undefined' && process.env && (process.env.VITE_API_BASE_URL || process.env.REACT_APP_API_URL)) ||
  'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      if (!window.location.pathname.includes('/login') && !window.location.pathname.includes('/register')) {
        localStorage.removeItem('user_role');
        localStorage.removeItem('user_id');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export const authAPI = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  logout: () => api.post('/auth/logout'),
};

export const patientAPI = {
  getPatient: (id) => api.get(`/patients/${id}`),
};

export const requestAPI = {
  create: (data) => api.post('/requests', data),
  extractPdf: (formData) => api.post('/requests/extract-pdf', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  getUserRequests: () => api.get('/requests'),
  getDetail: (id) => api.get(`/requests/${id}`),
  resubmit: (id, data) => api.post(`/requests/${id}/resubmit`, data),
};


export const reviewAPI = {
  getQueue: () => api.get('/review-queue'),
  confirm: (id, data) => api.post(`/requests/${id}/confirm`, data),
};

export const codeAPI = {
  getHcpcs: (search = '', limit = 100) => api.get(`/codes/hcpcs?search=${encodeURIComponent(search)}&limit=${limit}`),
  getIcd10: (search = '', hcpcs = '', limit = 100) => api.get(`/codes/icd10?search=${encodeURIComponent(search)}&hcpcs=${encodeURIComponent(hcpcs)}&limit=${limit}`),
};

export default api;
