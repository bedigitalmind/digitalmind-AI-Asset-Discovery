import axios from 'axios'
import { getToken, clearAuth } from './auth'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (error) => {
    // Só redireciona para /login se o 401 vier de uma rota protegida,
    // nunca da própria rota de login (evita loop de redirecionamento).
    const isLoginEndpoint = error.config?.url?.includes('/auth/login')
    if (error.response?.status === 401 && typeof window !== 'undefined' && !isLoginEndpoint) {
      clearAuth()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// ─── Auth ────────────────────────────────────────────────────────────────────

export const login = (email: string, password: string) =>
  api.post('/auth/login', { email, password }).then((r) => r.data)

export const getMe = () => api.get('/auth/me').then((r) => r.data)

// ─── Workspaces ───────────────────────────────────────────────────────────────

export const listWorkspaces = () =>
  api.get('/workspaces').then((r) => r.data)

export const getWorkspace = (id: number) =>
  api.get(`/workspaces/${id}`).then((r) => r.data)

export const createWorkspace = (data: {
  name: string; slug: string; description?: string
  industry?: string; company_size?: string; contact_email?: string
}) => api.post('/workspaces', data).then((r) => r.data)

export const updateWorkspace = (id: number, data: Partial<{
  name: string; description: string; industry: string
  company_size: string; contact_email: string; status: string
}>) => api.patch(`/workspaces/${id}`, data).then((r) => r.data)

// ─── Files ────────────────────────────────────────────────────────────────────

export const listFiles = (workspaceId: number) =>
  api.get(`/workspaces/${workspaceId}/files`).then((r) => r.data)

export const uploadFile = (workspaceId: number, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post(`/workspaces/${workspaceId}/files`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then((r) => r.data)
}

export const deleteFile = (workspaceId: number, fileId: number) =>
  api.delete(`/workspaces/${workspaceId}/files/${fileId}`)

// ─── Members ──────────────────────────────────────────────────────────────────

export const listMembers = (workspaceId: number) =>
  api.get(`/workspaces/${workspaceId}/members`).then((r) => r.data)

export const addMember = (workspaceId: number, data: {
  email: string; full_name: string; role: string; password: string
}) => api.post(`/workspaces/${workspaceId}/members`, data).then((r) => r.data)

export const updateMemberRole = (workspaceId: number, memberId: number, role: string) =>
  api.patch(`/workspaces/${workspaceId}/members/${memberId}`, { role }).then((r) => r.data)

// ─── Audit logs ───────────────────────────────────────────────────────────────

export const listAuditLogs = (workspaceId: number) =>
  api.get(`/workspaces/${workspaceId}/audit-logs`).then((r) => r.data)

// ─── Connectors ───────────────────────────────────────────────────────────────

export const listConnectors = (workspaceId: number) =>
  api.get(`/workspaces/${workspaceId}/connectors`).then((r) => r.data)

export const createConnector = (workspaceId: number, data: {
  name: string
  connector_type: string
  platform: string
  config: Record<string, string>
}) => api.post(`/workspaces/${workspaceId}/connectors`, data).then((r) => r.data)

export const triggerScan = (workspaceId: number, connectorId: number) =>
  api.post(`/workspaces/${workspaceId}/connectors/${connectorId}/scan`).then((r) => r.data)

// ─── Assets ───────────────────────────────────────────────────────────────────

export const listAssets = (workspaceId: number, params?: {
  category?: string
  risk_level?: string
  is_shadow_ai?: boolean
  analyst_status?: string
  skip?: number
  limit?: number
}) => api.get(`/workspaces/${workspaceId}/assets`, { params }).then((r) => r.data)

export const updateAsset = (workspaceId: number, assetId: number, data: {
  analyst_status?: string
  analyst_notes?: string
  risk_score?: number
}) => api.patch(`/workspaces/${workspaceId}/assets/${assetId}`, data).then((r) => r.data)

// ─── Detection ────────────────────────────────────────────────────────────────

export const triggerFileDetection = (workspaceId: number, fileId: number) =>
  api.post(`/workspaces/${workspaceId}/detect/file/${fileId}`).then((r) => r.data)

export const triggerFileDetectionSync = (workspaceId: number, fileId: number) =>
  api.post(`/workspaces/${workspaceId}/detect/file/${fileId}/sync`).then((r) => r.data)

export const getDetectionStats = (workspaceId: number) =>
  api.get(`/workspaces/${workspaceId}/detect/stats`).then((r) => r.data)

export const getAssetCategories = (workspaceId: number) =>
  api.get(`/workspaces/${workspaceId}/detect/categories`).then((r) => r.data)

// ─── Taxonomy ─────────────────────────────────────────────────────────────────

export const getTaxonomyStats = () =>
  api.get('/taxonomy').then((r) => r.data)

export const getTaxonomyCategories = () =>
  api.get('/taxonomy/categories').then((r) => r.data)

export const getTaxonomyEntries = (params?: {
  category?: string; risk_level?: string; is_saas?: boolean
}) => api.get('/taxonomy/entries', { params }).then((r) => r.data)

// ─── Reports ──────────────────────────────────────────────────────────────────

export const createReport = (workspaceId: number, data: {
  title?: string
  report_type?: 'full_discovery' | 'executive_summary' | 'shadow_ai_only'
}) => api.post(`/workspaces/${workspaceId}/reports`, data).then((r) => r.data)

export const listReports = (workspaceId: number) =>
  api.get(`/workspaces/${workspaceId}/reports`).then((r) => r.data)

export const getReport = (workspaceId: number, reportId: number) =>
  api.get(`/workspaces/${workspaceId}/reports/${reportId}`).then((r) => r.data)

export const getReportDownloadUrl = (workspaceId: number, reportId: number) =>
  api.get(`/workspaces/${workspaceId}/reports/${reportId}/download`).then((r) => r.data)

export const deleteReport = (workspaceId: number, reportId: number) =>
  api.delete(`/workspaces/${workspaceId}/reports/${reportId}`)

export default api
