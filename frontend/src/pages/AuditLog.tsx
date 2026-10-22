import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
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
import { listAuditLogs } from '@/api/audit'
import SearchInput from '@/components/SearchInput'

const ALL = '__all__'
const PAGE_SIZE = 50

function formatDate(date: Date): string {
  return date.toLocaleString()
}

function formatDetail(detail: unknown): string {
  if (!detail || typeof detail !== 'object' || Object.keys(detail).length === 0) return '—'
  return Object.entries(detail as Record<string, unknown>)
    .map(([key, value]) => {
      const text = typeof value === 'object' ? JSON.stringify(value) : String(value)
      return `${key}=${text}`
    })
    .join(' ')
}

export default function AuditLog() {
  const [resourceType, setResourceType] = useState(ALL)
  const [action, setAction] = useState('')
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['audit', { resourceType, action, page }],
    queryFn: () =>
      listAuditLogs({
        ...(resourceType !== ALL && { resourceType: resourceType }),
        ...(action && { action }),
        page,
        pageSize: PAGE_SIZE,
      }),
  })

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.pageSize)) : 1

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Audit Log</h1>

      <div className="flex gap-3">
        <Select
          value={resourceType}
          onValueChange={(value) => {
            setResourceType(value)
            setPage(1)
          }}
        >
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Resource" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All resources</SelectItem>
            <SelectItem value="account">Accounts</SelectItem>
            <SelectItem value="role">Roles</SelectItem>
            <SelectItem value="session">Sessions</SelectItem>
          </SelectContent>
        </Select>

        <SearchInput
          className="w-64"
          placeholder="Filter by action..."
          value={action}
          onChange={(e) => {
            setAction(e.target.value)
            setPage(1)
          }}
        />
      </div>

      {isLoading ? (
        <div className="text-muted-foreground">Loading audit log...</div>
      ) : !data?.items.length ? (
        <div className="text-muted-foreground">No audit entries found.</div>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Resource</TableHead>
                <TableHead>Detail</TableHead>
                <TableHead>IP</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="text-sm whitespace-nowrap">
                    {formatDate(entry.createdAt)}
                  </TableCell>
                  <TableCell>{entry.user?.displayName ?? 'system'}</TableCell>
                  <TableCell className="font-mono text-sm">{entry.action}</TableCell>
                  <TableCell className="text-sm">
                    {entry.resourceType
                      ? `${entry.resourceType}/${entry.resourceId ?? '—'}`
                      : '—'}
                  </TableCell>
                  <TableCell
                    className="max-w-72 truncate text-sm text-muted-foreground"
                    title={formatDetail(entry.detail)}
                  >
                    {formatDetail(entry.detail)}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {entry.ipAddress ?? '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 1}
          onClick={() => setPage((p) => p - 1)}
        >
          Previous
        </Button>
        <span>
          Page {data?.page ?? page} of {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= totalPages}
          onClick={() => setPage((p) => p + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  )
}
