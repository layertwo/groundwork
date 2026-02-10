import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Skeleton } from '@/components/ui/skeleton'

export default function AdminRoute({
  children,
}: {
  children: React.ReactNode
}) {
  const { isAuthenticated, isAdmin, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="space-y-4 p-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/" replace />
  }

  if (!isAdmin) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
