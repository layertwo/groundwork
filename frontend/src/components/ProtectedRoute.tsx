import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const REDIRECT_KEY = 'gw:redirect_after_login'

function saveRedirectUrl() {
  const path = window.location.pathname + window.location.search
  if (path && path !== '/') {
    sessionStorage.setItem(REDIRECT_KEY, path)
  }
}

export function consumeRedirectUrl(): string | null {
  const url = sessionStorage.getItem(REDIRECT_KEY)
  sessionStorage.removeItem(REDIRECT_KEY)
  if (url && url.startsWith('/')) {
    return url
  }
  return null
}

export default function ProtectedRoute({
  children,
}: {
  children: React.ReactNode
}) {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return <div className="loading">Loading...</div>
  }

  if (!isAuthenticated) {
    saveRedirectUrl()
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
