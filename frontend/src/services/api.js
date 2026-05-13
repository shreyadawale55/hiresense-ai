import axios from 'axios'
import toast from 'react-hot-toast'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'

const ACCESS_KEY = 'hiresense.access_token'
const REFRESH_KEY = 'hiresense.refresh_token'
const USER_KEY = 'hiresense.user'
const hasStorage = typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'

export const getStoredAuth = () => ({
  accessToken: hasStorage ? localStorage.getItem(ACCESS_KEY) : null,
  refreshToken: hasStorage ? localStorage.getItem(REFRESH_KEY) : null,
  user: (() => {
    try {
      return hasStorage ? JSON.parse(localStorage.getItem(USER_KEY) || 'null') : null
    } catch {
      return null
    }
  })(),
})

export const setStoredAuth = ({ accessToken, refreshToken, user }) => {
  if (!hasStorage) return
  if (accessToken) localStorage.setItem(ACCESS_KEY, accessToken)
  if (refreshToken) localStorage.setItem(REFRESH_KEY, refreshToken)
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export const clearStoredAuth = () => {
  if (!hasStorage) return
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
}

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

const refreshClient = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = hasStorage ? localStorage.getItem(ACCESS_KEY) : null
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let refreshing = false
let pending = []

const resolvePending = (error, token = null) => {
  pending.forEach(({ resolve, reject }) => {
    if (error) reject(error)
    else resolve(token)
  })
  pending = []
}

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config || {}
    if (err.response?.status === 401 && !original._retry) {
      const refreshToken = hasStorage ? localStorage.getItem(REFRESH_KEY) : null
      if (!refreshToken) {
        clearStoredAuth()
        return Promise.reject(err)
      }

      if (refreshing) {
        return new Promise((resolve, reject) => {
          pending.push({ resolve, reject })
        }).then((token) => {
          original.headers.Authorization = `Bearer ${token}`
          return api(original)
        })
      }

      original._retry = true
      refreshing = true
      try {
        const response = await refreshClient.post('/api/auth/refresh', { refresh_token: refreshToken })
        const { access_token: accessToken, refresh_token: newRefreshToken, user } = response.data
        setStoredAuth({ accessToken, refreshToken: newRefreshToken, user })
        resolvePending(null, accessToken)
        original.headers.Authorization = `Bearer ${accessToken}`
        return api(original)
      } catch (refreshError) {
        resolvePending(refreshError, null)
        clearStoredAuth()
        return Promise.reject(refreshError)
      } finally {
        refreshing = false
      }
    }

    const msg = err.response?.data?.detail || err.message || 'Request failed'
    toast.error(msg)
    return Promise.reject(err)
  }
)

export const authApi = {
  login: (payload) => api.post('/api/auth/login', payload),
  refresh: (refreshToken) => refreshClient.post('/api/auth/refresh', { refresh_token: refreshToken }),
  logout: (refreshToken = null) => api.post('/api/auth/logout', { refresh_token: refreshToken }),
  me: () => api.get('/api/auth/me'),
  register: (payload) => api.post('/api/auth/register', payload),
  bootstrap: () => api.get('/api/auth/bootstrap'),
}

export const jobsApi = {
  list: (params = {}) => api.get('/api/jobs/', { params }),
  get: (id) => api.get(`/api/jobs/${id}`),
  create: (data) => api.post('/api/jobs/', data),
  update: (id, data) => api.patch(`/api/jobs/${id}`, data),
  delete: (id) => api.delete(`/api/jobs/${id}`),
}

export const resumesApi = {
  list: (params = {}) => api.get('/api/resumes/', { params }),
  get: (id) => api.get(`/api/resumes/${id}`),
  upload: (file, jobId = null) => {
    const form = new FormData()
    form.append('file', file)
    if (jobId) form.append('job_id', jobId)
    return api.post('/api/resumes/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })
  },
  uploadBatch: (files, jobId = null) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    if (jobId) form.append('job_id', jobId)
    return api.post('/api/resumes/upload-batch', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  },
  delete: (id) => api.delete(`/api/resumes/${id}`),
}

export const screeningApi = {
  start: (jobId, resumeIds, queryText = null) =>
    api.post('/api/screening/', { job_id: jobId, resume_ids: resumeIds, query_text: queryText }),
  getResults: (jobId) => api.get(`/api/screening/${jobId}/results`),
  getSingle: (screeningId) => api.get(`/api/screening/result/${screeningId}`),
  getStats: (jobId) => api.get(`/api/screening/stats/${jobId}`),
  similarity: (resumeId, limit = 10) => api.get(`/api/screening/similarity/${resumeId}`, { params: { limit } }),
  search: (query, limit = 10, includeFairness = true) =>
    api.post('/api/screening/search', { query, limit, include_fairness: includeFairness }),
}

export const notificationsApi = {
  wsUrl: (token) => `${WS_BASE}/ws/notifications?token=${encodeURIComponent(token)}`,
  screeningUrl: (jobId, token) => `${WS_BASE}/ws/screening/${jobId}?token=${encodeURIComponent(token)}`,
}

export const healthApi = {
  check: () => api.get('/health'),
  detailed: () => api.get('/health/detailed'),
}

export default api
