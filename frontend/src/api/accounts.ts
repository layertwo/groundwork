import { apiFetch } from './client'

// Wire shapes mirror smithy/models/accounts.smithy (camelCase).

export interface AccountResponse {
  id: string
  awsAccountId: string | null
  accountName: string
  accountEmail: string
  organizationalUnit: string
  status: string
  awsStatus: string | null
  ssoUserEmail: string
  provisionedProductId: string | null
  createdBy: string
  errorMessage: string | null
  createdAt: string
  updatedAt: string
  alias: string | null
  color: string | null
}

export interface AccountCreate {
  accountName: string
  accountEmail: string
  organizationalUnit: string
  ssoUserEmail: string
}

export interface AccountUpdate {
  accountName?: string
  organizationalUnit?: string
  ssoUserEmail?: string
  alias?: string
  color?: string
}

export function listAccounts(): Promise<AccountResponse[]> {
  return apiFetch<{ accounts: AccountResponse[] }>('/api/accounts').then(
    (data) => data.accounts,
  )
}

export function getAccount(id: string): Promise<AccountResponse> {
  return apiFetch<AccountResponse>(`/api/accounts/${id}`)
}

export function createAccount(data: AccountCreate): Promise<AccountResponse> {
  return apiFetch<AccountResponse>('/api/accounts', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateAccount(
  id: string,
  data: AccountUpdate,
): Promise<AccountResponse> {
  return apiFetch<AccountResponse>(`/api/accounts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}
