import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '../lib/api'
import { ShieldCheck, KeyRound } from 'lucide-react'
import api from '../lib/api'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [ssoEnabled, setSsoEnabled] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/auth/sso/status').then((r) => setSsoEnabled(r.data.enabled)).catch(() => {})
  }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await login(username, password)
      navigate('/')
    } catch (err) {
      setError(err?.response?.data?.detail || 'Invalid username or password')
    } finally {
      setBusy(false)
    }
  }

  function handleSso() {
    // Full browser redirect - this is an OAuth/OIDC round trip, not an API call
    window.location.href = '/api/auth/sso/login'
  }

  return (
    <div className="login-screen">
      <div className="panel login-card">
        <div className="login-logo">
          <div className="mark">SN</div>
          <h2>Salesforce Nexus AI Server</h2>
          <p>Admin console</p>
        </div>

        {error && <div className="login-error">{error}</div>}

        {ssoEnabled && (
          <>
            <button className="btn" style={{ width: '100%', justifyContent: 'center', padding: '11px', marginBottom: 14 }} onClick={handleSso} type="button">
              <KeyRound size={15} /> Continue with single sign-on
            </button>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '14px 0', color: 'var(--text-muted)', fontSize: 11.5 }}>
              <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
              or sign in with a local account
              <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            </div>
          </>
        )}

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label>Username</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
          </div>
          <div className="field">
            <label>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', padding: '11px' }} disabled={busy}>
            <ShieldCheck size={15} />
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="login-hint">Default credentials: admin / admin123 — change after first login</div>
      </div>
    </div>
  )
}
