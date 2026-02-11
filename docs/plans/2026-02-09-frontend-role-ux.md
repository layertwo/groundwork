# Frontend Role UX Improvements

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve role management UX with update support, 1-click template creation, card-based layout, and cleaner account details.

**Architecture:** All changes are frontend-only. The backend already exposes `PATCH /api/accounts/{account_id}/roles/{role_id}` and the frontend API client already has `updateRole()`. We add a role edit dialog, a quick-create dropdown, replace the role table with cards, and reorganize the account detail header.

**Tech Stack:** React, TypeScript, TanStack React Query, Radix UI (Dialog, DropdownMenu, Select), Tailwind CSS, shadcn/ui Card component.

---

### Task 1: Add missing fields to frontend RoleResponse

The backend `RoleResponse` schema returns `status` and `error_message` but the frontend interface omits them. We need these for role cards (showing status badges, disabling actions on pending/updating roles).

**Files:**
- Modify: `frontend/src/api/roles.ts:3-17`

**Step 1: Add status and error_message to RoleResponse**

In `frontend/src/api/roles.ts`, add two fields to the `RoleResponse` interface:

```typescript
export interface RoleResponse {
  id: string
  account_id: string
  role_name: string
  role_arn: string
  status: string
  error_message: string | null
  allowed_groups: string[]
  managed_policy_arns: string[]
  inline_policy: Record<string, unknown> | null
  allowed_users: string[]
  api_session_duration: number
  console_session_duration: number
  description: string | null
  created_at: string
  updated_at: string
}
```

**Step 2: Commit**

```bash
git add frontend/src/api/roles.ts
git commit -m "feat: add status and error_message to RoleResponse interface"
```

---

### Task 2: Create RoleEditDialog component

A dialog for editing an existing role. Pre-fills all editable fields. Uses the existing `updateRole` API function and `TagInput` component.

**Files:**
- Create: `frontend/src/components/RoleEditDialog.tsx`

**Step 1: Create the RoleEditDialog component**

Create `frontend/src/components/RoleEditDialog.tsx`:

