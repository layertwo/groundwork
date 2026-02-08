import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from '@/components/ui/sonner'
import { AuthProvider } from '@/context/AuthContext'
import Layout from '@/components/Layout'
import ProtectedRoute from '@/components/ProtectedRoute'
import AdminRoute from '@/components/AdminRoute'
import Dashboard from '@/pages/Dashboard'
import AccountDetail from '@/pages/AccountDetail'
import AccountCreate from '@/pages/AccountCreate'
import RoleCreate from '@/pages/RoleCreate'
import JobList from '@/pages/JobList'
import RoleTemplates from '@/pages/RoleTemplates'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route
                path="/accounts/new"
                element={
                  <AdminRoute>
                    <AccountCreate />
                  </AdminRoute>
                }
              />
              <Route
                path="/accounts/:id"
                element={
                  <ProtectedRoute>
                    <AccountDetail />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/accounts/:id/roles/new"
                element={
                  <AdminRoute>
                    <RoleCreate />
                  </AdminRoute>
                }
              />
              <Route
                path="/jobs"
                element={
                  <ProtectedRoute>
                    <JobList />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/role-templates"
                element={
                  <ProtectedRoute>
                    <RoleTemplates />
                  </ProtectedRoute>
                }
              />
            </Route>
          </Routes>
        </BrowserRouter>
        <Toaster />
      </AuthProvider>
    </QueryClientProvider>
  )
}
