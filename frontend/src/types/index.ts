export interface User {
  id: number
  email: string
  full_name: string
  is_platform_admin: boolean
}

export interface Workspace {
  id: number
  name: string
  slug: string
  description?: string
  industry?: string
  company_size?: string
  contact_email?: string
  status: 'active' | 'paused' | 'archived'
  created_at: string
  updated_at: string
}

export interface WorkspaceMember {
  id: number
  user_id: number
  workspace_id: number
  role: 'viewer' | 'analyst' | 'admin'
  is_active: boolean
  user: User
  created_at: string
}

export interface IngestionFile {
  id: number
  original_filename: string
  file_size: number
  mime_type?: string
  source_type: string
  status: string
  uploaded_by_email?: string
  checksum_sha256?: string
  created_at: string
}

export interface AuditLog {
  id: number
  user_email?: string
  action: string
  resource_type?: string
  resource_id?: string
  detail?: Record<string, unknown>
  ip_address?: string
  created_at: string
}

// Sprint 2 — Connectors & Assets

export interface Connector {
  id: number
  name: string
  connector_type: 'azure' | 'm365' | 'google_workspace' | 'aws' | 'gcp' | 'manual'
  platform: string
  /** 'configured' | 'error' | 'disabled' */
  status: string
  last_scan_at?: string
  /** Backend returns 'success' | 'error' | 'running' | null */
  last_scan_status?: string
  last_scan_error?: string
  created_by_email?: string
  created_at: string
}

export interface ScanJob {
  id: number
  connector_id: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  started_at?: string
  completed_at?: string
  assets_found: number
  error_message?: string
  created_at: string
}

export interface DiscoveredAsset {
  id: number
  external_id: string
  name: string
  vendor?: string
  category: string
  subcategory?: string
  description?: string
  resource_type?: string
  resource_group?: string
  location?: string
  risk_level: 'low' | 'medium' | 'high' | 'critical'
  risk_score: number
  confidence_score: number
  is_shadow_ai: boolean
  analyst_status: 'pending_review' | 'confirmed' | 'false_positive' | 'accepted_risk'
  analyst_notes?: string
  first_seen_at: string
  last_seen_at: string
  scan_job_id?: number
  raw_data?: Record<string, unknown>
}

export interface TaxonomyEntry {
  id: string
  name: string
  vendor: string
  category: string
  subcategory: string
  risk_level: string
  risk_score: number
  description: string
  is_saas: boolean
}

// Sprint 4 — Reports

export interface Report {
  id: number
  title: string
  report_type: 'full_discovery' | 'executive_summary' | 'shadow_ai_only'
  format: 'pdf' | 'docx'
  status: 'generating' | 'ready' | 'error'
  file_size?: number
  generated_by_email?: string
  snapshot?: {
    total_assets: number
    shadow_ai: number
    critical: number
    high_risk: number
  }
  error_message?: string
  created_at: string
  updated_at: string
}

export interface WorkspaceStats {
  workspace: Workspace
  total_assets: number
  shadow_ai_count: number
  high_risk_count: number
  last_scan_at?: string
  connector_count: number
}
