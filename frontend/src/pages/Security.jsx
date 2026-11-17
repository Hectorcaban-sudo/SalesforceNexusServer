import { useEffect, useState } from 'react'
import { ShieldCheck, ScrollText, KeyRound, LockOpen, AlertTriangle, Plus, Trash2 } from 'lucide-react'
import api from '../lib/api'
import { useToast } from '../lib/ToastContext'

const TABS = [
  { key: 'auth', label: 'Authentication Monitoring', icon: KeyRound },
  { key: 'actions', label: 'Admin Action Audit Log', icon: ScrollText },
  { key: 'clients', label: 'API clients', icon: KeyRound },
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
  const { toast } = useToast()
  const [tab, setTab] = useState('auth')
  const [summary, setSummary] = useState(null)
  const [authEvents, setAuthEvents] = useState([])
  const [actions, setActions] = useState([])
  const [eventFilter, setEventFilter] = useState('')
  const [clients, setClients] = useState([])
  const [projects, setProjects] = useState([])
  const [name, setName] = useState('')
  const [projectId, setProjectId] = useState('')
  const [issued, setIssued] = useState(null)

  async function load() {
    const [s, a] = await Promise.all([
      api.get('/audit/summary'),
      tab === 'auth'
        ? api.get('/audit/auth-events', { params: { event_type: eventFilter || undefined } })
        : tab === 'actions'
          ? api.get('/audit/actions')
          : api.get('/api-clients'),
    ])
    setSummary(s.data)
    if (tab === 'auth') setAuthEvents(a.data)
    else if (tab === 'actions') setActions(a.data)
    else setClients(a.data || [])
  }

  useEffect(() => {
    load()
    if (tab === 'clients') api.get('/projects').then((r) => setProjects(r.data || [])).catch(() => {})
    const id = setInterval(load, 8000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, eventFilter])

  async function unlockUser(username) {
    try {
      await api.post(`/users/${username}/unlock`)
      toast('User unlocked')
      load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Failed to unlock user', { kind: 'error' })
    }
  }

  async function createClient(ev) {
    ev.preventDefault()
    try {
      const { data } = await api.post('/api-clients', { name, project_id: projectId || null })
      setIssued(data)
      setName('')
      toast('Client created. Copy the secret now.')
      load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Failed to create client', { kind: 'error' })
    }
  }

  async function toggle(c) {
    try {
      await api.post(`/api-clients/${c.id}/${c.enabled ? 'disable' : 'enable'}`)
      load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Failed to update client', { kind: 'error' })
    }
  }

  async function remove(c) {
    if (!confirm('Delete ' + c.name + '?')) return
    try {
      await api.delete('/api-clients/' + c.id)
      toast('Client deleted')
      load()
    } catch (err) {
      toast(err?.response?.data?.detail || 'Delete failed', { kind: 'error' })
    }
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

      {tab === 'clients' && (
        <div className="panel">
          <div className="panel-header"><h3><KeyRound size={15} /> API clients</h3></div>
          <div className="panel-body">
            <p className="muted">Send these as X-Consumer-Key and X-Consumer-Secret on POST /api/execute/{'{project}'}/pipeline/{'{pipeline_id}'}. A client can be limited to one project.</p>
            <form onSubmit={createClient} className="form-row-2" style={{ marginTop: 12 }}>
              <div className="field"><label>Name</label><input value={name} onChange={(e) => setName(e.target.value)} required /></div>
              <div className="field"><label>Project</label>
                <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                  <option value="">Any project</option>
                  {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div><button className="btn btn-primary"><Plus size={13} /> Create client</button></div>
            </form>
            {issued && (
              <div className="panel" style={{ marginTop: 12, padding: 12 }}>
                <p>Copy the secret now. It is not shown again.</p>
                <div className="mono">Key: {issued.consumer_key}</div>
                <div className="mono">Secret: {issued.consumer_secret}</div>
              </div>
            )}
            <table style={{ marginTop: 16 }}>
              <thead><tr><th>Name</th><th>Consumer key</th><th>Project</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {clients.length === 0 && <tr><td colSpan={5} className="empty-state">No clients yet</td></tr>}
                {clients.map((c) => (
                  <tr key={c.id}>
                    <td>{c.name}</td>
                    <td className="mono">{c.consumer_key}</td>
                    <td>{projects.find((p) => p.id === c.project_id)?.name || (c.project_id ? c.project_id : 'Any')}</td>
                    <td><span className={`badge ${c.enabled ? 'badge-green' : 'badge-gray'}`}>{c.enabled ? 'Enabled' : 'Disabled'}</span></td>
                    <td>
                      <button className="btn btn-sm" onClick={() => toggle(c)}>{c.enabled ? 'Disable' : 'Enable'}</button>
                      <button className="btn btn-sm btn-danger" onClick={() => remove(c)}><Trash2 size={13} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
