# Dark Theme + Navbar UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the white/light theme with a dark theme, restyle the navbar with logo + nav links + user avatar, add search bars to all tables, group accounts by OU, and add an email column.

**Architecture:** Pure frontend changes. Update CSS custom properties in `index.css` to dark-only values, rewrite `Layout.tsx` navbar, update `Dashboard.tsx` with OU grouping + search + email column, add search to `AccountDetail.tsx` and `JobList.tsx`, create a stub `RoleTemplates.tsx` page, wire it in `App.tsx`.

**Tech Stack:** React 19, React Router 7, Tailwind CSS 4, shadcn/ui, Lucide React, TanStack React Query

**Design reference:** `docs/theme-preview-navbar.html` — open in browser for visual reference.

---

### Task 1: Update CSS theme to dark-only

**Files:**
- Modify: `frontend/src/index.css`

**Step 1: Replace the CSS**

Replace the entire contents of `frontend/src/index.css`. The key changes:
- Remove the light `:root` color block entirely
- Move dark colors into `:root` as the only theme
- Update color values to match the design:
  - `--background`: `#161616` (flat charcoal)
  - `--foreground`: `#e5e5e5` (primary text)
  - `--card` / `--popover`: `#1a1a1a` (surface color)
  - `--card-foreground` / `--popover-foreground`: `#e5e5e5`
  - `--primary`: `#047857` (dark emerald — buttons, active icons)
  - `--primary-foreground`: `#ffffff`
  - `--secondary`: `#262626`
  - `--secondary-foreground`: `#e5e5e5`
  - `--muted`: `#262626`
  - `--muted-foreground`: `#737373`
  - `--accent`: `#262626`
  - `--accent-foreground`: `#e5e5e5`
  - `--destructive`: `oklch(0.704 0.191 22.216)` (keep existing)
  - `--border`: `rgba(255, 255, 255, 0.07)`
  - `--input`: `rgba(255, 255, 255, 0.07)`
  - `--ring`: `#047857`
- Remove the `.dark { }` block (no longer needed)
- Remove `@custom-variant dark` line
- Remove sidebar CSS variables from the `@theme inline` block and `:root`
- Keep the `@layer base` block unchanged

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";

@theme inline {
  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) + 4px);
  --radius-2xl: calc(var(--radius) + 8px);
  --radius-3xl: calc(var(--radius) + 12px);
  --radius-4xl: calc(var(--radius) + 16px);
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --color-chart-1: var(--chart-1);
  --color-chart-2: var(--chart-2);
  --color-chart-3: var(--chart-3);
  --color-chart-4: var(--chart-4);
  --color-chart-5: var(--chart-5);
}

:root {
  --radius: 0.625rem;
  --background: #161616;
  --foreground: #e5e5e5;
  --card: #1a1a1a;
  --card-foreground: #e5e5e5;
  --popover: #1a1a1a;
  --popover-foreground: #e5e5e5;
  --primary: #047857;
  --primary-foreground: #ffffff;
  --secondary: #262626;
  --secondary-foreground: #e5e5e5;
  --muted: #262626;
  --muted-foreground: #737373;
  --accent: #262626;
  --accent-foreground: #e5e5e5;
  --destructive: oklch(0.704 0.191 22.216);
  --border: rgba(255, 255, 255, 0.07);
  --input: rgba(255, 255, 255, 0.07);
  --ring: #047857;
  --chart-1: oklch(0.488 0.243 264.376);
  --chart-2: oklch(0.696 0.17 162.48);
  --chart-3: oklch(0.769 0.188 70.08);
  --chart-4: oklch(0.627 0.265 303.9);
  --chart-5: oklch(0.645 0.246 16.439);
}

@layer base {
  * {
    @apply border-border outline-ring/50;
  }
  body {
    @apply bg-background text-foreground;
  }
}
```

**Step 2: Verify the build compiles**

Run: `cd /Users/lucas/groundwork/frontend && npx vite build 2>&1 | tail -5`
Expected: Build succeeds with no errors.

**Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(ui): switch to dark-only theme with emerald accents"
```

---

### Task 2: Create Logo component

**Files:**
- Create: `frontend/src/components/Logo.tsx`

**Step 1: Create the Logo component**

Create `frontend/src/components/Logo.tsx` — an inline SVG component matching the logo from `docs/logo.svg`. Accept `size` prop defaulting to 24. Use `currentColor` for the keyhole fill so it adapts to the background.

