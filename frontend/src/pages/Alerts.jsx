import { useEffect, useState } from 'react'
import { Plus, Trash2, Send, BellRing } from 'lucide-react'
import api from '../lib/api'

const SCOPE_LABELS = {
  transaction_failed: 'A transaction fails',
  connection_failed: "A Salesforce org's CometD connection fails",
  integration_failed: 'An integration dispatch fails',
  broker_degraded: 'The configured RabbitMQ broker fails to connect',
}

const EMPTY = { name: '', scope: 'transaction_failed', enabled: true, org_id: '', integration_id: '' }

export default function Alerts() {
  const [alerts, setAlerts] = useState([])
  const [orgs, setOrgs] = useState([])
  const [integrations, setIntegrations] = useState([])
  const [modalOpen, setModalOpen] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [testResult, setTestResult] = useState(null)

  async function load() {
    const [a, o, i] = await Promise.all([api.get('/alerts'), api.get('/orgs'), api.get('/integrations')])
    setAlerts(a.data)
    setOrgs(o.data)
    setIntegrations(i.data)
  }

  useEffect(() => { load() }, [])

  function orgName(id) {
    if (!id) return 'All orgs'
    return orgs.find((o) => o.id === id)?.name || id
  }

  function integrationName(id) {
    return integrations.find((i) => i.id === id)?.name || id
  }

  function openCreate() {
    setForm({ ...EMPTY, integration_id: integrations[0]?.id || '' })
    setTestResult(null)
    setModalOpen(true)
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post('/alerts', { ...form, org_id: form.org_id || null })
      setModalOpen(false)
      load()
    } finally {
      setSaving(false)
    }
  }

  async function toggle(alert) {
    await api.put(`/alerts/${alert.id}`, { enabled: !alert.enabled })
    load()
  }

  async function remove(alert) {
    if (!confirm(`Delete alert "${alert.name}"?`)) return
    await api.delete(`/alerts/${alert.id}`)
    load()
  }

  async function sendTest(alert) {
    setTestResult({ id: alert.id, status: 'sending' })
    try {
      await api.post(`/alerts/${alert.id}/test`)
      setTestResult({ id: alert.id, status: 'ok' })
    } catch (err) {
      setTestResult({ id: alert.id, status: 'fail', detail: err?.response?.data?.detail })
    }
    load()
  }

  return (
    <div>
      <div className="page-title-row">
        <div>
          <h1>Alerts</h1>
          <p>Get notified through an existing integration sink when something fails — a transaction, an org connection, an integration, or the message broker</p>
        </div>
        <button className="btn btn-primary" onClick={openCreate} disabled={integrations.length === 0}><Plus size={15} /> Add alert</button>
      </div>

      {integrations.length === 0 && (
        <div className="panel"><div className="empty-state">Add an integration sink first (Integrations page) — alerts deliver through one of those.</div></div>
      )}

      <div className="panel">
        <table>
          <thead><tr><th>Name</th><th>Fires when</th><th>Scope</th><th>Delivers via</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {alerts.length === 0 && <tr><td colSpan={6} className="empty-state">No alerts configured yet</td></tr>}
            {alerts.map((a) => (
              <tr key={a.id}>
                <td>{a.name}</td>
                <td style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{SCOPE_LABELS[a.scope] || a.scope}</td>
                <td>{orgName(a.org_id)}</td>
                <td><Send size={12} style={{ verticalAlign: -1, marginRight: 5 }} />{integrationName(a.integration_id)}</td>
                <td>
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, margin: 0, cursor: 'pointer' }}>
                    <input type="checkbox" style={{ width: 15 }} checked={a.enabled} onChange={() => toggle(a)} />
                    {a.enabled ? 'Enabled' : 'Disabled'}
                  </label>
                  {a.last_status && (
                    <div style={{ fontSize: 11, marginTop: 4, color: a.last_status === 'ok' ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                      last: {a.last_status === 'ok' ? 'delivered' : `failed — ${a.last_error}`}
                    </div>
                  )}
                  {testResult?.id === a.id && (
                    <div style={{ fontSize: 11, marginTop: 4, color: testResult.status === 'ok' ? 'var(--accent-green)' : testResult.status === 'fail' ? 'var(--accent-red)' : 'var(--text-muted)' }}>
                      {testResult.status === 'sending' ? 'Sending…' : testResult.status === 'ok' ? 'Test sent' : `Test failed: ${testResult.detail}`}
                    </div>
                  )}
                </td>
                <td style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-sm btn-icon" onClick={() => sendTest(a)}><Send size={13} /></button>
                  <button className="btn btn-sm btn-icon btn-danger" onClick={() => remove(a)}><Trash2 size={13} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modalOpen && (
        <div className="modal-overlay" onClick={() => setModalOpen(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header"><h3><BellRing size={15} /> Add alert</h3></div>
            <form onSubmit={save}>
              <div className="panel-body">
                <div className="field">
                  <label>Name</label>
                  <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ops on-call notification" />
                </div>
                <div className="field">
                  <label>Fires when…</label>
                  <select value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })}>
                    {Object.entries(SCOPE_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                  </select>
                </div>
                {form.scope !== 'broker_degraded' && (
                  <div className="field">
                    <label>Scope to org (optional)</label>
                    <select value={form.org_id} onChange={(e) => setForm({ ...form, org_id: e.target.value })}>
                      <option value="">All orgs</option>
                      {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                    </select>
                  </div>
                )}
                <div className="field">
                  <label>Deliver via</label>
                  <select required value={form.integration_id} onChange={(e) => setForm({ ...form, integration_id: e.target.value })}>
                    {integrations.map((i) => <option key={i.id} value={i.id}>{i.name} ({i.type}){i.alert_only ? ' — alert-only' : ''}</option>)}
                  </select>
                  <p style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 6 }}>
                    Tip: mark an integration as "alert-only" (on the Integrations page) if you don't want it to also
                    receive normal per-transaction fan-out.
                  </p>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Save alert'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
