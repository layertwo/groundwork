import { useState, useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAuth } from '@/context/AuthContext'
import { getAccount } from '@/api/accounts'
import { listRoles, assumeRole, getConsoleUrl, deleteRole } from '@/api/roles'
import { ApiError } from '@/api/client'
import { listJobs } from '@/api/jobs'
import SearchInput from '@/components/SearchInput'
import CredentialsDialog from '@/components/CredentialsDialog'
import type { AssumeRoleResponse } from '@/api/roles'

function statusVariant(status: string) {
  switch (status) {
    case 'active':
    case 'completed':
      return 'default' as const
    case 'failed':
      return 'destructive' as const
    default:
      return 'secondary' as const
  }
}

export default function AccountDetail() {
  const { id } = useParams<{ id: string }>()
  const { isAdmin } = useAuth()
  const [credentials, setCredentials] = useState<AssumeRoleResponse | null>(null)
  const [credentialsRoleName, setCredentialsRoleName] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleDialogChange = (open: boolean) => {
    setDialogOpen(open)
    if (!open) setCredentials(null)
  }

  const { data: account, isLoading: accountLoading } = useQuery({
    queryKey: ['account', id],
    queryFn: () => getAccount(id!),
    enabled: !!id,
  })

  const { data: allRoles, refetch: refetchRoles } = useQuery({
    queryKey: ['roles'],
    queryFn: listRoles,
  })

  const roles = allRoles?.filter((r) => r.account_id === id) ?? []

  const [roleSearch, setRoleSearch] = useState('')
  const filteredRoles = useMemo(() => {
    const q = roleSearch.toLowerCase()
    if (!q) return roles
    return roles.filter(
      (r) =>
        r.role_name.toLowerCase().includes(q) ||
        (r.description ?? '').toLowerCase().includes(q) ||
        r.allowed_groups.some((g) => g.toLowerCase().includes(q)) ||
        r.allowed_users.some((u) => u.toLowerCase().includes(q))
    )
  }, [roles, roleSearch])

  const isProvisioning = account?.status === 'pending' || account?.status === 'provisioning'

  const { data: jobs } = useQuery({
    queryKey: ['jobs', id],
    queryFn: () => listJobs({ account_id: id }),
    enabled: !!id && isProvisioning,
    refetchInterval: isProvisioning ? 5000 : false,
  })

  const handleFederate = async (roleId: string) => {
    setLoading(roleId)
    setError(null)
    try {
      const res = await getConsoleUrl(roleId)
      const url = new URL(res.console_url)
      if (url.protocol !== 'https:' || !url.hostname.endsWith('.aws.amazon.com')) {
        setError('Invalid console URL returned')
        return
      }
      window.open(res.console_url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to federate')
    } finally {
      setLoading(null)
    }
  }

  const handleCopyCli = async (roleId: string, roleName: string) => {
    setLoading(roleId)
    setError(null)
    try {
      const res = await assumeRole(roleId)
      setCredentials(res)
      setCredentialsRoleName(roleName)
      setDialogOpen(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to get credentials')
    } finally {
      setLoading(null)
    }
  }

  const handleDelete = async (roleId: string) => {
    if (!id || !confirm('Delete this role? This will remove the IAM role from AWS.')) return
    setError(null)
    try {
      await deleteRole(id, roleId)
      refetchRoles()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to delete role')
    }
  }

  if (accountLoading) {
    return <div className="text-muted-foreground">Loading...</div>
  }

  if (!account) {
    return <div className="text-muted-foreground">Account not found.</div>
  }

  return (
    <div className="space-y-6">
      <Link to="/" className="text-sm text-muted-foreground hover:underline">
        &larr; Accounts
      </Link>

      <div className="space-y-1">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">
            {account.account_name}
          </h1>
          <Badge variant={statusVariant(account.status)}>{account.status}</Badge>
        </div>
        <div className="text-sm text-muted-foreground space-x-4">
          <span>AWS Account: <span className="font-mono">{account.aws_account_id ?? '—'}</span></span>
          <span>OU: <span className="font-mono">{account.organizational_unit}</span></span>
        </div>
        <div className="text-sm text-muted-foreground space-x-4">
          <span>Email: {account.account_email}</span>
          <span>SSO: {account.sso_user_email}</span>
        </div>
        {account.error_message && (
          <p className="text-sm text-destructive">{account.error_message}</p>
        )}
      </div>

      {isProvisioning && jobs && jobs.length > 0 && (
        <div className="rounded-md border p-4 space-y-2">
          <h3 className="text-sm font-medium">Provisioning Jobs</h3>
          {jobs.map((job) => (
            <div key={job.id} className="flex items-center gap-2 text-sm">
              <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
              <span>{job.job_type}</span>
              {job.error_message && (
                <span className="text-destructive">{job.error_message}</span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Roles</h2>
          {isAdmin && account.status === 'active' && (
            <Button asChild size="sm">
              <Link to={`/accounts/${id}/roles/new`}>Add Role</Link>
            </Button>
          )}
        </div>

        <SearchInput
          placeholder="Search roles..."
          value={roleSearch}
          onChange={(e) => setRoleSearch(e.target.value)}
        />

        {roles.length === 0 ? (
          <div className="text-sm text-muted-foreground">No roles on this account.</div>
        ) : filteredRoles.length === 0 ? (
          <div className="text-sm text-muted-foreground">No roles match your search.</div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Role Name</TableHead>
                <TableHead>Groups</TableHead>
                <TableHead>Users</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredRoles.map((role) => (
                <TableRow key={role.id}>
                  <TableCell className="font-medium">
                    {role.role_name}
                    {role.description && (
                      <span className="block text-xs text-muted-foreground">
                        {role.description}
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {role.allowed_groups.length > 0
                        ? role.allowed_groups.map((g) => (
                            <Badge key={g} variant="outline" className="text-xs">
                              {g}
                            </Badge>
                          ))
                        : '—'}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {role.allowed_users.length > 0
                        ? role.allowed_users.map((u) => (
                            <Badge key={u} variant="outline" className="text-xs">
                              {u}
                            </Badge>
                          ))
                        : '—'}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={loading === role.id || account.status !== 'active'}
                        onClick={() => handleFederate(role.id)}
                      >
                        Federate
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={loading === role.id || account.status !== 'active'}
                        onClick={() => handleCopyCli(role.id, role.role_name)}
                      >
                        Copy CLI
                      </Button>
                      {isAdmin && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive"
                          onClick={() => handleDelete(role.id)}
                        >
                          Delete
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <CredentialsDialog
        open={dialogOpen}
        onOpenChange={handleDialogChange}
        credentials={credentials}
        roleName={credentialsRoleName}
        accountName={account.account_name}
      />
    </div>
  )
}
