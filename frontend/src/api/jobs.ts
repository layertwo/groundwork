import {
  CreateJobCommand,
  GetJobCommand,
  ListJobsCommand,
  type CreateJobInput,
  type JobResponse,
  type ListJobsCommandInput,
} from '@groundwork/client'
import { client, request } from './sdk'

export function listJobs(filters?: ListJobsCommandInput): Promise<JobResponse[]> {
  return request(() => client.send(new ListJobsCommand(filters ?? {}))).then(
    (out) => out.jobs ?? [],
  )
}

export function getJob(id: string): Promise<JobResponse> {
  return request(() => client.send(new GetJobCommand({ id })))
}

export function createJob(data: CreateJobInput): Promise<JobResponse> {
  return request(() => client.send(new CreateJobCommand(data)))
}
