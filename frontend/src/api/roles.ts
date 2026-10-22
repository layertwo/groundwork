import {
  CreateRoleCommand,
  CreateRoleTemplateCommand,
  DeleteRoleCommand,
  DeleteRoleTemplateCommand,
  FixRoleDriftCommand,
  ListRolesCommand,
  ListRoleTemplatesCommand,
  UpdateRoleCommand,
  UpdateRoleTemplateCommand,
  type CreateRoleInput,
  type CreateRoleTemplateInput,
  type RoleResponse,
  type RoleTemplateResponse,
  type UpdateRoleInput,
  type UpdateRoleTemplateInput,
} from '@groundwork/client'
import { apiFetch } from './client'
import { client, request } from './sdk'

// Federate is not modelled in Smithy (redirect / temporary credentials).
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
  return request(() => client.send(new ListRolesCommand({}))).then(
    (out) => out.roles ?? [],
  )
}

export function getRoleTemplates(): Promise<RoleTemplateResponse[]> {
  return request(() => client.send(new ListRoleTemplatesCommand({}))).then(
    (out) => out.templates ?? [],
  )
}

export function createRoleTemplate(
  data: CreateRoleTemplateInput,
): Promise<RoleTemplateResponse> {
  return request(() => client.send(new CreateRoleTemplateCommand(data)))
}

export function updateRoleTemplate(
  data: UpdateRoleTemplateInput,
): Promise<RoleTemplateResponse> {
  return request(() => client.send(new UpdateRoleTemplateCommand(data)))
}

export async function deleteRoleTemplate(templateId: string): Promise<void> {
  await request(() => client.send(new DeleteRoleTemplateCommand({ templateId })))
}

export function createRole(data: CreateRoleInput): Promise<RoleResponse> {
  return request(() => client.send(new CreateRoleCommand(data)))
}

export function updateRole(data: UpdateRoleInput): Promise<RoleResponse> {
  return request(() => client.send(new UpdateRoleCommand(data)))
}

export async function deleteRole(accountId: string, roleId: string): Promise<void> {
  await request(() => client.send(new DeleteRoleCommand({ accountId, roleId })))
}

export async function fixDrift(accountId: string, roleId: string): Promise<void> {
  await request(() => client.send(new FixRoleDriftCommand({ accountId, roleId })))
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
