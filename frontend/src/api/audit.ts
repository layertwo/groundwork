import { apiFetch } from './client'

export interface AuditUser {
  id: string
  display_name: string
}

export interface AuditLogEntry {
  id: number
  user_id: string | null
  action: string
  resource_type: string | null
  resource_id: string | null
  detail: Record<string, unknown> | null
  ip_address: string | null
  user_agent: string | null
  created_at: string
  user: AuditUser | null
}

export interface AuditLogFilters {
  resource_type?: string
  resource_id?: string
  user_id?: string
  action?: string
  page?: number
  page_size?: number
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export function listAuditLogs(
  filters: AuditLogFilters,
): Promise<Paginated<AuditLogEntry>> {
  const params = new URLSearchParams()
  if (filters.resource_type) params.set('resource_type', filters.resource_type)
  if (filters.resource_id) params.set('resource_id', filters.resource_id)
  if (filters.user_id) params.set('user_id', filters.user_id)
  if (filters.action) params.set('action', filters.action)
  if (filters.page) params.set('page', String(filters.page))
  if (filters.page_size) params.set('page_size', String(filters.page_size))
  const qs = params.toString()
  return apiFetch<Paginated<AuditLogEntry>>(`/api/audit${qs ? `?${qs}` : ''}`)
}