```tsx
interface LogoProps {
  size?: number
}

export default function Logo({ size = 24 }: LogoProps) {
  return (
    <svg
      viewBox="0 0 512 512"
      width={size}
      height={size}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="gw-g1" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#34d399" />
          <stop offset="100%" stopColor="#059669" />
        </linearGradient>
        <linearGradient id="gw-g2" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#059669" />
          <stop offset="100%" stopColor="#047857" />
        </linearGradient>
        <linearGradient id="gw-g3" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#047857" />
          <stop offset="100%" stopColor="#065f46" />
        </linearGradient>
      </defs>
      <path d="M256 100 L436 180 L256 260 L76 180 Z" fill="url(#gw-g1)" />
      <path d="M76 230 L256 310 L436 230 L436 280 L256 360 L76 280 Z" fill="url(#gw-g2)" />
      <path d="M76 330 L256 410 L436 330 L436 380 L256 460 L76 380 Z" fill="url(#gw-g3)" />
      <path
        d="M256 150 C240 150 228 162 228 178 C228 189 234 198 244 203 L240 230 L272 230 L268 203 C278 198 284 189 284 178 C284 162 272 150 256 150 Z"
        fill="#1a1a1a"
        opacity="0.85"
      />
    </svg>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/Logo.tsx
git commit -m "feat(ui): add inline SVG Logo component"
```

---

### Task 3: Create SearchInput component

**Files:**
- Create: `frontend/src/components/SearchInput.tsx`

**Step 1: Create the SearchInput component**

A reusable search input with a magnifying glass icon. Uses Lucide `Search` icon and the shadcn `Input` component. Accepts `placeholder` and passes through standard input props.

```tsx
import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

interface SearchInputProps extends React.ComponentProps<'input'> {
  containerClassName?: string
}

export default function SearchInput({
  className,
  containerClassName,
  ...props
}: SearchInputProps) {
  return (
    <div className={cn('relative', containerClassName)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input className={cn('pl-9', className)} {...props} />
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/SearchInput.tsx
git commit -m "feat(ui): add reusable SearchInput component"
```

---

### Task 4: Rewrite Layout.tsx navbar

**Files:**
- Modify: `frontend/src/components/Layout.tsx`

**Step 1: Rewrite Layout.tsx**

Replace the entire `Layout.tsx` with the new navbar design. Key changes:
- Add Logo component alongside "Groundwork" text
- Add three nav links with Lucide icons: Accounts (`/`), Role Templates (`/role-templates`), Jobs (`/jobs`)
- Use `useLocation` to highlight the active nav item
- Active nav item: white text + green icon. Inactive: muted gray.
- Show `user.display_name` instead of `user.email` in the user dropdown
- User avatar circle with initials
- Remove the `<Separator />` (border-bottom on the header handles it)
- Main content area uses `max-w-6xl mx-auto` for centered layout

```tsx
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
```

**Step 2: Verify the build compiles**

Run: `cd /Users/lucas/groundwork/frontend && npx vite build 2>&1 | tail -5`
Expected: Build succeeds with no errors.

**Step 3: Commit**

```bash
git add frontend/src/components/Layout.tsx
git commit -m "feat(ui): restyle navbar with logo, nav links, and user avatar"
```

---

### Task 5: Update Dashboard with OU grouping, email column, and search

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: Rewrite Dashboard.tsx**

Key changes to the authenticated view:
- Add `useState` for search query
- Add `SearchInput` above the table with placeholder "Search accounts..."
- Group accounts by `organizational_unit` — sort by OU name, render an OU header row before each group
- Add Email column (`account.account_email`) between Name and AWS ID columns
- Filter accounts by search query (matches against name, email, AWS ID, or OU — case insensitive)
- Remove the Landing component's `<h1>Groundwork</h1>` hero — simplify to just the SSO button and a subtitle
- OU header row uses Lucide `Folder` icon, spans all 5 columns, uppercase dimmed text

```tsx
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Folder } from 'lucide-react'
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
import SearchInput from '@/components/SearchInput'

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

  const grouped = useMemo(() => {
    if (!accounts) return []
    const q = search.toLowerCase()
    const filtered = q
      ? accounts.filter(
          (a) =>
            a.account_name.toLowerCase().includes(q) ||
            a.account_email.toLowerCase().includes(q) ||
            (a.aws_account_id ?? '').includes(q) ||
            a.organizational_unit.toLowerCase().includes(q)
        )
      : accounts
    const map = new Map<string, typeof accounts>()
    for (const a of filtered) {
      const ou = a.organizational_unit
      if (!map.has(ou)) map.set(ou, [])
      map.get(ou)!.push(a)
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [accounts, search])

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
          <Button asChild>
            <Link to="/accounts/new">+ New Account</Link>
          </Button>
        )}
      </div>

      <SearchInput
        placeholder="Search accounts..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

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
                    <TableRow key={account.id}>
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
```

**Step 2: Verify the build compiles**

Run: `cd /Users/lucas/groundwork/frontend && npx vite build 2>&1 | tail -5`
Expected: Build succeeds with no errors.

