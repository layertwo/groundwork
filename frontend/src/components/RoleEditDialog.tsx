import { useState, useEffect } from 'react'
import { toast } from 'sonner'
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
      toast.success('Role updated')
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
