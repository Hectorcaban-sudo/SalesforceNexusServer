import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import Login from './pages/Login'
import SsoCallback from './pages/SsoCallback'
import Dashboard from './pages/Dashboard'
import Orgs from './pages/Orgs'
import EventsConfig from './pages/EventsConfig'
import Transactions from './pages/Transactions'
import Logs from './pages/Logs'
import AdminConfig from './pages/AdminConfig'
import Users from './pages/Users'
import Integrations from './pages/Integrations'
import Layout from './components/Layout'
import { isAuthed } from './lib/api'
import { AuthProvider, useAuth, hasRole } from './lib/AuthContext'

function RequireAuth({ children }) {
  const navigate = useNavigate()

  useEffect(() => {
    function onUnauthorized() { navigate('/login') }
    window.addEventListener('nexus:unauthorized', onUnauthorized)
    return () => window.removeEventListener('nexus:unauthorized', onUnauthorized)
  }, [navigate])

  if (!isAuthed()) return <Navigate to="/login" replace />
  return (
    <AuthProvider>
      <Layout>{children}</Layout>
    </AuthProvider>
  )
}

function RequireRole({ role, children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="empty-state">Loading…</div>
  if (!hasRole(user, role)) {
    return (
      <div className="panel">
        <div className="empty-state">
          You need the "{role}" role or higher to view this page. Signed in as {user?.username} ({user?.role}).
        </div>
      </div>
    )
  }
  return children
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/sso-callback" element={<SsoCallback />} />
        <Route path="/" element={<RequireAuth><Dashboard /></RequireAuth>} />
        <Route path="/orgs" element={<RequireAuth><Orgs /></RequireAuth>} />
        <Route path="/events" element={<RequireAuth><EventsConfig /></RequireAuth>} />
        <Route path="/transactions" element={<RequireAuth><Transactions /></RequireAuth>} />
        <Route path="/logs" element={<RequireAuth><Logs /></RequireAuth>} />
        <Route path="/admin-config" element={<RequireAuth><RequireRole role="admin"><AdminConfig /></RequireRole></RequireAuth>} />
        <Route path="/users" element={<RequireAuth><RequireRole role="admin"><Users /></RequireRole></RequireAuth>} />
        <Route path="/integrations" element={<RequireAuth><RequireRole role="admin"><Integrations /></RequireRole></RequireAuth>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
