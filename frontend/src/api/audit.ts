import { apiFetch } from './client'

// Wire shapes mirror smithy/models/audit.smithy.

export interface AuditUser {
  id: string
  displayName: string
}

export interface AuditLogEntry {
  id: number
  userId: string | null
  action: string
  resourceType: string | null
  resourceId: string | null
  detail: Record<string, unknown> | null
  ipAddress: string | null
  userAgent: string | null
  createdAt: string
  user: AuditUser | null
}

export interface AuditLogFilters {
  resourceType?: string
  resourceId?: string
  userId?: string
  action?: string
  page?: number
  pageSize?: number
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

export function listAuditLogs(
  filters: AuditLogFilters,
): Promise<Paginated<AuditLogEntry>> {
  const params = new URLSearchParams()
  if (filters.resourceType) params.set('resourceType', filters.resourceType)
  if (filters.resourceId) params.set('resourceId', filters.resourceId)
  if (filters.userId) params.set('userId', filters.userId)
  if (filters.action) params.set('action', filters.action)
  if (filters.page) params.set('page', String(filters.page))
  if (filters.pageSize) params.set('pageSize', String(filters.pageSize))
  const qs = params.toString()
  return apiFetch<Paginated<AuditLogEntry>>(`/api/audit${qs ? `?${qs}` : ''}`)
}