```tsx
import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import TagInput from '@/components/TagInput'
import { updateRole } from '@/api/roles'
import { ApiError } from '@/api/client'
import type { RoleResponse } from '@/api/roles'

interface RoleEditDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  role: RoleResponse | null
  accountId: string
  onUpdated: () => void
}

export default function RoleEditDialog({
  open,
  onOpenChange,
  role,
  accountId,
  onUpdated,
}: RoleEditDialogProps) {
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [description, setDescription] = useState('')
  const [managedPolicies, setManagedPolicies] = useState<string[]>([])
  const [inlinePolicy, setInlinePolicy] = useState('')
  const [allowedGroups, setAllowedGroups] = useState<string[]>([])
  const [allowedUsers, setAllowedUsers] = useState<string[]>([])
  const [apiSessionMinutes, setApiSessionMinutes] = useState(15)
  const [consoleSessionMinutes, setConsoleSessionMinutes] = useState(60)

  useEffect(() => {
    if (role && open) {
      setDescription(role.description ?? '')
      setManagedPolicies(role.managed_policy_arns)
      setInlinePolicy(role.inline_policy ? JSON.stringify(role.inline_policy, null, 2) : '')
      setAllowedGroups(role.allowed_groups)
      setAllowedUsers(role.allowed_users)
      setApiSessionMinutes(Math.round(role.api_session_duration / 60))
      setConsoleSessionMinutes(Math.round(role.console_session_duration / 60))
      setError('')
    }
  }, [role, open])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!role) return
    setError('')
    setSubmitting(true)

    try {
      if (
        apiSessionMinutes < 15 ||
        apiSessionMinutes > 720 ||
        !Number.isInteger(apiSessionMinutes)
      ) {
        setError('API session must be a whole number between 15 and 720 minutes')
        setSubmitting(false)
        return
      }
      if (
        consoleSessionMinutes < 15 ||
        consoleSessionMinutes > 720 ||
        !Number.isInteger(consoleSessionMinutes)
      ) {
        setError('Console session must be a whole number between 15 and 720 minutes')
        setSubmitting(false)
        return
      }

      let parsedInlinePolicy: Record<string, unknown> | null = null
      if (inlinePolicy.trim()) {
        try {
          parsedInlinePolicy = JSON.parse(inlinePolicy)
        } catch {
          setError('Invalid JSON in inline policy')
          setSubmitting(false)
          return
        }
      }

      await updateRole(accountId, role.id, {
        description: description || null,
        managed_policy_arns: managedPolicies,
        inline_policy: parsedInlinePolicy,
        allowed_groups: allowedGroups,
        allowed_users: allowedUsers,
        api_session_duration: apiSessionMinutes * 60,
        console_session_duration: consoleSessionMinutes * 60,
      })
      onUpdated()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to update role')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit {role?.role_name}</DialogTitle>
        </DialogHeader>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="edit_description">Description</Label>
            <Input
              id="edit_description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={1000}
            />
          </div>

          <div className="space-y-2">
            <Label>Managed Policy ARNs</Label>
            <TagInput
              value={managedPolicies}
              onChange={setManagedPolicies}
              placeholder="arn:aws:iam::aws:policy/..."
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="edit_inline_policy">Inline Policy (JSON)</Label>
            <Textarea
              id="edit_inline_policy"
              value={inlinePolicy}
              onChange={(e) => setInlinePolicy(e.target.value)}
              rows={6}
              maxLength={10240}
              className="font-mono text-sm"
              placeholder='{"Statement": []}'
            />
          </div>

          <div className="space-y-2">
            <Label>Allowed Groups</Label>
            <TagInput
              value={allowedGroups}
              onChange={setAllowedGroups}
              placeholder="Add group name..."
            />
          </div>

          <div className="space-y-2">
            <Label>Allowed Users</Label>
            <TagInput
              value={allowedUsers}
              onChange={setAllowedUsers}
              placeholder="Add user email or sub..."
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="edit_api_session">API Session (min)</Label>
              <Input
                id="edit_api_session"
                type="number"
                min={15}
                max={720}
                value={apiSessionMinutes}
                onChange={(e) => setApiSessionMinutes(Number(e.target.value))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit_console_session">Console Session (min)</Label>
              <Input
                id="edit_console_session"
                type="number"
                min={15}
                max={720}
                value={consoleSessionMinutes}
                onChange={(e) => setConsoleSessionMinutes(Number(e.target.value))}
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Saving...' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/RoleEditDialog.tsx
git commit -m "feat: add RoleEditDialog component for editing existing roles"
```

---

### Task 3: Rewrite AccountDetail with card layout, edit dialog, quick-create, and neat account info

This is the main task. We rewrite `AccountDetail.tsx` to:
1. Show account details in a clean labeled grid
2. Replace the role table with cards
3. Add the edit dialog integration
4. Add a quick-create dropdown for 1-click template role creation

**Files:**
- Modify: `frontend/src/pages/AccountDetail.tsx`

**Step 1: Rewrite AccountDetail.tsx**

Replace the full contents of `frontend/src/pages/AccountDetail.tsx`:

```tsx
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
    refetchInterval: isProvisioning ? 5000 : false,
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
```

**Step 2: Verify the build compiles**

Run: `cd frontend && npm run build`
Expected: No TypeScript or build errors.

**Step 3: Commit**

```bash
git add frontend/src/pages/AccountDetail.tsx
git commit -m "feat: rewrite account detail with role cards, edit dialog, quick-create, and info grid"
```

---

### Task 4: Verify and fix any build issues

**Step 1: Run the build**

Run: `cd frontend && npm run build`

If there are any missing imports or type issues, fix them.

**Step 2: Verify visually**

Run: `cd frontend && npm run dev`

Check `/accounts/<id>` page:
- Account info shows in a card with labeled grid
- Roles display as cards in a 2-column grid
- Each card shows status badge, groups, users, policies
- Edit button opens dialog with pre-filled fields
- Quick Create dropdown shows templates
- Add Role button still links to full creation form

**Step 3: Final commit if fixes were needed**

```bash
git add -A frontend/src/
git commit -m "fix: resolve build issues from account detail rewrite"
```
