import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Orgs from './pages/Orgs'
import EventsConfig from './pages/EventsConfig'
import Transactions from './pages/Transactions'
import Logs from './pages/Logs'
import Layout from './components/Layout'
import { isAuthed } from './lib/api'

function RequireAuth({ children }) {
  const navigate = useNavigate()

  useEffect(() => {
    function onUnauthorized() { navigate('/login') }
    window.addEventListener('nexus:unauthorized', onUnauthorized)
    return () => window.removeEventListener('nexus:unauthorized', onUnauthorized)
  }, [navigate])

  if (!isAuthed()) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<RequireAuth><Dashboard /></RequireAuth>} />
        <Route path="/orgs" element={<RequireAuth><Orgs /></RequireAuth>} />
        <Route path="/events" element={<RequireAuth><EventsConfig /></RequireAuth>} />
        <Route path="/transactions" element={<RequireAuth><Transactions /></RequireAuth>} />
        <Route path="/logs" element={<RequireAuth><Logs /></RequireAuth>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
