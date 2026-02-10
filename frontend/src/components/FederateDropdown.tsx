import { useState } from 'react'
import { toast } from 'sonner'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import CredentialsDialog from './CredentialsDialog'
import { federate } from '@/api/roles'
import { ApiError } from '@/api/client'
import type { RoleResponse, AssumeRoleResponse, ConsoleUrlResponse } from '@/api/roles'

interface FederateDropdownProps {
  accountName: string
  accountStatus: string
  awsAccountId: string
  roles: RoleResponse[]
}

export default function FederateDropdown({
  accountName,
  accountStatus,
  awsAccountId,
  roles,
}: FederateDropdownProps) {
  const [credentials, setCredentials] = useState<AssumeRoleResponse | null>(null)
  const [credentialsRoleName, setCredentialsRoleName] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [loading, setLoading] = useState<string | null>(null)

  const disabled = accountStatus !== 'active' || roles.length === 0

  const handleDialogChange = (open: boolean) => {
    setDialogOpen(open)
    if (!open) setCredentials(null)
  }

  const handleFederate = async (roleName: string) => {
    setLoading(roleName)
    try {
      const res = (await federate(awsAccountId, roleName, 'console')) as ConsoleUrlResponse
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
      const res = (await federate(awsAccountId, roleName, 'cli')) as AssumeRoleResponse
      setCredentials(res)
      setCredentialsRoleName(roleName)
      setDialogOpen(true)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Failed to get credentials')
    } finally {
      setLoading(null)
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" disabled={disabled}>
            {loading ? 'Loading...' : 'Federate'}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          {roles.map((role, i) => (
            <DropdownMenuGroup key={role.id}>
              {i > 0 && <DropdownMenuSeparator />}
              <DropdownMenuLabel>{role.role_name}</DropdownMenuLabel>
              <DropdownMenuItem onClick={() => handleFederate(role.role_name)}>
                Federate
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleCopyCli(role.role_name)}>
                Copy CLI
              </DropdownMenuItem>
            </DropdownMenuGroup>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <CredentialsDialog
        open={dialogOpen}
        onOpenChange={handleDialogChange}
        credentials={credentials}
        roleName={credentialsRoleName}
        accountName={accountName}
      />
    </>
  )
}
