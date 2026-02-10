import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import TagInput from '@/components/TagInput'
import { createRole, getRoleTemplates } from '@/api/roles'
import { getAccount } from '@/api/accounts'
import { ApiError } from '@/api/client'

type Mode = 'template' | 'custom'

export default function RoleCreate() {
  const { id: accountId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [mode, setMode] = useState<Mode>('custom')

  const [roleName, setRoleName] = useState('')
  const [description, setDescription] = useState('')
  const [templateId, setTemplateId] = useState<string | null>(null)
  const [managedPolicies, setManagedPolicies] = useState<string[]>([])
  const [inlinePolicy, setInlinePolicy] = useState('')
  const [allowedGroups, setAllowedGroups] = useState<string[]>([])
  const [allowedUsers, setAllowedUsers] = useState<string[]>([])
  const [apiSessionMinutes, setApiSessionMinutes] = useState(15)
  const [consoleSessionMinutes, setConsoleSessionMinutes] = useState(60)

  const { data: account } = useQuery({
    queryKey: ['account', accountId],
    queryFn: () => getAccount(accountId!),
    enabled: !!accountId,
  })

  const { data: templates } = useQuery({
    queryKey: ['role-templates'],
    queryFn: getRoleTemplates,
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!accountId) return
    setError('')
    setSubmitting(true)

    try {
      if (apiSessionMinutes < 15 || apiSessionMinutes > 720 || !Number.isInteger(apiSessionMinutes)) {
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
      if (mode === 'custom' && inlinePolicy.trim()) {
        try {
          parsedInlinePolicy = JSON.parse(inlinePolicy)
        } catch {
          setError('Invalid JSON in inline policy')
          setSubmitting(false)
          return
        }
      }

      await createRole(accountId, {
        role_name: roleName,
        template_id: mode === 'template' ? templateId : null,
        managed_policy_arns: mode === 'custom' ? managedPolicies : [],
        inline_policy: parsedInlinePolicy,
        allowed_groups: allowedGroups,
        allowed_users: allowedUsers,
        api_session_duration: apiSessionMinutes * 60,
        console_session_duration: consoleSessionMinutes * 60,
        description: description || null,
      })
      await queryClient.invalidateQueries({ queryKey: ['roles'] })
      navigate(`/accounts/${accountId}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create role')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-lg space-y-6">
      <Link
        to={`/accounts/${accountId}`}
        className="text-sm text-muted-foreground hover:underline"
      >
        &larr; {account?.account_name ?? 'Account'}
      </Link>

      <h1 className="text-2xl font-semibold tracking-tight">Create Role</h1>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="role_name">Role Name</Label>
          <Input
            id="role_name"
            value={roleName}
            onChange={(e) => setRoleName(e.target.value)}
            required
            maxLength={128}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="description">Description</Label>
          <Input
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={1000}
          />
        </div>

        <div className="flex gap-2">
          <Button
            type="button"
            variant={mode === 'template' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setMode('template')}
          >
            From Template
          </Button>
          <Button
            type="button"
            variant={mode === 'custom' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setMode('custom')}
          >
            Custom
          </Button>
        </div>

        {mode === 'template' && (
          <div className="space-y-2">
            <Label>Template</Label>
            <Select value={templateId ?? ''} onValueChange={setTemplateId}>
              <SelectTrigger>
                <SelectValue placeholder="Select a template..." />
              </SelectTrigger>
              <SelectContent>
                {templates?.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name}
                    {t.description && ` — ${t.description}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {mode === 'custom' && (
          <>
            <div className="space-y-2">
              <Label>Managed Policy ARNs</Label>
              <TagInput
                value={managedPolicies}
                onChange={setManagedPolicies}
                placeholder="arn:aws:iam::aws:policy/..."
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="inline_policy">Inline Policy (JSON)</Label>
              <Textarea
                id="inline_policy"
                value={inlinePolicy}
                onChange={(e) => setInlinePolicy(e.target.value)}
                rows={6}
                maxLength={10240}
                className="font-mono text-sm"
                placeholder='{"Statement": []}'
              />
            </div>
          </>
        )}

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
            <Label htmlFor="api_session">API Session (min)</Label>
            <Input
              id="api_session"
              type="number"
              min={15}
              max={720}
              value={apiSessionMinutes}
              onChange={(e) => setApiSessionMinutes(Number(e.target.value))}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="console_session">Console Session (min)</Label>
            <Input
              id="console_session"
              type="number"
              min={15}
              max={720}
              value={consoleSessionMinutes}
              onChange={(e) => setConsoleSessionMinutes(Number(e.target.value))}
            />
          </div>
        </div>

        <div className="flex gap-2 pt-2">
          <Button type="button" variant="outline" asChild>
            <Link to={`/accounts/${accountId}`}>Cancel</Link>
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? 'Creating...' : 'Create Role'}
          </Button>
        </div>
      </form>
    </div>
  )
}
