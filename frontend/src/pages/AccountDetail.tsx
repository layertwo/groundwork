import { useState, useMemo } from 'react'
import { toast } from 'sonner'
import { Pencil, Check, X } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  HoverCard,
  HoverCardTrigger,
  HoverCardContent,
} from '@/components/ui/hover-card'
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/context/AuthContext'
import { getAccount, updateAccount } from '@/api/accounts'
import {
  listRoles,
  federate,
  deleteRole,
  createRole,
  getRoleTemplates,
  fixDrift,
} from '@/api/roles'
import { ApiError } from '@/api/client'
import { AWS_COLORS, AWS_COLOR_NAMES, awsColorLabel } from '@/lib/aws-colors'
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
    case 'drifted':
      return 'destructive' as const
    default:
      return 'secondary' as const
  }
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

export default function AccountDetail() {
  const { id } = useParams<{ id: string }>()
  const { isAdmin } = useAuth()
  const queryClient = useQueryClient()
  const [credentials, setCredentials] = useState<AssumeRoleResponse | null>(null)
  const [credentialsRoleName, setCredentialsRoleName] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [loading, setLoading] = useState<string | null>(null)
  const [deleteRoleId, setDeleteRoleId] = useState<string | null>(null)

  // Edit dialog state
  const [editRole, setEditRole] = useState<RoleResponse | null>(null)
  const [editOpen, setEditOpen] = useState(false)

  // Quick-create state
  const [creating, setCreating] = useState(false)

  // Alias editing state
  const [editingAlias, setEditingAlias] = useState(false)
  const [aliasValue, setAliasValue] = useState('')

  const aliasMutation = useMutation({
    mutationFn: (alias: string) => updateAccount(id!, { alias }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['account', id] })
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      setEditingAlias(false)
      toast.success('Account alias updated')
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.detail : 'Failed to update alias')
    },
  })

  const colorMutation = useMutation({
    mutationFn: (color: string) => updateAccount(id!, { color }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['account', id] })
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      toast.success('Account color updated')
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.detail : 'Failed to update color')
    },
  })

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
    try {
      const res = (await federate(
        account!.aws_account_id!,
        roleName,
        'console',
      )) as ConsoleUrlResponse
      const url = new URL(res.console_url)
      if (url.protocol !== 'https:' || !url.hostname.endsWith('.aws.amazon.com')) {
        toast.error('Invalid console URL returned')
        return
      }
      window.open(res.console_url, '_blank', 'noopener,noreferrer')
      toast.success('Opened AWS Console')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Failed to federate')
    } finally {
      setLoading(null)
    }
  }

  const handleCopyCli = async (roleName: string) => {
    setLoading(roleName)
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
      toast.error(err instanceof ApiError ? err.detail : 'Failed to get credentials')
    } finally {
      setLoading(null)
    }
  }

  const handleDelete = async () => {
    if (!id || !deleteRoleId) return
    try {
      await deleteRole(id, deleteRoleId)
      refetchRoles()
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      toast.success('Role deletion started')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Failed to delete role')
    } finally {
      setDeleteRoleId(null)
    }
  }

  const handleEdit = (role: RoleResponse) => {
    setEditRole(role)
    setEditOpen(true)
  }

  const handleQuickCreate = async (templateId: string, templateName: string) => {
    if (!id) return
    setCreating(true)
    try {
      await createRole(id, {
        role_name: templateName,
        template_id: templateId,
      })
      refetchRoles()
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      toast.success('Role creation started')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Failed to create role from template')
    } finally {
      setCreating(false)
    }
  }

  if (accountLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-8 w-32" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      </div>
    )
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
            <div>
              <dt className="text-muted-foreground">Account Alias</dt>
              <dd>
                {editingAlias ? (
                  <div className="flex items-center gap-1">
                    <Input
                      value={aliasValue}
                      onChange={(e) => setAliasValue(e.target.value)}
                      placeholder="e.g. my-prod-account"
                      className="h-7 w-48 text-sm"
                      pattern="[a-z0-9-]*"
                    />
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={() => aliasMutation.mutate(aliasValue)}
                      disabled={aliasMutation.isPending}
                    >
                      <Check className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={() => setEditingAlias(false)}
                    >
                      <X className="size-3.5" />
                    </Button>
                  </div>
                ) : (
                  <span className="flex items-center gap-1.5">
                    {account.alias ?? '—'}
                    {isAdmin && account.status === 'active' && (
                      <Button
                        variant="ghost"
                        size="xs"
                        onClick={() => {
                          setAliasValue(account.alias ?? '')
                          setEditingAlias(true)
                        }}
                      >
                        <Pencil className="size-3" />
                      </Button>
                    )}
                  </span>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Account Color</dt>
              <dd>
                {isAdmin && account.status === 'active' ? (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="xs" className="gap-1.5" disabled={colorMutation.isPending}>
                        {account.color && AWS_COLORS[account.color] ? (
                          <>
                            <span
                              className="inline-block size-3 rounded-sm"
                              style={{ backgroundColor: AWS_COLORS[account.color] }}
                            />
                            {awsColorLabel(account.color)}
                          </>
                        ) : (
                          'None'
                        )}
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent>
                      <DropdownMenuItem onClick={() => colorMutation.mutate('none')}>
                        None
                      </DropdownMenuItem>
                      {AWS_COLOR_NAMES.map((c) => (
                        <DropdownMenuItem key={c} onClick={() => colorMutation.mutate(c)}>
                          <span
                            className="inline-block size-3 rounded-sm mr-2"
                            style={{ backgroundColor: AWS_COLORS[c] }}
                          />
                          {awsColorLabel(c)}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                ) : (
                  <span className="flex items-center gap-1.5">
                    {account.color && AWS_COLORS[account.color] ? (
                      <>
                        <span
                          className="inline-block size-3 rounded-sm"
                          style={{ backgroundColor: AWS_COLORS[account.color] }}
                        />
                        {awsColorLabel(account.color)}
                      </>
                    ) : (
                      '—'
                    )}
                  </span>
                )}
              </dd>
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
                  {role.last_used_at ? (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <p className="text-xs text-muted-foreground cursor-default">
                          Last used {relativeTime(role.last_used_at)}
                        </p>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>{new Date(role.last_used_at).toLocaleString()}</p>
                      </TooltipContent>
                    </Tooltip>
                  ) : (
                    <p className="text-xs text-muted-foreground">Never used</p>
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
                          <HoverCard key={arn} openDelay={200} closeDelay={0}>
                            <HoverCardTrigger asChild>
                              <Badge variant="secondary" className="text-xs cursor-default">
                                {arn.split('/').pop()}
                              </Badge>
                            </HoverCardTrigger>
                            <HoverCardContent className="w-auto max-w-sm">
                              <p className="text-xs font-mono break-all">{arn}</p>
                            </HoverCardContent>
                          </HoverCard>
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
                      {role.status === 'drifted' && (
                        <Button
                          variant="outline"
                          size="xs"
                          onClick={async () => {
                            try {
                              await fixDrift(id!, role.id)
                              refetchRoles()
                              toast.success('Drift fix started')
                            } catch (err) {
                              toast.error(
                                err instanceof ApiError ? err.detail : 'Failed to fix drift'
                              )
                            }
                          }}
                        >
                          Fix Drift
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="xs"
                        className="text-destructive"
                        onClick={() => setDeleteRoleId(role.id)}
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

      <AlertDialog open={!!deleteRoleId} onOpenChange={(open) => !open && setDeleteRoleId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete role?</AlertDialogTitle>
            <AlertDialogDescription>
              This will remove the IAM role from AWS. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
