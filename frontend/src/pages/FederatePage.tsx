import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { federate } from '@/api/roles'
import { ApiError } from '@/api/client'
import type { ConsoleUrlResponse } from '@/api/roles'

export default function FederatePage() {
  const [params] = useSearchParams()
  const accountId = params.get('account_id')
  const roleName = params.get('role_name')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!accountId || !roleName) {
      setError('Missing account_id or role_name parameter')
      return
    }

    let cancelled = false

    federate(accountId, roleName, 'console')
      .then((res) => {
        if (cancelled) return
        const { console_url } = res as ConsoleUrlResponse
        const url = new URL(console_url)
        if (url.protocol !== 'https:' || !url.hostname.endsWith('.aws.amazon.com')) {
          setError('Invalid console URL returned')
          return
        }
        window.location.href = console_url
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof ApiError ? err.detail : 'Failed to federate')
      })

    return () => {
      cancelled = true
    }
  }, [accountId, roleName])

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4">
        <p className="text-destructive">{error}</p>
        <Link to="/" className="text-sm text-muted-foreground hover:underline">
          Back to Dashboard
        </Link>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[40vh] gap-2">
      <p className="text-muted-foreground">Redirecting to AWS Console...</p>
    </div>
  )
}
