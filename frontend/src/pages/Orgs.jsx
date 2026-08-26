import { useEffect, useState } from 'react'
import { Plus, Building2, Wifi, Pencil, Trash2, PlugZap } from 'lucide-react'
import api from '../lib/api'
import { StatusBadge } from '../components/UI'

const EMPTY_ORG = {
  name: '', description: '', login_url: 'https://login.salesforce.com',
  auth_type: 'password', client_id: '', client_secret: '',
  username: '', password: '', security_token: '', api_version: '60.0', active: true,
}

export default function Orgs() {
  const [orgs, setOrgs] = useState([])
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY_ORG)
  const [saving, setSaving] = useState(false)
  const [testResult, setTestResult] = useState(null)

  async function load() {
    const { data } = await api.get('/orgs')
    setOrgs(data)
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 6000)
    return () => clearInterval(id)
  }, [])

  function openCreate() {
    setEditing(null)
    setForm(EMPTY_ORG)
    setTestResult(null)
    setModalOpen(true)
  }

  function openEdit(org) {
    setEditing(org)
    setForm({ ...EMPTY_ORG, ...org, client_secret: '', password: '', security_token: '' })
    setTestResult(null)
    setModalOpen(true)
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = { ...form }
      // don't overwrite secrets with the masked placeholder if user didn't change them
      if (editing) {
        ;['client_secret', 'password', 'security_token'].forEach((f) => {
          if (!payload[f]) delete payload[f]
        })
        await api.put(`/orgs/${editing.id}`, payload)
      } else {
        await api.post('/orgs', payload)
      }
      setModalOpen(false)
      load()
    } finally {
      setSaving(false)
    }
  }

  async function remove(org) {
    if (!confirm(`Delete org "${org.name}"? This also removes it from all event configs.`)) return
    await api.delete(`/orgs/${org.id}`)
    load()
  }

  async function testConnection(org) {
    setTestResult({ id: org.id, status: 'testing' })
    try {
      const { data } = await api.post(`/orgs/${org.id}/test-connection`)
      setTestResult({ id: org.id, status: 'ok', detail: data.instance_url })
    } catch (err) {
      setTestResult({ id: org.id, status: 'fail', detail: err?.response?.data?.detail || 'Connection failed' })
    }
  }

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Salesforce Orgs</h1>
          <p>Configure and monitor connections to each Salesforce instance</p>
        </div>
        <button className="btn btn-primary" onClick={openCreate}><Plus size={15} /> Add org</button>
      </div>

      {orgs.length === 0 && (
        <div className="panel"><div className="empty-state">No orgs configured yet. Click "Add org" to connect your first Salesforce instance.</div></div>
      )}

      <div className="org-grid">
        {orgs.map((org) => (
          <div className="panel org-card" key={org.id}>
            <div className="org-card-top">
              <div style={{ display: 'flex', gap: 10 }}>
                <div className="ticker-icon" style={{ background: 'rgba(61,139,253,.12)', width: 34, height: 34 }}>
                  <Building2 size={16} color="var(--accent-blue)" />
                </div>
                <div>
                  <h4>{org.name}</h4>
                  <div className="url">{org.login_url}</div>
                </div>
              </div>
              <StatusBadge status={org.active ? org.status : 'disabled'} />
            </div>

            <div className="org-card-meta">
              <div>Auth <b>{org.auth_type}</b></div>
              <div>API <b>v{org.api_version}</b></div>
            </div>
            {org.last_error && (
              <div style={{ fontSize: 11.5, color: 'var(--accent-red)', background: 'rgba(255,84,112,.08)', padding: '6px 8px', borderRadius: 6 }}>
                {org.last_error}
              </div>
            )}
            {testResult?.id === org.id && (
              <div style={{ fontSize: 11.5, color: testResult.status === 'ok' ? 'var(--accent-green)' : testResult.status === 'fail' ? 'var(--accent-red)' : 'var(--text-muted)' }}>
                {testResult.status === 'testing' ? 'Testing connection…' : testResult.detail}
              </div>
            )}
            <div className="org-card-actions">
              <button className="btn btn-sm" onClick={() => testConnection(org)}><PlugZap size={13} /> Test</button>
              <button className="btn btn-sm" onClick={() => openEdit(org)}><Pencil size={13} /> Edit</button>
              <button className="btn btn-sm btn-danger" onClick={() => remove(org)}><Trash2 size={13} /></button>
            </div>
          </div>
        ))}
      </div>

      {modalOpen && (
        <div className="modal-overlay" onClick={() => setModalOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header"><h3><Wifi size={15} /> {editing ? 'Edit org' : 'Add Salesforce org'}</h3></div>
            <form onSubmit={save}>
              <div className="panel-body">
                <div className="field">
                  <label>Org name</label>
                  <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Production, Sandbox, Partner Org…" />
                </div>
                <div className="field">
                  <label>Description</label>
                  <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
                </div>
                <div className="form-row-2">
                  <div className="field">
                    <label>Login URL</label>
                    <input required value={form.login_url} onChange={(e) => setForm({ ...form, login_url: e.target.value })} />
                  </div>
                  <div className="field">
                    <label>API version</label>
                    <input required value={form.api_version} onChange={(e) => setForm({ ...form, api_version: e.target.value })} />
                  </div>
                </div>
                <div className="field">
                  <label>Auth type</label>
                  <select value={form.auth_type} onChange={(e) => setForm({ ...form, auth_type: e.target.value })}>
                    <option value="password">Username / Password / Token</option>
                    <option value="client_credentials">Client Credentials</option>
                    <option value="jwt_bearer">JWT Bearer</option>
                  </select>
                </div>
                <div className="form-row-2">
                  <div className="field">
                    <label>Connected App Client ID</label>
                    <input value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })} />
                  </div>
                  <div className="field">
                    <label>Connected App Client Secret</label>
                    <input type="password" value={form.client_secret} onChange={(e) => setForm({ ...form, client_secret: e.target.value })} placeholder={editing ? '(unchanged)' : ''} />
                  </div>
                </div>
                {form.auth_type === 'password' && (
                  <>
                    <div className="field">
                      <label>Salesforce username</label>
                      <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
                    </div>
                    <div className="form-row-2">
                      <div className="field">
                        <label>Password</label>
                        <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder={editing ? '(unchanged)' : ''} />
                      </div>
                      <div className="field">
                        <label>Security token</label>
                        <input type="password" value={form.security_token} onChange={(e) => setForm({ ...form, security_token: e.target.value })} placeholder={editing ? '(unchanged)' : ''} />
                      </div>
                    </div>
                  </>
                )}
                <div className="field" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input type="checkbox" style={{ width: 16 }} checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} />
                  <label style={{ margin: 0 }}>Active (subscribe/publish enabled)</label>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save org'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
