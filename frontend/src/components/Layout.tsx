import { Link, Outlet, useLocation } from 'react-router-dom'
import { Building2, Shield, Activity } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuth } from '@/context/AuthContext'
import Logo from '@/components/Logo'
import { cn } from '@/lib/utils'

const navItems = [
  { to: '/', label: 'Accounts', icon: Building2, match: (p: string) => p === '/' || p.startsWith('/accounts') },
  { to: '/role-templates', label: 'Role Templates', icon: Shield, match: (p: string) => p.startsWith('/role-templates') },
  { to: '/jobs', label: 'Jobs', icon: Activity, match: (p: string) => p.startsWith('/jobs') },
]

function getInitials(name: string): string {
  return name
    .split(/[\s.@_-]+/)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() ?? '')
    .join('')
}

export default function Layout() {
  const { user, isAuthenticated, logout } = useAuth()
  const location = useLocation()

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b bg-card">
        <div className="flex h-13 items-center justify-between px-6">
          <div className="flex items-center gap-7">
            <Link to="/" className="flex items-center gap-2.5 text-[15px] font-semibold text-foreground">
              <Logo />
              Groundwork
            </Link>
            {isAuthenticated && (
              <nav className="flex items-center gap-1">
                {navItems.map(({ to, label, icon: Icon, match }) => {
                  const active = match(location.pathname)
                  return (
                    <Link
                      key={to}
                      to={to}
                      className={cn(
                        'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13.5px] font-medium transition-colors',
                        active
                          ? 'bg-white/[0.06] text-foreground'
                          : 'text-muted-foreground hover:bg-white/[0.05] hover:text-[#a3a3a3]'
                      )}
                    >
                      <Icon
                        className={cn(
                          'size-4',
                          active ? 'text-primary' : ''
                        )}
                      />
                      {label}
                    </Link>
                  )
                })}
              </nav>
            )}
          </div>
          {isAuthenticated && user && (
            <DropdownMenu>
              <DropdownMenuTrigger className="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] text-muted-foreground hover:bg-white/[0.05] outline-none">
                <span className="flex size-6 items-center justify-center rounded-full bg-secondary text-[9px] font-semibold text-[#a3a3a3]">
                  {getInitials(user.display_name)}
                </span>
                {user.display_name}
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={logout}>
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  )
}
