import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Folder, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAuth } from '@/context/AuthContext'
import { listAccounts } from '@/api/accounts'
import { listRoles } from '@/api/roles'
import { createJob } from '@/api/jobs'
import FederateDropdown from '@/components/FederateDropdown'
import SearchInput from '@/components/SearchInput'
import { consumeRedirectUrl } from '@/components/ProtectedRoute'

function statusVariant(status: string) {
  switch (status) {
    case 'active':
      return 'default' as const
    case 'failed':
      return 'destructive' as const
    default:
      return 'secondary' as const
  }
}

function Landing() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6">
      <div className="text-center space-y-2">
        <p className="text-muted-foreground text-lg">
          AWS account &amp; role management
        </p>
      </div>
      <Button asChild size="lg">
        <a href="/api/auth/login">Sign in with SSO</a>
      </Button>
    </div>
  )
}

export default function Dashboard() {
  const { isAuthenticated, isAdmin, isLoading: authLoading } = useAuth()
  const [search, setSearch] = useState('')
  const [showClosed, setShowClosed] = useState(false)

  const navigate = useNavigate()

  useEffect(() => {
    if (isAuthenticated) {
      const redirect = consumeRedirectUrl()
      if (redirect) {
        navigate(redirect, { replace: true })
      }
    }
  }, [isAuthenticated, navigate])

  const { data: accounts, isLoading: accountsLoading } = useQuery({
    queryKey: ['accounts'],
    queryFn: listAccounts,
    enabled: isAuthenticated,
  })

  const { data: roles } = useQuery({
    queryKey: ['roles'],
    queryFn: listRoles,
    enabled: isAuthenticated,
  })

  const queryClient = useQueryClient()

  const syncMutation = useMutation({
    mutationFn: () => createJob({ job_type: 'sync_accounts' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      navigate('/jobs')
    },
  })

  const rolesByAccount = useMemo(() => {
    if (!roles) return {}
    const map: Record<string, typeof roles> = {}
    for (const role of roles) {
      const key = role.account_id
      if (!map[key]) map[key] = []
      map[key].push(role)
    }
    return map
  }, [roles])

  const grouped = useMemo(() => {
    if (!accounts) return []
    let filtered = accounts

    // Hide suspended/closed accounts unless toggled
    if (!showClosed) {
      filtered = filtered.filter(
        (a) => !a.aws_status || a.aws_status === 'ACTIVE'
      )
    }

    const q = search.toLowerCase()
    if (q) {
      filtered = filtered.filter(
        (a) =>
          a.account_name.toLowerCase().includes(q) ||
          a.account_email.toLowerCase().includes(q) ||
          (a.aws_account_id ?? '').includes(q) ||
          a.organizational_unit.toLowerCase().includes(q)
      )
    }

    const map = new Map<string, typeof accounts>()
    for (const a of filtered) {
      const ou = a.organizational_unit
      if (!map.has(ou)) map.set(ou, [])
      map.get(ou)!.push(a)
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [accounts, search, showClosed])

  if (authLoading) {
    return <div className="flex items-center justify-center h-64">Loading...</div>
  }

  if (!isAuthenticated) {
    return <Landing />
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Accounts</h1>
        {isAdmin && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => syncMutation.mutate()}
              disabled={syncMutation.isPending}
            >
              <RefreshCw className={`mr-1.5 size-3.5 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
              Sync Accounts
            </Button>
            <Button asChild>
              <Link to="/accounts/new">+ New Account</Link>
            </Button>
          </div>
        )}
      </div>

      <SearchInput
        placeholder="Search accounts..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {accounts && accounts.some((a) => a.aws_status && a.aws_status !== 'ACTIVE') && (
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={showClosed}
            onChange={(e) => setShowClosed(e.target.checked)}
            className="rounded"
          />
          Show suspended/closed accounts
        </label>
      )}

      {accountsLoading ? (
        <div className="text-muted-foreground">Loading accounts...</div>
      ) : !accounts?.length ? (
        <div className="text-muted-foreground">No accounts found.</div>
      ) : grouped.length === 0 ? (
        <div className="text-muted-foreground">No accounts match your search.</div>
      ) : (
        <div className="rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>AWS Account ID</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {grouped.map(([ou, ouAccounts]) => (
                <>
                  <TableRow key={`ou-${ou}`} className="bg-white/[0.02] hover:bg-white/[0.02]">
                    <TableCell
                      colSpan={5}
                      className="py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                    >
                      <Folder className="mr-1.5 inline-block size-3.5 align-[-3px]" />
                      {ou}
                    </TableCell>
                  </TableRow>
                  {ouAccounts.map((account) => (
                    <TableRow
                      key={account.id}
                      className={
                        account.aws_status && account.aws_status !== 'ACTIVE'
                          ? 'opacity-50'
                          : undefined
                      }
                    >
                      <TableCell>
                        <Link
                          to={`/accounts/${account.id}`}
                          className="font-medium hover:underline"
                        >
                          {account.account_name}
                        </Link>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {account.account_email}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {account.aws_account_id ?? '—'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusVariant(account.status)}>
                          {account.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <FederateDropdown
                          accountName={account.account_name}
                          accountStatus={account.status}
                          awsAccountId={account.aws_account_id ?? ''}
                          roles={rolesByAccount[account.id] ?? []}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
