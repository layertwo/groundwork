import { useState } from 'react'
import { toast } from 'sonner'
import { Link, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { createAccount } from '@/api/accounts'
import { ApiError } from '@/api/client'

export default function AccountCreate() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [form, setForm] = useState({
    accountName: '',
    accountEmail: '',
    organizationalUnit: '',
    ssoUserEmail: '',
  })

  const set = (field: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const account = await createAccount(form)
      await queryClient.invalidateQueries({ queryKey: ['accounts'] })
      toast.success('Account created')
      navigate(`/accounts/${account.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create account')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-lg space-y-6">
      <Link to="/" className="text-sm text-muted-foreground hover:underline">
        &larr; Accounts
      </Link>

      <h1 className="text-2xl font-semibold tracking-tight">Create Account</h1>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="accountName">Account Name</Label>
          <Input
            id="accountName"
            value={form.accountName}
            onChange={set('accountName')}
            required
            maxLength={50}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="accountEmail">Account Email</Label>
          <Input
            id="accountEmail"
            type="email"
            value={form.accountEmail}
            onChange={set('accountEmail')}
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="organizationalUnit">Organizational Unit (OU)</Label>
          <Input
            id="organizationalUnit"
            value={form.organizationalUnit}
            onChange={set('organizationalUnit')}
            required
            placeholder="ou-xxxx-xxxxxxxx or r-xxxx"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="ssoUserEmail">SSO User Email</Label>
          <Input
            id="ssoUserEmail"
            type="email"
            value={form.ssoUserEmail}
            onChange={set('ssoUserEmail')}
            required
          />
        </div>
        <div className="flex gap-2 pt-2">
          <Button type="button" variant="outline" asChild>
            <Link to="/">Cancel</Link>
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? 'Creating...' : 'Create Account'}
          </Button>
        </div>
      </form>
    </div>
  )
}
