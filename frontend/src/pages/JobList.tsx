import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { listJobs } from '@/api/jobs'
import { listAccounts } from '@/api/accounts'
import SearchInput from '@/components/SearchInput'

const ALL = '__all__'

function statusVariant(status: string) {
  switch (status) {
    case 'completed':
      return 'default' as const
    case 'failed':
      return 'destructive' as const
    default:
      return 'secondary' as const
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString()
}

export default function JobList() {
  const [statusFilter, setStatusFilter] = useState(ALL)
  const [typeFilter, setTypeFilter] = useState(ALL)
  const [search, setSearch] = useState('')

  const filters = {
    ...(statusFilter !== ALL && { status: statusFilter }),
    ...(typeFilter !== ALL && { job_type: typeFilter }),
  }

  const { data: jobs, isLoading } = useQuery({
    queryKey: ['jobs', filters],
    queryFn: () => listJobs(Object.keys(filters).length > 0 ? filters : undefined),
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.some((j) => j.status === 'pending' || j.status === 'in_progress')) {
        return 5000
      }
      return false
    },
  })

  const { data: accounts } = useQuery({
    queryKey: ['accounts'],
    queryFn: listAccounts,
  })

  const accountMap = new Map(accounts?.map((a) => [a.id, a.account_name]) ?? [])

  const filteredJobs = useMemo(() => {
    if (!jobs) return []
    const q = search.toLowerCase()
    if (!q) return jobs
    return jobs.filter(
      (j) =>
        j.job_type.toLowerCase().includes(q) ||
        j.status.toLowerCase().includes(q) ||
        (j.account_id
          ? (accountMap.get(j.account_id) ?? j.account_id) : ''
        ).toLowerCase().includes(q)
    )
  }, [jobs, search, accountMap])

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>

      <div className="flex gap-3">
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All statuses</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="in_progress">In Progress</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>

        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All types</SelectItem>
            <SelectItem value="provision_account">Provision Account</SelectItem>
            <SelectItem value="create_role">Create Role</SelectItem>
            <SelectItem value="update_role">Update Role</SelectItem>
            <SelectItem value="delete_role">Delete Role</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <SearchInput
        placeholder="Search jobs..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {isLoading ? (
        <div className="text-muted-foreground">Loading jobs...</div>
      ) : !jobs?.length ? (
        <div className="text-muted-foreground">No jobs found.</div>
      ) : filteredJobs.length === 0 ? (
        <div className="text-muted-foreground">No jobs match your search.</div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Type</TableHead>
              <TableHead>Account</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Started</TableHead>
              <TableHead>Completed</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredJobs.map((job) => (
              <TableRow key={job.id}>
                <TableCell className="font-mono text-sm">{job.job_type}</TableCell>
                <TableCell>
                  {job.account_id ? accountMap.get(job.account_id) ?? job.account_id : '—'}
                </TableCell>
                <TableCell>
                  <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
                </TableCell>
                <TableCell className="text-sm">{formatDate(job.started_at)}</TableCell>
                <TableCell className="text-sm">{formatDate(job.completed_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
