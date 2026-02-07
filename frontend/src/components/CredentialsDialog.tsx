import { useEffect, useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

interface Credentials {
  access_key_id: string
  secret_access_key: string
  session_token: string
  expiration: string
}

interface CredentialsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  credentials: Credentials | null
  roleName: string
  accountName: string
}

function formatTimeRemaining(expirationStr: string): string {
  const diff = new Date(expirationStr).getTime() - Date.now()
  if (diff <= 0) return 'Expired'
  const minutes = Math.floor(diff / 60000)
  const seconds = Math.floor((diff % 60000) / 1000)
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export default function CredentialsDialog({
  open,
  onOpenChange,
  credentials,
  roleName,
  accountName,
}: CredentialsDialogProps) {
  const [timeRemaining, setTimeRemaining] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!credentials || !open) return

    const update = () => setTimeRemaining(formatTimeRemaining(credentials.expiration))
    update()
    const interval = setInterval(update, 1000)
    return () => clearInterval(interval)
  }, [credentials, open])

  if (!credentials) return null

  const envVars = [
    `export AWS_ACCESS_KEY_ID=${credentials.access_key_id}`,
    `export AWS_SECRET_ACCESS_KEY=${credentials.secret_access_key}`,
    `export AWS_SESSION_TOKEN=${credentials.session_token}`,
  ].join('\n')

  const handleCopy = async () => {
    await navigator.clipboard.writeText(envVars)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            AWS Credentials — {roleName} @ {accountName}
          </DialogTitle>
        </DialogHeader>
        <pre className="bg-muted rounded-md p-4 text-sm overflow-x-auto select-all">
          {envVars}
        </pre>
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            Expires in {timeRemaining}
          </span>
          <Button onClick={handleCopy} variant="outline" size="sm">
            {copied ? 'Copied' : 'Copy to Clipboard'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
