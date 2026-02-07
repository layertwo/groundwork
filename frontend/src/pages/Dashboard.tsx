import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
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
import FederateDropdown from '@/components/FederateDropdown'

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
        <h1 className="text-4xl font-bold tracking-tight">Groundwork</h1>
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

  if (authLoading) {
    return <div className="flex items-center justify-center h-64">Loading...</div>
  }

  if (!isAuthenticated) {
    return <Landing />
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Accounts</h1>
        {isAdmin && (
          <Button asChild>
            <Link to="/accounts/new">New Account</Link>
          </Button>
        )}
      </div>

      {accountsLoading ? (
        <div className="text-muted-foreground">Loading accounts...</div>
      ) : !accounts?.length ? (
        <div className="text-muted-foreground">No accounts found.</div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>AWS ID</TableHead>
              <TableHead>OU</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {accounts.map((account) => (
              <TableRow key={account.id}>
                <TableCell>
                  <Link
                    to={`/accounts/${account.id}`}
                    className="font-medium hover:underline"
                  >
                    {account.account_name}
                  </Link>
                </TableCell>
                <TableCell className="font-mono text-sm">
                  {account.aws_account_id ?? '—'}
                </TableCell>
                <TableCell className="font-mono text-sm">
                  {account.organizational_unit}
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
                    roles={rolesByAccount[account.id] ?? []}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
