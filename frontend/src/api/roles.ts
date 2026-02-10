import { apiFetch } from './client'

export interface RoleResponse {
  id: string
  account_id: string
  role_name: string
  role_arn: string
  status: string
  error_message: string | null
  allowed_groups: string[]
  managed_policy_arns: string[]
  inline_policy: Record<string, unknown> | null
  allowed_users: string[]
  api_session_duration: number
  console_session_duration: number
  description: string | null
  created_at: string
  updated_at: string
  last_used_at: string | null
}

export interface RoleCreate {
  role_name: string
  template_id?: string | null
  managed_policy_arns?: string[]
  inline_policy?: Record<string, unknown> | null
  allowed_groups?: string[]
  allowed_users?: string[]
  api_session_duration?: number
  console_session_duration?: number
  description?: string | null
}

export interface RoleUpdate {
  managed_policy_arns?: string[]
  inline_policy?: Record<string, unknown> | null
  allowed_groups?: string[]
  allowed_users?: string[]
  api_session_duration?: number
  console_session_duration?: number
  description?: string | null
}

export interface RoleTemplateResponse {
  id: string
  name: string
  description: string | null
  managed_policy_arns: string[]
  created_at: string
  updated_at: string
}

export interface AssumeRoleResponse {
  access_key_id: string
  secret_access_key: string
  session_token: string
  expiration: string
}

export interface ConsoleUrlResponse {
  console_url: string
}

export function listRoles(): Promise<RoleResponse[]> {
  return apiFetch<RoleResponse[]>('/api/roles')
}

export interface RoleTemplateCreate {
  name: string
  description?: string | null
  managed_policy_arns: string[]
}

export interface RoleTemplateUpdate {
  name?: string
  description?: string | null
  managed_policy_arns?: string[]
}

export function getRoleTemplates(): Promise<RoleTemplateResponse[]> {
  return apiFetch<RoleTemplateResponse[]>('/api/roles/templates')
}

export function createRoleTemplate(data: RoleTemplateCreate): Promise<RoleTemplateResponse> {
  return apiFetch<RoleTemplateResponse>('/api/roles/templates', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateRoleTemplate(
  templateId: string,
  data: RoleTemplateUpdate,
): Promise<RoleTemplateResponse> {
  return apiFetch<RoleTemplateResponse>(`/api/roles/templates/${templateId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteRoleTemplate(templateId: string): Promise<void> {
  return apiFetch<void>(`/api/roles/templates/${templateId}`, {
    method: 'DELETE',
  })
}

export function createRole(
  accountId: string,
  data: RoleCreate,
): Promise<RoleResponse> {
  return apiFetch<RoleResponse>(`/api/accounts/${accountId}/roles`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateRole(
  accountId: string,
  roleId: string,
  data: RoleUpdate,
): Promise<RoleResponse> {
  return apiFetch<RoleResponse>(`/api/accounts/${accountId}/roles/${roleId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteRole(
  accountId: string,
  roleId: string,
): Promise<void> {
  return apiFetch<void>(`/api/accounts/${accountId}/roles/${roleId}`, {
    method: 'DELETE',
  })
}

export function federate(
  awsAccountId: string,
  roleName: string,
  method: 'console' | 'cli' = 'console',
): Promise<AssumeRoleResponse | ConsoleUrlResponse> {
  const params = new URLSearchParams({
    account_id: awsAccountId,
    role: roleName,
    method,
  })
  return apiFetch(`/api/federate?${params}`)
}
