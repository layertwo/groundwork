import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { createAccount } from '@/api/accounts'
import { ApiError } from '@/api/client'

export default function AccountCreate() {
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [form, setForm] = useState({
    account_name: '',
    account_email: '',
    organizational_unit: '',
    sso_user_email: '',
  })

  const set = (field: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const account = await createAccount(form)
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
          <Label htmlFor="account_name">Account Name</Label>
          <Input
            id="account_name"
            value={form.account_name}
            onChange={set('account_name')}
            required
            maxLength={50}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="account_email">Account Email</Label>
          <Input
            id="account_email"
            type="email"
            value={form.account_email}
            onChange={set('account_email')}
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="organizational_unit">Organizational Unit (OU)</Label>
          <Input
            id="organizational_unit"
            value={form.organizational_unit}
            onChange={set('organizational_unit')}
            required
            placeholder="ou-xxxx-xxxxxxxx or r-xxxx"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="sso_user_email">SSO User Email</Label>
          <Input
            id="sso_user_email"
            type="email"
            value={form.sso_user_email}
            onChange={set('sso_user_email')}
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
