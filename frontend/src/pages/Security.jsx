import { useEffect, useState } from 'react'
import { ShieldCheck, ScrollText, KeyRound, LockOpen, AlertTriangle } from 'lucide-react'
import api from '../lib/api'

const TABS = [
  { key: 'auth', label: 'Authentication Monitoring', icon: KeyRound },
  { key: 'actions', label: 'Admin Action Audit Log', icon: ScrollText },
]

const EVENT_LABELS = {
  login_success: 'Login success',
  login_failure: 'Login failure',
  login_blocked_locked: 'Login blocked (account locked)',
  account_locked: 'Account locked',
  account_unlocked: 'Account unlocked',
  password_change: 'Password changed',
  sso_login_success: 'SSO login success',
}

const EVENT_TONE = {
  login_success: 'green',
  sso_login_success: 'green',
  account_unlocked: 'green',
  login_failure: 'orange',
  account_locked: 'red',
  login_blocked_locked: 'red',
  password_change: 'blue',
}

export default function Security() {
  const [tab, setTab] = useState('auth')
  const [summary, setSummary] = useState(null)
  const [authEvents, setAuthEvents] = useState([])
  const [actions, setActions] = useState([])
  const [eventFilter, setEventFilter] = useState('')

  async function load() {
    const [s, a] = await Promise.all([
      api.get('/audit/summary'),
      tab === 'auth'
        ? api.get('/audit/auth-events', { params: { event_type: eventFilter || undefined } })
        : api.get('/audit/actions'),
    ])
    setSummary(s.data)
    if (tab === 'auth') setAuthEvents(a.data)
    else setActions(a.data)
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 8000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, eventFilter])

  async function unlockUser(username) {
    await api.post(`/users/${username}/unlock`)
    load()
  }

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Security</h1>
          <p>Authentication activity and a record of every privileged admin-console action — supports several CMMC Level 2 / NIST 800-171 audit and access-control practices</p>
        </div>
      </div>

      {summary && (
        <div className="ticker-row" style={{ marginBottom: 16 }}>
          <div className="panel ticker-card">
            <div className="ticker-top"><div className="label">Logins (24h)</div></div>
            <div className="ticker-value">{summary.successful_logins_last_24h}</div>
            <div className="ticker-delta up">successful</div>
          </div>
          <div className="panel ticker-card">
            <div className="ticker-top"><div className="label">Failed logins (24h)</div></div>
            <div className="ticker-value">{summary.failed_logins_last_24h}</div>
            <div className="ticker-delta down">including blocked</div>
          </div>
          <div className="panel ticker-card">
            <div className="ticker-top"><div className="label">Locked accounts</div></div>
            <div className="ticker-value">{summary.locked_accounts.length}</div>
            <div className="ticker-delta down">right now</div>
          </div>
          <div className="panel ticker-card">
            <div className="ticker-top"><div className="label">Admin actions logged</div></div>
            <div className="ticker-value">{summary.total_audit_actions}</div>
            <div className="ticker-delta up">all time</div>
          </div>
        </div>
      )}

      {summary?.locked_accounts.length > 0 && (
        <div className="panel" style={{ marginBottom: 16, borderColor: 'rgba(255,84,112,.3)' }}>
          <div className="panel-header"><h3><AlertTriangle size={14} color="var(--accent-red)" /> Currently locked accounts</h3></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {summary.locked_accounts.map((a) => (
              <div key={a.username} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <b>{a.username}</b>
                  <span style={{ color: 'var(--text-muted)', fontSize: 12 }}> — locked until {new Date(a.locked_until * 1000).toLocaleString()}</span>
                </div>
                <button className="btn btn-sm" onClick={() => unlockUser(a.username)}><LockOpen size={13} /> Unlock</button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="tabs-row" style={{ padding: 0, marginBottom: 18, borderBottom: '1px solid var(--border)', paddingBottom: 14 }}>
        {TABS.map((t) => (
          <div key={t.key} className={`tab-pill ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>
            <t.icon size={13} style={{ verticalAlign: -2, marginRight: 6 }} />
            {t.label}
          </div>
        ))}
      </div>

      {tab === 'auth' && (
        <div className="panel">
          <div className="panel-header">
            <h3><ShieldCheck size={15} /> Authentication events</h3>
            <select value={eventFilter} onChange={(e) => setEventFilter(e.target.value)} style={{ width: 220 }}>
              <option value="">All event types</option>
              {Object.entries(EVENT_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          </div>
          <table>
            <thead><tr><th>Time</th><th>Username</th><th>Event</th><th>IP</th><th>Detail</th></tr></thead>
            <tbody>
              {authEvents.length === 0 && <tr><td colSpan={5} className="empty-state">No authentication events yet</td></tr>}
              {authEvents.map((e) => (
                <tr key={e.id}>
                  <td className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{new Date(e.timestamp * 1000).toLocaleString()}</td>
                  <td>{e.username}</td>
                  <td>
                    <span className={`badge badge-${EVENT_TONE[e.event_type] || 'gray'}`}>
                      <span className="badge-dot" />{EVENT_LABELS[e.event_type] || e.event_type}
                    </span>
                  </td>
                  <td className="mono" style={{ fontSize: 12, color: 'var(--text-muted)' }}>{e.ip || '—'}</td>
                  <td style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{e.detail || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'actions' && (
        <div className="panel">
          <div className="panel-header"><h3><ScrollText size={15} /> Admin action audit log</h3></div>
          <p style={{ padding: '0 20px', marginTop: 14, color: 'var(--text-secondary)', fontSize: 12.5 }}>
            Every state-changing (create/update/delete) call to the admin API, captured automatically regardless of
            which page it came from.
          </p>
          <table>
            <thead><tr><th>Time</th><th>User</th><th>Role</th><th>Method</th><th>Path</th><th>Status</th></tr></thead>
            <tbody>
              {actions.length === 0 && <tr><td colSpan={6} className="empty-state">No admin actions logged yet</td></tr>}
              {actions.map((a) => (
                <tr key={a.id}>
                  <td className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{new Date(a.timestamp * 1000).toLocaleString()}</td>
                  <td>{a.username}</td>
                  <td><span className="badge badge-gray">{a.role || '—'}</span></td>
                  <td className="mono" style={{ fontSize: 12 }}>{a.method}</td>
                  <td className="mono" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{a.path}</td>
                  <td>
                    <span className={`badge ${a.status_code < 300 ? 'badge-green' : a.status_code < 400 ? 'badge-blue' : 'badge-red'}`}>
                      {a.status_code}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
