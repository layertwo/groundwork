import { apiFetch } from './client'

// Wire shapes mirror smithy/models/roles.smithy and role_templates.smithy.

export interface RoleResponse {
  id: string
  accountId: string
  roleName: string
  roleArn: string
  status: string
  errorMessage: string | null
  allowedGroups: string[]
  managedPolicyArns: string[]
  inlinePolicy: Record<string, unknown> | null
  allowedUsers: string[]
  apiSessionDuration: number
  consoleSessionDuration: number
  description: string | null
  createdAt: string
  updatedAt: string
  lastUsedAt: string | null
}

export interface RoleCreate {
  roleName: string
  templateId?: string | null
  managedPolicyArns?: string[]
  inlinePolicy?: Record<string, unknown> | null
  allowedGroups?: string[]
  allowedUsers?: string[]
  apiSessionDuration?: number
  consoleSessionDuration?: number
  description?: string | null
}

export interface RoleUpdate {
  managedPolicyArns?: string[]
  inlinePolicy?: Record<string, unknown> | null
  allowedGroups?: string[]
  allowedUsers?: string[]
  apiSessionDuration?: number
  consoleSessionDuration?: number
  description?: string | null
}

export interface RoleTemplateResponse {
  id: string
  name: string
  description: string | null
  managedPolicyArns: string[]
  createdAt: string
  updatedAt: string
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
  return apiFetch<{ roles: RoleResponse[] }>('/api/roles').then((data) => data.roles)
}

export interface RoleTemplateCreate {
  name: string
  description?: string | null
  managedPolicyArns: string[]
}

export interface RoleTemplateUpdate {
  name?: string
  description?: string | null
  managedPolicyArns?: string[]
}

export function getRoleTemplates(): Promise<RoleTemplateResponse[]> {
  return apiFetch<{ templates: RoleTemplateResponse[] }>('/api/roles/templates').then(
    (data) => data.templates,
  )
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

export function fixDrift(
  accountId: string,
  roleId: string,
): Promise<void> {
  return apiFetch<void>(`/api/accounts/${accountId}/roles/${roleId}/fix-drift`, {
    method: 'POST',
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
