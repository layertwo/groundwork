import { useState, useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardAction,
} from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuth } from '@/context/AuthContext'
import { getAccount } from '@/api/accounts'
import {
  listRoles,
  federate,
  deleteRole,
  createRole,
  getRoleTemplates,
} from '@/api/roles'
import { ApiError } from '@/api/client'
import { listJobs } from '@/api/jobs'
import SearchInput from '@/components/SearchInput'
import CredentialsDialog from '@/components/CredentialsDialog'
import RoleEditDialog from '@/components/RoleEditDialog'
import type { AssumeRoleResponse, ConsoleUrlResponse, RoleResponse } from '@/api/roles'

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
  const queryClient = useQueryClient()
  const [credentials, setCredentials] = useState<AssumeRoleResponse | null>(null)
  const [credentialsRoleName, setCredentialsRoleName] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Edit dialog state
  const [editRole, setEditRole] = useState<RoleResponse | null>(null)
  const [editOpen, setEditOpen] = useState(false)

  // Quick-create state
  const [creating, setCreating] = useState(false)

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

  const { data: templates } = useQuery({
    queryKey: ['role-templates'],
    queryFn: getRoleTemplates,
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
  })

  const handleFederate = async (roleName: string) => {
    setLoading(roleName)
    setError(null)
    try {
      const res = (await federate(
        account!.aws_account_id!,
        roleName,
        'console',
      )) as ConsoleUrlResponse
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

  const handleCopyCli = async (roleName: string) => {
    setLoading(roleName)
    setError(null)
    try {
      const res = (await federate(
        account!.aws_account_id!,
        roleName,
        'cli',
      )) as AssumeRoleResponse
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
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to delete role')
    }
  }

  const handleEdit = (role: RoleResponse) => {
    setEditRole(role)
    setEditOpen(true)
  }

  const handleQuickCreate = async (templateId: string, templateName: string) => {
    if (!id) return
    setError(null)
    setCreating(true)
    try {
      await createRole(id, {
        role_name: templateName,
        template_id: templateId,
      })
      refetchRoles()
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create role from template')
    } finally {
      setCreating(false)
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

      {/* Account details card */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <CardTitle className="text-2xl">{account.account_name}</CardTitle>
            <Badge variant={statusVariant(account.status)}>{account.status}</Badge>
            {account.aws_status && account.aws_status !== 'ACTIVE' && (
              <Badge variant="secondary">{account.aws_status.toLowerCase()}</Badge>
            )}
          </div>
          {account.error_message && (
            <p className="text-sm text-destructive">{account.error_message}</p>
          )}
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
            <div>
              <dt className="text-muted-foreground">AWS Account ID</dt>
              <dd className="font-mono">{account.aws_account_id ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Organizational Unit</dt>
              <dd className="font-mono">{account.organizational_unit}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Email</dt>
              <dd>{account.account_email}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">SSO User</dt>
              <dd>{account.sso_user_email}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Created</dt>
              <dd>{new Date(account.created_at).toLocaleDateString()}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Last Updated</dt>
              <dd>{new Date(account.updated_at).toLocaleDateString()}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {/* Provisioning jobs */}
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

      {/* Roles section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Roles</h2>
          {isAdmin && account.status === 'active' && (
            <div className="flex items-center gap-2">
              {templates && templates.length > 0 && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" disabled={creating}>
                      {creating ? 'Creating...' : 'Quick Create'}
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {templates.map((t) => (
                      <DropdownMenuItem
                        key={t.id}
                        onClick={() => handleQuickCreate(t.id, t.name)}
                      >
                        {t.name}
                        {t.description && (
                          <span className="ml-2 text-muted-foreground text-xs">
                            {t.description}
                          </span>
                        )}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
              <Button asChild size="sm">
                <Link to={`/accounts/${id}/roles/new`}>Add Role</Link>
              </Button>
            </div>
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
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredRoles.map((role) => (
              <Card key={role.id}>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <CardTitle className="text-base">{role.role_name}</CardTitle>
                    <Badge variant={statusVariant(role.status)} className="text-xs">
                      {role.status}
                    </Badge>
                  </div>
                  {role.description && (
                    <CardDescription>{role.description}</CardDescription>
                  )}
                  {role.error_message && (
                    <p className="text-xs text-destructive">{role.error_message}</p>
                  )}
                  <CardAction>
                    <div className="flex gap-1">
                      <Button
                        variant="outline"
                        size="xs"
                        disabled={
                          loading === role.role_name ||
                          account.status !== 'active' ||
                          role.status !== 'active'
                        }
                        onClick={() => handleFederate(role.role_name)}
                      >
                        Federate
                      </Button>
                      <Button
                        variant="outline"
                        size="xs"
                        disabled={
                          loading === role.role_name ||
                          account.status !== 'active' ||
                          role.status !== 'active'
                        }
                        onClick={() => handleCopyCli(role.role_name)}
                      >
                        CLI
                      </Button>
                    </div>
                  </CardAction>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div>
                    <span className="text-xs text-muted-foreground">Groups</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {role.allowed_groups.length > 0
                        ? role.allowed_groups.map((g) => (
                            <Badge key={g} variant="outline" className="text-xs">
                              {g}
                            </Badge>
                          ))
                        : <span className="text-xs text-muted-foreground">—</span>}
                    </div>
                  </div>
                  <div>
                    <span className="text-xs text-muted-foreground">Users</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {role.allowed_users.length > 0
                        ? role.allowed_users.map((u) => (
                            <Badge key={u} variant="outline" className="text-xs">
                              {u}
                            </Badge>
                          ))
                        : <span className="text-xs text-muted-foreground">—</span>}
                    </div>
                  </div>
                  {role.managed_policy_arns.length > 0 && (
                    <div>
                      <span className="text-xs text-muted-foreground">Policies</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {role.managed_policy_arns.map((arn) => (
                          <Badge key={arn} variant="secondary" className="text-xs">
                            {arn.split('/').pop()}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {isAdmin && (
                    <div className="flex gap-1 pt-1">
                      <Button
                        variant="outline"
                        size="xs"
                        onClick={() => handleEdit(role)}
                        disabled={role.status === 'pending' || role.status === 'deleting'}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="xs"
                        className="text-destructive"
                        onClick={() => handleDelete(role.id)}
                        disabled={role.status === 'updating'}
                      >
                        Delete
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
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

      <RoleEditDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        role={editRole}
        accountId={id!}
        onUpdated={() => {
          refetchRoles()
          queryClient.invalidateQueries({ queryKey: ['account', id] })
        }}
      />
    </div>
  )
}
