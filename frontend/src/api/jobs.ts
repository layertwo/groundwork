import { apiFetch } from './client'

export interface JobResponse {
  id: string
  account_id: string | null
  job_type: string
  status: string
  started_by: string
  started_at: string | null
  completed_at: string | null
  result: Record<string, unknown> | null
  error_message: string | null
  created_at: string
}

export interface JobFilters {
  account_id?: string
  status?: string
  job_type?: string
}

export function listJobs(filters?: JobFilters): Promise<JobResponse[]> {
  const params = new URLSearchParams()
  if (filters?.account_id) params.set('account_id', filters.account_id)
  if (filters?.status) params.set('status', filters.status)
  if (filters?.job_type) params.set('job_type', filters.job_type)
  const qs = params.toString()
  return apiFetch<JobResponse[]>(`/api/jobs${qs ? `?${qs}` : ''}`)
}

export function getJob(id: string): Promise<JobResponse> {
  return apiFetch<JobResponse>(`/api/jobs/${id}`)
}

export interface JobCreate {
  job_type: string
}

export function createJob(data: JobCreate): Promise<JobResponse> {
  return apiFetch<JobResponse>('/api/jobs', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
