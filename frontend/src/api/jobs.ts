import { apiFetch } from './client'

// Wire shapes mirror smithy/models/jobs.smithy (camelCase).

export interface JobResponse {
  id: string
  accountId: string | null
  jobType: string
  status: string
  startedBy: string
  startedAt: string | null
  completedAt: string | null
  result: Record<string, unknown> | null
  errorMessage: string | null
  createdAt: string
  scheduledAfter: string | null
}

export interface JobFilters {
  accountId?: string
  status?: string
  jobType?: string
}

export function listJobs(filters?: JobFilters): Promise<JobResponse[]> {
  const params = new URLSearchParams()
  if (filters?.accountId) params.set('accountId', filters.accountId)
  if (filters?.status) params.set('status', filters.status)
  if (filters?.jobType) params.set('jobType', filters.jobType)
  const qs = params.toString()
  return apiFetch<{ jobs: JobResponse[] }>(`/api/jobs${qs ? `?${qs}` : ''}`).then(
    (data) => data.jobs,
  )
}

export function getJob(id: string): Promise<JobResponse> {
  return apiFetch<JobResponse>(`/api/jobs/${id}`)
}

export interface JobCreate {
  jobType: string
}

export function createJob(data: JobCreate): Promise<JobResponse> {
  return apiFetch<JobResponse>('/api/jobs', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
