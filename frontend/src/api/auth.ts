import { apiFetch } from './client'

export interface UserInfo {
  id: string
  sub: string
  email: string
  display_name: string
  groups: string[]
  is_admin: boolean
}

export interface AuthStatus {
  authenticated: boolean
  user: UserInfo | null
}

export function getAuthStatus(): Promise<AuthStatus> {
  return apiFetch<AuthStatus>('/api/auth/status')
}

export function getUserInfo(): Promise<UserInfo> {
  return apiFetch<UserInfo>('/api/auth/me')
}

export function logout(): Promise<void> {
  return apiFetch<void>('/api/auth/logout', { method: 'POST' })
}