**Step 3: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(ui): group accounts by OU, add email column and search"
```

---

### Task 6: Add search to AccountDetail roles table

**Files:**
- Modify: `frontend/src/pages/AccountDetail.tsx`

**Step 1: Add search state and filter**

Add these changes to `AccountDetail.tsx`:
- Import `SearchInput` from `@/components/SearchInput`
- Add `const [roleSearch, setRoleSearch] = useState('')` (import `useState` is already there)
- Filter the `roles` array: `const filteredRoles = roles.filter(r => ...)` matching against `role_name`, `description`, `allowed_groups`, `allowed_users` (case insensitive)
- Render `<SearchInput>` above the roles table, placeholder "Search roles..."
- Use `filteredRoles` instead of `roles` for the table body and the empty-state check

The specific edits (leaving everything else unchanged):

1. Add import: `import SearchInput from '@/components/SearchInput'`
2. After the `const roles = ...` line (~line 59), add:
```tsx
const [roleSearch, setRoleSearch] = useState('')
const filteredRoles = useMemo(() => {
  const q = roleSearch.toLowerCase()
  if (!q) return roles
  return roles.filter(
    (r) =>
      r.role_name.toLowerCase().includes(q) ||
      (r.description ?? '').toLowerCase().includes(q) ||
      r.allowed_groups.some((g) => g.toLowerCase().includes(q)) ||
      r.allowed_users.some((u) => u.toLowerCase().includes(q))
  )
}, [roles, roleSearch])
```
3. Add `useMemo` to the existing `import { useState }` at the top (change to `import { useState, useMemo }`)
4. Before the `<Table>` in the roles section, add:
```tsx
<SearchInput
  placeholder="Search roles..."
  value={roleSearch}
  onChange={(e) => setRoleSearch(e.target.value)}
/>
```
5. Change `roles.length === 0` empty check to `roles.length === 0` (keep — shows "No roles" if there are genuinely none)
6. Change `roles.map(...)` in the table body to `filteredRoles.map(...)`
7. If `filteredRoles.length === 0 && roles.length > 0`, show "No roles match your search." instead of the table

**Step 2: Verify the build compiles**

Run: `cd /Users/lucas/groundwork/frontend && npx vite build 2>&1 | tail -5`
Expected: Build succeeds with no errors.

**Step 3: Commit**

```bash
git add frontend/src/pages/AccountDetail.tsx
git commit -m "feat(ui): add search to account detail roles table"
```

---

### Task 7: Add search to JobList

**Files:**
- Modify: `frontend/src/pages/JobList.tsx`

**Step 1: Add search state and filter**

Add these changes to `JobList.tsx`:
- Import `SearchInput` from `@/components/SearchInput`
- Add `import { useMemo } from 'react'` (already has `useState`)
- Add `const [search, setSearch] = useState('')`
- After `const accountMap = ...`, add:
```tsx
const filteredJobs = useMemo(() => {
  if (!jobs) return []
  const q = search.toLowerCase()
  if (!q) return jobs
  return jobs.filter(
    (j) =>
      j.job_type.toLowerCase().includes(q) ||
      j.status.toLowerCase().includes(q) ||
      (j.account_id ? (accountMap.get(j.account_id) ?? j.account_id) : '').toLowerCase().includes(q)
  )
}, [jobs, search, accountMap])
```
- Render `<SearchInput>` after the filter dropdowns row, placeholder "Search jobs..."
- Use `filteredJobs` instead of `jobs` for table rendering

**Step 2: Verify the build compiles**

Run: `cd /Users/lucas/groundwork/frontend && npx vite build 2>&1 | tail -5`
Expected: Build succeeds with no errors.

**Step 3: Commit**

```bash
git add frontend/src/pages/JobList.tsx
git commit -m "feat(ui): add search to jobs table"
```

---

### Task 8: Create RoleTemplates stub page and wire routing

**Files:**
- Create: `frontend/src/pages/RoleTemplates.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Create the stub page**

Create `frontend/src/pages/RoleTemplates.tsx`:

```tsx
export default function RoleTemplates() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold tracking-tight">Role Templates</h1>
      <div className="text-muted-foreground">Role templates will be listed here.</div>
    </div>
  )
}
```

**Step 2: Add the route to App.tsx**

In `frontend/src/App.tsx`:
- Add import: `import RoleTemplates from '@/pages/RoleTemplates'`
- Add a new `<Route>` inside the `<Route element={<Layout />}>` block, after the jobs route:
```tsx
<Route
  path="/role-templates"
  element={
    <ProtectedRoute>
      <RoleTemplates />
    </ProtectedRoute>
  }
/>
```

**Step 3: Verify the build compiles**

Run: `cd /Users/lucas/groundwork/frontend && npx vite build 2>&1 | tail -5`
Expected: Build succeeds with no errors.

**Step 4: Commit**

```bash
git add frontend/src/pages/RoleTemplates.tsx frontend/src/App.tsx
git commit -m "feat(ui): add Role Templates stub page and route"
```

---

### Task 9: Final build verification and cleanup

**Step 1: Full build**

Run: `cd /Users/lucas/groundwork/frontend && npx vite build`
Expected: Build succeeds with no errors.

**Step 2: Check for TypeScript errors**

Run: `cd /Users/lucas/groundwork/frontend && npx tsc --noEmit`
Expected: No type errors.

**Step 3: Delete the old sidebar preview file**

The sidebar preview (`docs/theme-preview.html`) was already deleted. Verify:

Run: `ls /Users/lucas/groundwork/docs/theme-preview.html 2>&1`
Expected: "No such file or directory"

**Step 4: Final commit if any fixes were needed**

Only commit if fixes were made in previous steps.
