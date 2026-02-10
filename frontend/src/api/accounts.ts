import { apiFetch } from './client'

export interface AccountResponse {
  id: string
  aws_account_id: string | null
  account_name: string
  account_email: string
  organizational_unit: string
  status: string
  aws_status: string | null
  sso_user_email: string
  provisioned_product_id: string | null
  created_by: string
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface AccountCreate {
  account_name: string
  account_email: string
  organizational_unit: string
  sso_user_email: string
}

export interface AccountUpdate {
  account_name?: string
  organizational_unit?: string
  sso_user_email?: string
}

export function listAccounts(): Promise<AccountResponse[]> {
  return apiFetch<AccountResponse[]>('/api/accounts')
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
